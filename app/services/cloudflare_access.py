"""Manage the Cloudflare Access allowlist that gates the public tunnel.

Terraform (`infra/`) creates the Access application and policy and seeds the
policy's allowlist from `access_allowed_emails`, then stops managing that
list (`lifecycle.ignore_changes`) so this module can add and remove emails
at runtime through the Admin panel without fighting `terraform apply`.
"""

import os

import httpx

_API_BASE = "https://api.cloudflare.com/client/v4"
_READ_ONLY_FIELDS = ("id", "created_at", "updated_at")


class CloudflareAccessError(RuntimeError):
    """Raised when the Access allowlist can't be read or changed."""


def _config() -> tuple[str, str, str, str]:
    token = os.getenv("CLOUDFLARE_ACCESS_API_TOKEN")
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    app_id = os.getenv("CLOUDFLARE_ACCESS_APP_ID")
    policy_id = os.getenv("CLOUDFLARE_ACCESS_POLICY_ID")
    if not all([token, account_id, app_id, policy_id]):
        raise CloudflareAccessError(
            "Cloudflare Access isn't configured on this deployment — set "
            "CLOUDFLARE_ACCESS_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, "
            "CLOUDFLARE_ACCESS_APP_ID, and CLOUDFLARE_ACCESS_POLICY_ID "
            "(see infra/README.md)."
        )
    return token, account_id, app_id, policy_id


def _policy_url(account_id: str, app_id: str, policy_id: str) -> str:
    return (
        f"{_API_BASE}/accounts/{account_id}/access/apps/{app_id}/policies/{policy_id}"
    )


def _emails_from_policy(policy: dict) -> set[str]:
    return {
        rule["email"]["email"]
        for rule in policy.get("include") or []
        if "email" in rule
    }


async def _get_policy(
    client: httpx.AsyncClient, token: str, account_id: str, app_id: str, policy_id: str
) -> dict:
    response = await client.get(
        _policy_url(account_id, app_id, policy_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise CloudflareAccessError(
            f"Cloudflare rejected the request: {data.get('errors')}"
        )
    return data["result"]


async def _put_policy(
    client: httpx.AsyncClient,
    token: str,
    account_id: str,
    app_id: str,
    policy_id: str,
    policy: dict,
) -> None:
    body = {k: v for k, v in policy.items() if k not in _READ_ONLY_FIELDS}
    response = await client.put(
        _policy_url(account_id, app_id, policy_id),
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise CloudflareAccessError(
            f"Cloudflare rejected the request: {data.get('errors')}"
        )


async def list_allowed_emails(client: httpx.AsyncClient) -> list[str]:
    """Current allowlist, straight from the Access policy."""
    token, account_id, app_id, policy_id = _config()
    try:
        policy = await _get_policy(client, token, account_id, app_id, policy_id)
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise CloudflareAccessError(f"Could not fetch the Access allowlist: {e}") from e
    return sorted(_emails_from_policy(policy))


async def _update_allowed_emails(
    client: httpx.AsyncClient, email: str, *, add: bool
) -> list[str]:
    token, account_id, app_id, policy_id = _config()
    try:
        policy = await _get_policy(client, token, account_id, app_id, policy_id)
        emails = _emails_from_policy(policy)
        if add:
            emails.add(email)
        else:
            emails.discard(email)
        policy["include"] = [{"email": {"email": e}} for e in sorted(emails)]
        await _put_policy(client, token, account_id, app_id, policy_id, policy)
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise CloudflareAccessError(
            f"Could not update the Access allowlist: {e}"
        ) from e
    return sorted(emails)


async def add_allowed_email(client: httpx.AsyncClient, email: str) -> list[str]:
    return await _update_allowed_emails(client, email, add=True)


async def remove_allowed_email(client: httpx.AsyncClient, email: str) -> list[str]:
    return await _update_allowed_emails(client, email, add=False)
