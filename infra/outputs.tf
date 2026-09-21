output "public_hostname" {
  description = "Public hostname exposed through the Cloudflare tunnel"
  value       = local.public_hostname
}

output "tunnel_id" {
  description = "Cloudflare tunnel ID"
  value       = cloudflare_zero_trust_tunnel_cloudflared.fintwit.id
}

output "tunnel_token" {
  description = "Token used by cloudflared to connect to the managed tunnel"
  value       = cloudflare_zero_trust_tunnel_cloudflared.fintwit.tunnel_token
  sensitive   = true
}

output "cloudflared_env_line" {
  description = "Env line to place in your shell or .env for docker compose tunnel profile"
  value       = "CLOUDFLARE_TUNNEL_TOKEN=${cloudflare_zero_trust_tunnel_cloudflared.fintwit.tunnel_token}"
  sensitive   = true
}

output "access_application_id" {
  description = "Cloudflare Access application ID protecting the public hostname"
  value       = cloudflare_zero_trust_access_application.fintwit.id
}

output "access_policy_id" {
  description = "Cloudflare Access policy ID — needed by the app's Admin panel to manage the allowlist at runtime (see CLOUDFLARE_ACCESS_POLICY_ID in .env.example)"
  value       = cloudflare_zero_trust_access_policy.fintwit_allowed_users.id
}
