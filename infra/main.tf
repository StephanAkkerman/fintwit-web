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
