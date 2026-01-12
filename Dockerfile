# Stage 1: Build Go Binary and Driver
FROM golang:1.22 AS builder
WORKDIR /app

# Copy source
COPY . .

# Initialize Module and Build
# If go.sum doesn't exist, tidy will create it
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o pix-service main.go

# Install Playwright CLI tool
RUN go install github.com/playwright-community/playwright-go/cmd/playwright@latest

# Stage 2: Final Image
FROM ubuntu:jammy

WORKDIR /app

# Install basic tools required for the installer
RUN apt-get update && apt-get install -y ca-certificates tzdata curl wget gnupg && rm -rf /var/lib/apt/lists/*

# Copy Binary and Playwright CLI from builder
COPY --from=builder /app/pix-service .
COPY --from=builder /go/bin/playwright /usr/local/bin/playwright

# Install Browsers and System Dependencies
# This command installs the driver, the browsers, and the OS dependencies (apt-get)
RUN playwright install --with-deps chromium

# Expose Port
ENV PORT=8000
EXPOSE 8000

# Run
CMD ["./pix-service"]
