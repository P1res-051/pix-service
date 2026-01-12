terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0.1"
    }
  }
}

provider "docker" {
  host = "ssh://root@178.18.247.84:22" # Substitua pelo IP/Usuário correto se necessário
  # Requer chave SSH configurada no agente local (ssh-add)
}

resource "docker_image" "pix_service" {
  name = "pix-service:latest"
  build {
    context = "."
  }
}

resource "docker_container" "pix_service" {
  name  = "pix-service"
  image = docker_image.pix_service.image_id
  restart = "always"
  
  ports {
    internal = 8000
    external = 8000
  }

  env = [
    "PORT=8000",
    "MAX_WORKERS=4"
  ]

  volumes {
    host_path      = "/root/pix-service/debug"
    container_path = "/app/debug"
  }
  
  # Limites de recursos (simulando o deploy do docker-compose)
  memory = 1536 # MB
  cpu_shares = 1024
}

resource "docker_container" "dozzle" {
  name  = "dozzle"
  image = "amir20/dozzle:latest"
  restart = "always"
  
  ports {
    internal = 8080
    external = 8888
  }

  volumes {
    host_path      = "/var/run/docker.sock"
    container_path = "/var/run/docker.sock"
  }
}
