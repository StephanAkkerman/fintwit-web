"""Shared API key dependency, so routers outside main.py can require it too."""

from fastapi import HTTPException, Request


async def api_key_dep(request: Request):
    expected = getattr(request.app.state, "API_KEY", "")
    got = request.headers.get("X-API-Key")
    if expected and got != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
