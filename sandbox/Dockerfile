FROM golang:1.26.5-alpine AS builder

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/sandboxd ./cmd/sandboxd

FROM alpine:3.22

RUN apk --no-cache add ca-certificates \
    && addgroup -S sandbox \
    && adduser -S -G sandbox sandbox

WORKDIR /app

COPY --from=builder /out/sandboxd /app/sandboxd

USER sandbox

EXPOSE 9000

ENTRYPOINT ["/app/sandboxd"]
