# Cloudflare IaC (Terraform)

This folder provisions Cloudflare DNS and a managed cloudflared tunnel for
serving fintwit-web from your Raspberry Pi.

## Resources Created

- Cloudflare tunnel (`cloudflare_zero_trust_tunnel_cloudflared`)
- Tunnel ingress config (`cloudflare_zero_trust_tunnel_cloudflared_config`)
- DNS CNAME record: `<subdomain>.<zone_name>` -> `<tunnel-id>.cfargotunnel.com`
- Access application + allow policy (`cloudflare_zero_trust_access_application`,
  `cloudflare_zero_trust_access_policy`) gating the public hostname behind a login —
  only the emails listed in `access_allowed_emails` can get in, via Cloudflare's
  hosted one-time-PIN screen. No separate identity provider needed.

## Prerequisites

- Domain delegated to Cloudflare nameservers
- Cloudflare API token with:
  - Account: Cloudflare Tunnel Edit
  - Account: Access: Apps and Policies Edit
  - Zone: DNS Edit
- Docker + Docker Compose on the Pi

## Quick Run

1. Copy vars file:
   - `cp terraform.tfvars.example terraform.tfvars`
2. Fill in token/account values.
3. Apply Terraform:
   - `terraform init`
   - `terraform plan`
   - `terraform apply`
4. Read tunnel token:
   - `terraform output -raw tunnel_token`
5. Start app + tunnel from repo root. `cloudflared` is behind the `tunnel` Compose profile
   (see the root [README](../README.md#deploy-with-docker)), so either set
   `CLOUDFLARE_TUNNEL_TOKEN` and `COMPOSE_PROFILES=tunnel` in `.env` and run
   `docker compose up -d --build`, or:
   - `CLOUDFLARE_TUNNEL_TOKEN=<token> docker compose --profile tunnel up -d --build`

## Notes

- By default this config assumes cloudflared runs as a Compose service and routes to
  `http://frontend:80`.
- If you run cloudflared directly on the host instead of Compose, set
  `tunnel_origin_url = "http://localhost:3000"`.
- `access_allowed_emails` only seeds the policy on the *first* apply — the policy's
  `include` list is then `lifecycle.ignore_changes`d so the Admin page (below) can manage
  it without Terraform reverting those edits on the next apply.
- Access enforcement lives entirely at Cloudflare's edge; the backend and frontend
  containers have no awareness of it and stay unauthenticated on localhost/LAN.

## Admin page invites

Once the Access application + policy exist, the app's own **Admin** page (`/admin`) can add
and remove allowed emails without touching Terraform at all — useful for showing the
dashboard to a friend on short notice. It calls the Cloudflare API directly
(`app/services/cloudflare_access.py`), so it needs its own credentials in the backend's
`.env` (see `.env.example`):

- `CLOUDFLARE_ACCESS_API_TOKEN` — a **separate** token from the one Terraform uses, scoped
  to only **Account: Access: Apps and Policies Edit**. Keeping it narrower than the
  Terraform token means a leaked runtime secret can't touch DNS or the tunnel.
- `CLOUDFLARE_ACCOUNT_ID` — same value as `cloudflare_account_id` in `terraform.tfvars`.
- `CLOUDFLARE_ACCESS_APP_ID` — `terraform output -raw access_application_id`.
- `CLOUDFLARE_ACCESS_POLICY_ID` — `terraform output -raw access_policy_id`.

Leave these unset if you'd rather manage the allowlist purely through `terraform.tfvars` —
the Admin panel just shows "Cloudflare Access isn't configured" and the tunnel still works
with whatever `access_allowed_emails` provisioned.
