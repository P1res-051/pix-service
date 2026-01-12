#!/bin/bash
echo "🚀 Testando API Pix Service..."

# Aguarda um pouco para garantir que o serviço subiu
echo "⏳ Aguardando serviço iniciar completamente..."
sleep 5

# Verifica se o container está rodando
if ! docker ps | grep -q pix-service; then
    echo "❌ O container 'pix-service' não está rodando!"
    echo "📜 Logs recentes:"
    docker logs --tail 20 pix-service
    exit 1
fi

# Teste 1: Health Check
echo "1. Verificando Saúde da API (/health)..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$HEALTH" == "200" ]; then
    echo "✅ API Online (HTTP 200)"
else
    echo "❌ API Offline ou com erro (HTTP $HEALTH)"
    echo "📜 Logs do container:"
    docker logs --tail 50 pix-service
    exit 1
fi

# Teste 2: Gerar Pix (Link Real)
echo "2. Testando Geração de Pix..."
echo "   - Link: https://pagueaqui.top/Y2xpZW50XzIyNjc0NA=="
echo "   - Aguardando resposta..."

RESPONSE=$(curl -s -X POST http://localhost:8000/gerar-pix \
  -H "Content-Type: application/json" \
  -d '{
    "link": "https://pagueaqui.top/Y2xpZW50XzIyNjc0NA==",
    "email": "teste@email.com"
  }')

echo "📄 Resposta:"
echo "$RESPONSE"

if echo "$RESPONSE" | grep -q "success\":true"; then
    echo "✅ SUCESSO! Pix gerado corretamente."
else
    echo "⚠️ FALHA ou PIX NÃO ENCONTRADO."
    echo "   - Verifique se o link ainda é válido."
fi

