#!/bin/bash

# Script de Deploy/Atualização Automática
echo "🔄 Iniciando atualização do Pix Service..."

# 1. Garante que estamos na pasta certa
cd "$(dirname "$0")"

# 2. Atualiza o código do GitHub
echo "📥 Baixando atualizações do GitHub..."
git fetch origin
git reset --hard origin/main

# 3. Verifica qual Docker Compose usar (V2 é preferido) e instala se necessário
if ! docker compose version >/dev/null 2>&1; then
    echo "⚠️ Docker Compose V2 não encontrado. Tentando instalar plugin..."
    mkdir -p ~/.docker/cli-plugins/
    curl -SL https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose
    chmod +x ~/.docker/cli-plugins/docker-compose
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
    echo "✅ Usando Docker Compose V2"
else
    COMPOSE="docker-compose"
    echo "⚠️ Usando Docker Compose Legacy (V1)"
fi

# 4. Limpeza forçada para evitar erros de "ContainerConfig"
echo "🧹 Limpando containers antigos..."
docker rm -f pix-service 2>/dev/null
$COMPOSE down --remove-orphans

# 5. Reconstrói e reinicia
echo "🐳 Construindo e iniciando..."
$COMPOSE up -d --build

# 6. Limpa imagens não utilizadas
docker image prune -f

# 7. Configura Firewall (UFW) se disponível para liberar portas
if command -v ufw >/dev/null 2>&1; then
    echo "🛡️ Configurando Firewall (liberando portas 8000, 8888, 3001)..."
    ufw allow 8000/tcp
    ufw allow 8888/tcp
    ufw allow 3001/tcp
    echo "✅ Portas liberadas."
fi

echo "✅ Serviço atualizado e rodando!"
echo "📍 Teste em: http://$(curl -4 -s ifconfig.me):8000/gerar-pix"
