# TreeStore Server Dockerfile
# Multi-stage build for optimal image size

# Stage 1: Build the Go binary
FROM golang:1.25.4-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git gcc musl-dev

# Set working directory
WORKDIR /build

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the server binary
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo \
    -ldflags="-w -s" \
    -o treestore-server \
    ./cmd/treestore/

# Stage 2: Create minimal runtime image
FROM alpine:3.21

# Install runtime dependencies
RUN apk add --no-cache ca-certificates tzdata

# Create non-root user
RUN addgroup -g 1000 treestore && \
    adduser -D -u 1000 -G treestore treestore

# Set working directory
WORKDIR /app

# Copy binary from builder
COPY --from=builder /build/treestore-server .

# Create data directory
RUN mkdir -p /data && chown -R treestore:treestore /data

# Switch to non-root user
USER treestore

# Expose ports
EXPOSE 50051 9090

# Set default environment variables
ENV GRPC_PORT=50051 \
    METRICS_PORT=9090 \
    DB_PATH=/data/treestore.db \
    LOG_LEVEL=info \
    LOG_PRETTY=false

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:${METRICS_PORT}/health || exit 1

# Run the server
CMD ["sh", "-c", "./treestore-server -port ${GRPC_PORT} -metrics-port ${METRICS_PORT} -db ${DB_PATH} -log-level ${LOG_LEVEL} -log-pretty ${LOG_PRETTY}"]
