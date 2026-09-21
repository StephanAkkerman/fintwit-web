variable "cloudflare_api_token" {
  description = "Cloudflare API token with Zone DNS + Zero Trust Tunnel permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "zone_name" {
  description = "Cloudflare zone name (your own domain, delegated to Cloudflare nameservers)"
  type        = string
}

variable "subdomain" {
  description = "Subdomain for the public app hostname"
  type        = string
  default     = "fintwit"
}

variable "tunnel_name" {
  description = "Name for the Cloudflare tunnel"
  type        = string
  default     = "fintwit-pi"
}

variable "tunnel_origin_url" {
  description = "Origin URL cloudflared should route traffic to"
  type        = string
  default     = "http://frontend:80"
}

variable "access_allowed_emails" {
  description = "Email addresses allowed to log in via Cloudflare Access (one-time PIN)"
  type        = list(string)
}

variable "access_session_duration" {
  description = "How long an Access login stays valid before re-authenticating"
  type        = string
  default     = "24h"
}
