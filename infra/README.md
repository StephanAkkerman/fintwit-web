# Cloudflare IaC (Terraform)

This folder provisions Cloudflare DNS and a managed cloudflared tunnel for
serving fintwit-web from your Raspberry Pi.

## Resources Created

- Cloudflare tunnel (`cloudflare_zero_trust_tunnel_cloudflared`)
- Tunnel ingress config (`cloudflare_zero_trust_tunnel_cloudflared_config`)
- DNS CNAME record: `<subdomain>.<zone_name>` -> `<tunnel-id>.cfargotunnel.com`

## Prerequisites

- Domain delegated to Cloudflare nameservers
- Cloudflare API token with:
  - Account: Cloudflare Tunnel Edit
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
5. Start app + tunnel from repo root:
   - `docker compose up -d --build`
   - `CLOUDFLARE_TUNNEL_TOKEN=<token> docker compose --profile tunnel up -d`

## Notes

- By default this config assumes cloudflared runs as a Compose service and routes to
  `http://frontend:80`.
- If you run cloudflared directly on the host instead of Compose, set
  `tunnel_origin_url = "http://localhost:3000"`.
