# Stage 1: Build Go Binary
FROM golang:1.22 AS builder
WORKDIR /app

# Otimização de Cache: Copia arquivos de dependência primeiro
COPY go.mod go.sum* ./
RUN go mod download

# Copia o código fonte e compila
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o pix-service main.go

# Stage 2: Final Image (Usando imagem oficial do Playwright para economizar tempo)
# Essa imagem já vem com os navegadores e dependências instaladas!
FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app

# Instala apenas ferramentas básicas de sistema
RUN apt-get update && apt-get install -y \
    ca-certificates \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia o binário compilado do Stage 1
COPY --from=builder /app/pix-service .

# Playwright driver installation (necessário para o binding Go)
# A imagem já tem os browsers, mas precisamos do driver do Go
COPY --from=builder /go/pkg/mod/github.com/playwright-community/playwright-go* /go/pkg/mod/github.com/playwright-community/playwright-go*
# Ou instalamos o driver novamente (rápido)
RUN apt-get update && apt-get install -y wget && \
    wget https://github.com/playwright-community/playwright-go/releases/download/v0.4101.1/playwright-driver-linux-amd64.tar.gz && \
    tar -xvf playwright-driver-linux-amd64.tar.gz -C /usr/local/bin && \
    rm playwright-driver-linux-amd64.tar.gz

# Define variáveis de ambiente para o Playwright encontrar os browsers da imagem
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Expose Port
ENV PORT=8000
EXPOSE 8000

# Run
CMD ["./pix-service"]