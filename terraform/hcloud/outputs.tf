output "server_ip" {
  value       = hcloud_server.rag_server.ipv4_address
  description = "Public IP address of the RAG server"
}

output "server_status" {
  value = hcloud_server.rag_server.status
}
