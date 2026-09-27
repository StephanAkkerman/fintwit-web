"""One-line summary of which optional integrations this deployment has enabled.

Settings stay read where they're used (several services read them at call time
on purpose); this only reports them, so a new install shows at startup what is
on, what is off, and which variable turns it on.
"""

import os

from .ml.chart import _chart_enabled
from .runtime.streamer import _credential_source
from .services.reddit_service import has_reddit_credentials
from .services.signa import has_signa_key

_CLOUDFLARE_ACCESS_VARS = (
    "CLOUDFLARE_ACCESS_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_ACCESS_APP_ID",
    "CLOUDFLARE_ACCESS_POLICY_ID",
)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def integration_status() -> dict[str, str]:
    """Map each optional integration to a short state, e.g. ``{"X": "cookies"}``.

    Returns
    -------
    dict[str, str]
        Integration name to ``on``/``off`` or a more specific mode.
    """
    return {
        "X timeline": _credential_source() or "off (set X_AUTH_TOKEN, X_CT0)",
        "Reddit": (
            "authenticated" if has_reddit_credentials() else "unauthenticated fallback"
        ),
        "IBKR": "on" if _flag("IBKR_ENABLED") else "off",
        "Signa": "on" if has_signa_key() else "off",
        "Access admin": (
            "on" if all(os.getenv(v) for v in _CLOUDFLARE_ACCESS_VARS) else "off"
        ),
        "chart recognition": "on" if _chart_enabled() else "off",
        "API key": "on" if os.getenv("API_KEY") else "off",
    }


def integration_summary() -> str:
    """Render :func:`integration_status` as a single log line."""
    return " | ".join(
        f"{name}: {state}" for name, state in integration_status().items()
    )
