FROM golang:1.26.5-alpine AS builder

WORKDIR /src

# Download Go dependencies.
COPY go.mod go.sum ./
RUN go mod download

# Copy the Go application, internal packages, and recipe assets.
COPY cmd/ ./cmd/
COPY internal/ ./internal/
COPY recipe/ ./recipe/
COPY recipes/ ./recipes/

# Build the application entry point.
RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/agenyx \
    ./cmd/agenyx

# Runtime image.
FROM alpine:3.22

RUN apk --no-cache add ca-certificates \
    && addgroup -S agenyx \
    && adduser -S -G agenyx agenyx

WORKDIR /app

COPY --from=builder /out/agenyx /app/agenyx
COPY --from=builder /src/recipes /app/recipes

USER agenyx

EXPOSE 80 443

ENTRYPOINT ["/app/agenyx"]
