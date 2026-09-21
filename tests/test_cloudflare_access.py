"""Tests for the Cloudflare Access allowlist service."""

import httpx
import pytest

from app.services import cloudflare_access as ca

pytestmark = pytest.mark.asyncio


class _FakeClient:
    def __init__(self, get_response, put_response=None):
        self._get_response = get_response
        self._put_response = put_response
        self.put_calls = []

    async def get(self, url, headers=None):
        return self._get_response

    async def put(self, url, headers=None, json=None):
        self.put_calls.append(json)
        return self._put_response


def _response(status_code, json_body):
    # raise_for_status() needs a request attached, which the constructor
    # doesn't set unless we pass one in.
    return httpx.Response(
        status_code, json=json_body, request=httpx.Request("GET", "http://testserver")
    )


def _policy_response(emails):
    return _response(
        200,
        {
            "success": True,
            "result": {
                "id": "policy123",
                "name": "Allowed users",
                "decision": "allow",
                "precedence": 1,
                "include": [{"email": {"email": e}} for e in emails],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        },
    )


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCESS_API_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_ACCESS_APP_ID", "app")
    monkeypatch.setenv("CLOUDFLARE_ACCESS_POLICY_ID", "policy")


async def test_list_allowed_emails_sorted():
    client = _FakeClient(_policy_response(["b@example.com", "a@example.com"]))
    emails = await ca.list_allowed_emails(client)
    assert emails == ["a@example.com", "b@example.com"]


async def test_add_allowed_email_strips_readonly_fields_on_put():
    client = _FakeClient(
        _policy_response(["a@example.com"]),
        put_response=_response(200, {"success": True, "result": {}}),
    )
    emails = await ca.add_allowed_email(client, "b@example.com")

    assert emails == ["a@example.com", "b@example.com"]
    sent = client.put_calls[0]
    assert sent["include"] == [
        {"email": {"email": "a@example.com"}},
        {"email": {"email": "b@example.com"}},
    ]
    assert "id" not in sent
    assert "created_at" not in sent
    assert "updated_at" not in sent
    # Fields the API needs on a PUT must survive the round-trip.
    assert sent["name"] == "Allowed users"
    assert sent["decision"] == "allow"
    assert sent["precedence"] == 1


async def test_remove_allowed_email():
    client = _FakeClient(
        _policy_response(["a@example.com", "b@example.com"]),
        put_response=_response(200, {"success": True, "result": {}}),
    )
    emails = await ca.remove_allowed_email(client, "a@example.com")
    assert emails == ["b@example.com"]


async def test_removing_email_not_on_list_is_a_noop():
    client = _FakeClient(
        _policy_response(["a@example.com"]),
        put_response=_response(200, {"success": True, "result": {}}),
    )
    emails = await ca.remove_allowed_email(client, "missing@example.com")
    assert emails == ["a@example.com"]


async def test_missing_config_raises(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCESS_API_TOKEN", raising=False)
    client = _FakeClient(_policy_response([]))
    with pytest.raises(ca.CloudflareAccessError):
        await ca.list_allowed_emails(client)


async def test_cloudflare_rejection_raises():
    client = _FakeClient(_response(200, {"success": False, "errors": ["nope"]}))
    with pytest.raises(ca.CloudflareAccessError):
        await ca.list_allowed_emails(client)
