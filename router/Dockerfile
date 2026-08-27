FROM golang:1.26-alpine AS builder

WORKDIR /build

COPY go.mod ./

RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build \
    -o /router \
    ./cmd/router


FROM alpine:3.22

RUN apk add --no-cache ca-certificates \
    && addgroup -S -g 10001 router \
    && adduser -S -D -u 10001 -G router router

COPY --from=builder /router /router

USER 10001

EXPOSE 8005

ENTRYPOINT ["/router"]
