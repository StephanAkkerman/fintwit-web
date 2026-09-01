"""Guards that the test extra stays consistent with the runtime manifest.

`requirements.txt` is what production installs; the ``test`` extra in
`pyproject.toml` is a deliberate subset used by CI and local runs. Two manifests
means two places for a version to change, so this pins down the relationship
rather than trusting it: shared packages must agree, and the ML stack must stay
out of the test extra (installing it is what previously exhausted the CI
runner's disk).
"""

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Left out of the test extra on purpose: `app/ml/` imports these lazily inside
# functions, so no test needs them, and they cost ~2.5 GB of CUDA wheels.
LAZY_ML_PACKAGES = {"torch", "timm", "transformers", "pillow"}

_REQUIREMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)"  # package name
    r"(?:\[(?P<extras>[^\]]*)\])?"  # optional extras
    r"(?P<specifier>.*)$"  # version specifier, if any
)


def _normalize(name: str) -> str:
    """Normalize a distribution name per PEP 503."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _parse(line: str) -> tuple[str, str] | None:
    line = line.split("#", 1)[0].strip()
    # Drop any environment marker so a conditional pin compares on its version
    # specifier alone.
    line = line.split(";", 1)[0].strip()
    if not line or line.startswith("-"):
        return None

    match = _REQUIREMENT.match(line)
    if match is None:
        return None

    return _normalize(match["name"]), match["specifier"].strip()


def _requirements() -> dict[str, str]:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    parsed = (_parse(line) for line in text.splitlines())
    return {name: spec for name, spec in filter(None, parsed)}


def _test_extra() -> dict[str, str]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    entries = pyproject["project"]["optional-dependencies"]["test"]
    parsed = (_parse(entry) for entry in entries)
    return {name: spec for name, spec in filter(None, parsed)}


def test_test_extra_is_not_empty():
    assert _test_extra(), "the [test] extra should list the pytest dependencies"


def test_shared_packages_pin_the_same_version():
    """A package in both manifests must carry an identical specifier."""
    requirements = _requirements()
    mismatched = {
        name: (spec, requirements[name])
        for name, spec in _test_extra().items()
        if name in requirements and spec != requirements[name]
    }

    assert not mismatched, (
        "version drift between pyproject [test] extra and requirements.txt: "
        + ", ".join(
            f"{name} is {extra!r} vs {runtime!r}"
            for name, (extra, runtime) in sorted(mismatched.items())
        )
    )


def test_test_extra_excludes_the_lazy_ml_stack():
    present = LAZY_ML_PACKAGES & _test_extra().keys()
    assert not present, (
        f"{sorted(present)} must stay out of the test extra — app/ml imports them "
        "lazily, so tests never need them and installing them fills the CI disk"
    )


def test_lazy_ml_packages_are_absent_at_import_time():
    """Importing the app must not drag in the ML stack.

    This is the property the test extra relies on: if someone moves a `torch`
    import to module scope, the extra silently stops being sufficient and CI
    fails with a bare ImportError instead of explaining itself.

    Run in a subprocess so the result does not depend on what earlier tests
    already pulled into `sys.modules`, and holds whether or not the ML packages
    happen to be installed.
    """
    probe = (
        "import app.api.main, sys;"
        "leaked = {'torch', 'timm', 'transformers'} &"
        " {n.split('.', 1)[0] for n in sys.modules};"
        "print(','.join(sorted(leaked)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 0, f"importing app.api.main failed:\n{result.stderr}"

    leaked = result.stdout.strip()
    assert not leaked, (
        f"{leaked} was imported at module scope; keep ML imports inside the "
        "functions that use them so the test environment stays light"
    )


# Import names that differ from the distribution that provides them. Anything
# not listed here is assumed to install under its own name (normalized).
_MODULE_TO_DISTRIBUTION = {
    "dateutil": "python-dateutil",
    "dotenv": "dotenv",
    "PIL": "pillow",
    "xclient": "xtimeline",
}

# Imported by app/ but deliberately not declared: these ship with Python, or are
# provided by the environment rather than the manifest.
_NOT_DECLARED_ON_PURPOSE: set[str] = set()


def _third_party_imports() -> dict[str, str]:
    """Map every third-party module imported under app/ to where it is used.

    Walks the AST rather than the import machinery, so the result does not
    depend on which packages happen to be installed.
    """
    imports: dict[str, str] = {}

    for path in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # A non-zero level is a relative import — our own package.
                modules = [] if node.level else [(node.module or "").split(".")[0]]
            else:
                continue

            for module in modules:
                if not module or module == "app" or module in sys.stdlib_module_names:
                    continue
                imports.setdefault(module, f"{path.relative_to(ROOT)}:{node.lineno}")

    return imports


def test_every_imported_package_is_declared():
    """app/ must not rely on a transitive dependency for a direct import.

    A package that arrives only because something else happens to depend on it
    disappears the day that dependency drops it, and the failure surfaces at
    runtime rather than at install time.
    """
    declared = _requirements().keys()

    undeclared = {
        module: where
        for module, where in _third_party_imports().items()
        if module not in _NOT_DECLARED_ON_PURPOSE
        and _normalize(_MODULE_TO_DISTRIBUTION.get(module, module)) not in declared
    }

    assert not undeclared, (
        "imported by app/ but missing from requirements.txt: "
        + ", ".join(
            f"{module} ({where})" for module, where in sorted(undeclared.items())
        )
        + ". Add the distribution that provides it, or map the import name in "
        "_MODULE_TO_DISTRIBUTION if the two differ."
    )
