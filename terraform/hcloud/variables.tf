variable "hcloud_token" {
  description = "Hetzner Cloud API Token"
  type        = string
  sensitive   = true
}

variable "public_key" {
  description = "Public SSH key for the server"
  type        = string
}

variable "ssh_allowed_ips" {
  description = "List of IP addresses allowed to connect via SSH"
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
}
