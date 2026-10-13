FROM golang:1.26.5-alpine AS builder

WORKDIR /src

COPY go.mod ./
COPY main.go server.go middleware.go errors.go ./

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/agenyx-gateway .

FROM alpine:3.22

RUN apk --no-cache add ca-certificates \
    && addgroup -S agenyx \
    && adduser -S -G agenyx agenyx

WORKDIR /app

COPY --from=builder /out/agenyx-gateway /app/agenyx-gateway

USER agenyx

EXPOSE 80 443

ENTRYPOINT ["/app/agenyx-gateway"]
