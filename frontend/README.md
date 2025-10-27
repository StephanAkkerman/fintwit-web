# X Stream Frontend (Vite + React + Tailwind)

A lightweight SPA that connects to your FastAPI backend:

- `GET /api/posts` for initial load
- `GET /api/stream` (SSE) for live updates

## Dev setup

```bash
npm ci
npm run dev
```

The dev server proxies `/api/*` to `http://localhost:8000` (see `vite.config.ts`).

## Build

```bash
npm run build
```

Outputs static files in `dist/`. Serve them with Caddy or any static server and reverse-proxy `/api/*` to your FastAPI app.

## Notes

- If your backend requires an `X-API-Key`, inject it at the reverse proxy so the browser bundle doesn't include secrets.
- For self-hosting on Raspberry Pi, build on-device or use `docker buildx` with `--platform linux/arm64`.