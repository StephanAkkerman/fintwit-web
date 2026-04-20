"""Probe PyTorch/timm chart stack to isolate Illegal instruction failures.

Run inside the backend container:
python -m app.runtime.probe_chart_stack

Each probe runs in a child process. This allows the script to continue and report
which exact stage crashed, even when a probe dies with SIGILL.
"""

from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Probe:
    name: str
    code: str


PROBES: list[Probe] = [
    Probe(
        name="versions",
        code=(
            "import json, platform; "
            "import torch, timm, numpy; "
            "print(json.dumps({'python': platform.python_version(), "
            "'machine': platform.machine(), 'platform': platform.platform(), "
            "'torch': torch.__version__, 'timm': timm.__version__, "
            "'numpy': numpy.__version__}, indent=2))"
        ),
    ),
    Probe(
        name="torch_matmul",
        code=(
            "import torch; "
            "x=torch.randn(64,64); y=x@x; "
            "print('ok', tuple(y.shape), float(y.mean()))"
        ),
    ),
    Probe(
        name="torch_conv2d",
        code=(
            "import torch; "
            "conv=torch.nn.Conv2d(3,32,3,padding=1); "
            "x=torch.randn(1,3,224,224); "
            "y=conv(x); "
            "print('ok', tuple(y.shape), float(y.mean()))"
        ),
    ),
    Probe(
        name="timm_efficientnet_forward",
        code=(
            "import torch, timm; "
            "m=timm.create_model('efficientnet_b0', pretrained=False); "
            "m.eval(); "
            "x=torch.randn(1,3,224,224); "
            "with torch.no_grad(): y=m(x); "
            "print('ok', tuple(y.shape), float(y.mean()))"
        ),
    ),
    Probe(
        name="hf_chart_model_load",
        code=(
            "import timm; "
            "m=timm.create_model('hf_hub:StephanAkkerman/chart-recognizer', pretrained=True); "
            "m.eval(); "
            "print('ok', type(m).__name__)"
        ),
    ),
    Probe(
        name="hf_chart_model_forward",
        code=(
            "import torch, timm; "
            "m=timm.create_model('hf_hub:StephanAkkerman/chart-recognizer', pretrained=True); "
            "m.eval(); "
            "x=torch.randn(1,3,224,224); "
            "with torch.no_grad(): y=m(x); "
            "print('ok', tuple(y.shape), float(y.mean()))"
        ),
    ),
]


def _signal_name(sig_number: int) -> str:
    try:
        return signal.Signals(sig_number).name
    except Exception:
        return f"SIG{sig_number}"


def run_probe(probe: Probe) -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONFAULTHANDLER", "1")

    proc = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", probe.code],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )

    result: dict[str, object] = {
        "name": probe.name,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "status": "ok" if proc.returncode == 0 else "failed",
    }

    if proc.returncode < 0:
        sig_number = -proc.returncode
        result["status"] = "crashed"
        result["signal"] = _signal_name(sig_number)

    return result


def main() -> int:
    print("== chart stack probe ==")
    print(f"host_machine={platform.machine()} platform={platform.platform()}")

    results: list[dict] = []
    for probe in PROBES:
        print(f"\n-- {probe.name} --")
        try:
            res = run_probe(probe)
        except subprocess.TimeoutExpired:
            res = {
                "name": probe.name,
                "status": "timeout",
                "returncode": None,
                "stdout": "",
                "stderr": "probe timed out",
            }

        results.append(res)
        print(f"status={res['status']} returncode={res['returncode']}")
        if res.get("signal"):
            print(f"signal={res['signal']}")
        if res["stdout"]:
            print("stdout:")
            print(res["stdout"])
        if res["stderr"]:
            print("stderr:")
            print(res["stderr"])

        if res["status"] in {"crashed", "failed", "timeout"}:
            print("\nStopping early at first failing probe.")
            break

    print("\n== summary ==")
    print(json.dumps(results, indent=2))

    first_bad = next(
        (r for r in results if r["status"] in {"crashed", "failed", "timeout"}),
        None,
    )
    if first_bad is None:
        print("All probes passed.")
        return 0

    print(f"First failing probe: {first_bad['name']} ({first_bad['status']})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
