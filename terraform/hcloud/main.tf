terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

resource "hcloud_ssh_key" "default" {
  name       = "rag-ssh-key"
  public_key = var.public_key
}

# ---------------------------------------------------------------------------
# Firewall : SSH Strict + Web Open
# ---------------------------------------------------------------------------
resource "hcloud_firewall" "rag_firewall" {
  name = "rag-firewall"

  # SSH - Accès restreint via variable (Défaut : 0.0.0.0/0)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.ssh_allowed_ips
  }

  # HTTP/HTTPS - Commenté si pas de reverse proxy (Nginx)
  # rule {
  #   direction = "in"
  #   protocol  = "tcp"
  #   port      = "80"
  #   source_ips = ["0.0.0.0/0", "::/0"]
  # }

  # rule {
  #   direction = "in"
  #   protocol  = "tcp"
  #   port      = "443"
  #   source_ips = ["0.0.0.0/0", "::/0"]
  # }

  # Ports Applicatifs (API + Streamlit)
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "8000"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "8501"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # ICMP (Ping)
  rule {
    direction = "in"
    protocol  = "icmp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# ---------------------------------------------------------------------------
# Serveur avec Cloud-Init
# ---------------------------------------------------------------------------
resource "hcloud_server" "rag_server" {
  name         = "rag-chatbot-prod"
  image        = "ubuntu-22.04"
  server_type  = "cpx42"
  location     = "nbg1"
  ssh_keys     = [hcloud_ssh_key.default.id]
  firewall_ids = [hcloud_firewall.rag_firewall.id]

  user_data = <<-EOT
    #cloud-config
    package_update: true
    package_upgrade: true

    packages:
      - apt-transport-https
      - ca-certificates
      - curl
      - gnupg
      - lsb-release
      - git
      - ufw

    runcmd:
      # 1. Sécurité SSH : Désactivation mot de passe
      - sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
      - sed -i 's/#PasswordAuthentication no/PasswordAuthentication no/' /etc/ssh/sshd_config
      - systemctl restart ssh

      # 2. Installation Docker
      - mkdir -p /etc/apt/keyrings
      - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      - echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
      - apt-get update
      - apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

      # 3. Préparation application
      - mkdir -p /app/uploads
      - chown -R 1000:1000 /app

    final_message: "Le système est prêt après $UPTIME secondes"
  EOT

  labels = {
    project = "rag-chatbot"
    env     = "production"
  }
}
