terraform {
  required_version = ">= 1.5.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

locals {
  public_hostname = "${var.subdomain}.${var.zone_name}"
}

data "cloudflare_zone" "zone" {
  name = var.zone_name
}

resource "random_bytes" "tunnel_secret" {
  length = 32
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "fintwit" {
  account_id = var.cloudflare_account_id
  name       = var.tunnel_name
  secret     = random_bytes.tunnel_secret.base64
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "fintwit" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.fintwit.id

  config {
    ingress_rule {
      hostname = local.public_hostname
      service  = var.tunnel_origin_url
    }

    ingress_rule {
      service = "http_status:404"
    }
  }
}

resource "cloudflare_record" "fintwit" {
  zone_id = data.cloudflare_zone.zone.id
  name    = var.subdomain
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.fintwit.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
}

# Gates the public hostname behind Cloudflare Access so the tunnel above isn't
# open to anyone who finds the URL. Login is Cloudflare's hosted one-time-PIN
# screen (email code, no separate identity provider needed) — allowed
# addresses are listed in var.access_allowed_emails.
resource "cloudflare_zero_trust_access_application" "fintwit" {
  account_id       = var.cloudflare_account_id
  name             = "fintwit-web"
  domain           = local.public_hostname
  type             = "self_hosted"
  session_duration = var.access_session_duration
}

resource "cloudflare_zero_trust_access_policy" "fintwit_allowed_users" {
  account_id     = var.cloudflare_account_id
  application_id = cloudflare_zero_trust_access_application.fintwit.id
  name           = "Allowed users"
  precedence     = 1
  decision       = "allow"

  include {
    email = var.access_allowed_emails
  }

  # The app's Admin > Access panel edits this policy's allowlist directly
  # through the Cloudflare API (see app/services/cloudflare_access.py) so
  # you can invite friends without a Terraform run. Once that happens this
  # policy's `include` no longer matches access_allowed_emails, and without
  # `ignore_changes` the next `terraform apply` would silently revert
  # whoever was added at runtime. access_allowed_emails still seeds the
  # policy on first apply.
  lifecycle {
    ignore_changes = [include]
  }
}
