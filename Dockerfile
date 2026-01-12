# Use uma imagem oficial do Python leve
FROM python:3.11-slim

# Define variáveis de ambiente para evitar arquivos .pyc e buffer de logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema necessárias para o Playwright
# O Playwright precisa de algumas libs do sistema para rodar os browsers
# CURL é necessário para o Healthcheck
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Cria diretório de trabalho
WORKDIR /app

# Copia os requisitos
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Instala os navegadores do Playwright (e suas dependências de sistema)
RUN playwright install --with-deps chromium

# Copia o código da aplicação
COPY . .

# Expõe a porta 8000
EXPOSE 8000

# Comando para iniciar a aplicação usando a variável PORT ou padrão 8000
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
