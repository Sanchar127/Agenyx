FROM golang:1.26.5-alpine AS builder

WORKDIR /src

# Go module dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy all root-level Go source files, including:
# main.go, server.go, middleware.go, errors.go,
# authorization.go, and trusted_proxy.go
COPY *.go ./

# Shared recipe loader and gateway recipes
COPY recipe/ ./recipe/
COPY recipes/ ./recipes/

# Build the gateway binary
RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/agenyx-gateway .

# Runtime image
FROM alpine:3.22

# Install CA certificates and create a non-root user
RUN apk --no-cache add ca-certificates \
    && addgroup -S agenyx \
    && adduser -S -G agenyx agenyx

WORKDIR /app

# Copy the compiled gateway binary
COPY --from=builder /out/agenyx-gateway /app/agenyx-gateway

# Copy gateway recipes
COPY --from=builder /src/recipes /app/recipes

# Run as a non-root user
USER agenyx

# Expose HTTP and HTTPS ports
EXPOSE 80 443

# Start the gateway
ENTRYPOINT ["/app/agenyx-gateway"]
