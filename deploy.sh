#!/bin/bash

# Script de Deploy/Atualização Automática
echo "🔄 Iniciando atualização do Pix Service..."

# 1. Garante que estamos na pasta certa
cd "$(dirname "$0")"

# 2. Atualiza o código do GitHub
echo "📥 Baixando atualizações do GitHub..."
git pull origin main

# 3. Reconstrói e reinicia os containers
echo "🐳 Reiniciando containers Docker..."
docker-compose down
docker-compose up -d --build

# 4. Limpa imagens antigas para economizar espaço
docker image prune -f

echo "✅ Serviço atualizado e rodando!"
echo "📍 Teste em: http://$(curl -s ifconfig.me):8000/gerar-pix"
