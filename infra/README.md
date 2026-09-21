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
- To let someone else in later, add their email to `access_allowed_emails` in
  `terraform.tfvars` and re-run `terraform apply` — no redeploy of the app itself.
- Access enforcement lives entirely at Cloudflare's edge; the backend and frontend
  containers have no awareness of it and stay unauthenticated on localhost/LAN.
