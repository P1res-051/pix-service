#!/bin/bash

# Script de Deploy/Atualização Automática
echo "🔄 Iniciando atualização do Pix Service..."

# 1. Garante que estamos na pasta certa
cd "$(dirname "$0")"

# 2. Atualiza o código do GitHub
echo "📥 Baixando atualizações do GitHub..."
git fetch origin
git reset --hard origin/main

# 3. Verifica qual Docker Compose usar (V2 é preferido)
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

echo "✅ Serviço atualizado e rodando!"
echo "📍 Teste em: http://$(curl -4 -s ifconfig.me):8000/gerar-pix"
