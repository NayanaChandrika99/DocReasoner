# TreeStore Deployment Guide

This guide covers deploying TreeStore in various environments.

## Table of Contents

- [Quick Start](#quick-start)
- [Building from Source](#building-from-source)
- [Docker Deployment](#docker-deployment)
- [Full Stack Deployment](#full-stack-deployment)
- [Configuration](#configuration)
- [Monitoring & Observability](#monitoring--observability)
- [Troubleshooting](#troubleshooting)
- [Production Considerations](#production-considerations)

## Quick Start

### Running Locally

```bash
# Build the server
go build -o treestore-server ./cmd/treestore/

# Run with default settings
./treestore-server

# Run with custom configuration
./treestore-server \
  -port 50051 \
  -metrics-port 9090 \
  -db /data/treestore.db \
  -log-level info \
  -log-pretty false
```

### Running with Docker

```bash
# Build Docker image
cd tree_db
docker build -t treestore:latest .

# Run container
docker run -d \
  --name treestore \
  -p 50051:50051 \
  -p 9090:9090 \
  -v treestore_data:/data \
  treestore:latest
```

## Building from Source

### Prerequisites

- Go 1.25.4 or later
- Protocol Buffers compiler (protoc)
- Make (optional)

### Build Steps

```bash
# Clone repository
git clone <repository-url>
cd tree_db

# Install dependencies
go mod download

# Build binary
go build -o treestore-server ./cmd/treestore/

# Verify build
./treestore-server -h
```

### Running Tests

```bash
# Run all tests
go test ./...

# Run with coverage
go test -cover ./...

# Run integration tests
go test -v ./internal/server/...
```

## Docker Deployment

### Building the Image

The Dockerfile uses multi-stage builds for optimal size:

```bash
cd tree_db
docker build -t treestore:latest .
```

### Running the Container

#### Basic Usage

```bash
docker run -d \
  --name treestore \
  -p 50051:50051 \
  -p 9090:9090 \
  treestore:latest
```

#### With Persistent Storage

```bash
docker run -d \
  --name treestore \
  -p 50051:50051 \
  -p 9090:9090 \
  -v $(pwd)/data:/data \
  -e DB_PATH=/data/treestore.db \
  treestore:latest
```

#### With Custom Configuration

```bash
docker run -d \
  --name treestore \
  -p 50051:50051 \
  -p 9090:9090 \
  -e GRPC_PORT=50051 \
  -e METRICS_PORT=9090 \
  -e DB_PATH=/data/treestore.db \
  -e LOG_LEVEL=debug \
  -e LOG_PRETTY=false \
  -v $(pwd)/data:/data \
  treestore:latest
```

## Full Stack Deployment

Deploy TreeStore with the complete Reasoning Service stack:

### Using docker-compose

```bash
# From the reasoning-service root directory
cd /path/to/reasoning-service

# Start all services
docker-compose -f docker-compose.full.yml up -d

# Start with monitoring (Prometheus + Grafana)
docker-compose -f docker-compose.full.yml --profile monitoring up -d

# View logs
docker-compose -f docker-compose.full.yml logs -f treestore

# Stop all services
docker-compose -f docker-compose.full.yml down
```

### Service Architecture

The full stack includes:

| Service | Port | Description |
|---------|------|-------------|
| TreeStore | 50051 | gRPC API |
| TreeStore Metrics | 9090 | Prometheus metrics, health checks |
| Reasoning Service | 8000 | REST API |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Cache |
| Prometheus | 9091 | Metrics collection (optional) |
| Grafana | 3000 | Visualization (optional) |

### Health Checks

```bash
# TreeStore health
curl http://localhost:9090/health

# TreeStore readiness
curl http://localhost:9090/ready

# Reasoning Service health
curl http://localhost:8000/health
```

## Configuration

### Command-Line Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-port` | 50051 | gRPC server port |
| `-metrics-port` | 9090 | HTTP metrics/observability port |
| `-db` | treestore.db | Database file path |
| `-log-level` | info | Log level (debug, info, warn, error) |
| `-log-pretty` | true | Pretty-print logs (disable for production) |

### Environment Variables

When running in Docker:

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | 50051 | gRPC server port |
| `METRICS_PORT` | 9090 | Metrics port |
| `DB_PATH` | /data/treestore.db | Database path |
| `LOG_LEVEL` | info | Logging level |
| `LOG_PRETTY` | false | Pretty-print logs |

### Database Location

The database file location depends on your deployment:

- **Local**: Specify with `-db` flag (e.g., `/var/lib/treestore/db`)
- **Docker**: Mounted volume at `/data/treestore.db`
- **Production**: Use dedicated volume or persistent storage

## Monitoring & Observability

### Prometheus Metrics

TreeStore exposes comprehensive Prometheus metrics at `http://localhost:9090/metrics`:

**gRPC Metrics:**
- `treestore_grpc_requests_total` - Total requests by method and status
- `treestore_grpc_request_duration_seconds` - Request latency histogram
- `treestore_grpc_requests_in_flight` - Current active requests

**Database Metrics:**
- `treestore_db_operations_total` - Database operations counter
- `treestore_db_operation_duration_seconds` - Operation latency
- `treestore_db_size_bytes` - Database size
- `treestore_db_nodes_total` - Total nodes
- `treestore_db_documents_total` - Total documents

**Server Metrics:**
- `treestore_server_uptime_seconds` - Server uptime

### Structured Logging

TreeStore uses zerolog for structured JSON logging:

```json
{
  "level": "info",
  "service": "treestore",
  "component": "grpc",
  "method": "/treestore.TreeStoreService/StoreDocument",
  "duration_ms": 1.2,
  "time": "2025-11-14T10:00:00Z",
  "message": "gRPC request completed"
}
```

### Profiling with pprof

Access Go profiling endpoints at `http://localhost:9090/debug/pprof/`:

```bash
# CPU profile (30 seconds)
go tool pprof http://localhost:9090/debug/pprof/profile?seconds=30

# Heap profile
go tool pprof http://localhost:9090/debug/pprof/heap

# Goroutine profile
curl http://localhost:9090/debug/pprof/goroutine?debug=2

# Interactive profiling
go tool pprof -http=:8080 http://localhost:9090/debug/pprof/heap
```

### Grafana Dashboards

When running with the monitoring profile:

1. Access Grafana at http://localhost:3000
2. Login: admin / admin
3. Browse pre-configured TreeStore dashboard

Key metrics visualized:
- Request rate and latency
- Error rate
- Database size and operations
- Server uptime
- gRPC method breakdown

## Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Check what's using the port
lsof -i :50051
lsof -i :9090

# Kill existing process
kill -9 <PID>

# Or use different ports
./treestore-server -port 50052 -metrics-port 9091
```

#### Database Locked

```bash
# Check for existing connections
lsof | grep treestore.db

# Remove lock file (if server is stopped)
rm treestore.db-wal
rm treestore.db-shm
```

#### Connection Refused

```bash
# Verify server is running
curl http://localhost:9090/health

# Check server logs
docker logs treestore

# Verify firewall rules
sudo iptables -L

# Test connectivity
telnet localhost 50051
```

#### High Memory Usage

```bash
# Analyze heap profile
go tool pprof http://localhost:9090/debug/pprof/heap

# Check goroutine leaks
curl http://localhost:9090/debug/pprof/goroutine?debug=2
```

### Logging

#### Increase Log Level

```bash
# Debug logging
./treestore-server -log-level debug

# Docker
docker run -e LOG_LEVEL=debug treestore:latest
```

#### View Docker Logs

```bash
# Follow logs
docker logs -f treestore

# Last 100 lines
docker logs --tail 100 treestore

# With timestamps
docker logs -t treestore
```

### Performance Diagnostics

```bash
# Check metrics
curl http://localhost:9090/metrics | grep treestore

# CPU profile
go tool pprof -seconds=30 http://localhost:9090/debug/pprof/profile

# Memory profile
go tool pprof http://localhost:9090/debug/pprof/heap

# Block profile (contention)
curl http://localhost:9090/debug/pprof/block?debug=2
```

## Production Considerations

### Security

1. **Run as non-root user** - Already configured in Docker
2. **Network isolation** - Use Docker networks or VPNs
3. **TLS/mTLS** - Add gRPC TLS support (Week 14)
4. **Firewall rules** - Restrict access to gRPC and metrics ports
5. **Secrets management** - Use environment variables or secret managers

### Performance

1. **Resource limits** - Set Docker memory/CPU limits
2. **Database location** - Use fast SSD storage
3. **Connection pooling** - Configure client connection pools
4. **Batch operations** - Use bulk operations when possible

### Reliability

1. **Health checks** - Monitor `/health` endpoint
2. **Backups** - Regular database backups
3. **Restart policies** - Use `restart: unless-stopped` in docker-compose
4. **Graceful shutdown** - Server handles SIGTERM properly

### Monitoring

1. **Metrics collection** - Use Prometheus or similar
2. **Alerting** - Configure alerts on error rates, latency, disk usage
3. **Log aggregation** - Use ELK stack or similar for logs
4. **Distributed tracing** - Add OpenTelemetry support (future)

### Scaling

1. **Horizontal scaling** - Deploy multiple TreeStore instances
2. **Load balancing** - Use gRPC load balancer
3. **Database sharding** - Partition data by document ID (future)
4. **Read replicas** - Add read-only replicas (future)

### Example Production Configuration

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  treestore:
    image: treestore:1.0.0
    container_name: treestore-prod
    ports:
      - "50051:50051"
      - "9090:9090"
    environment:
      - GRPC_PORT=50051
      - METRICS_PORT=9090
      - DB_PATH=/data/treestore.db
      - LOG_LEVEL=info
      - LOG_PRETTY=false
    volumes:
      - /mnt/data/treestore:/data
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:9090/health"]
      interval: 30s
      timeout: 3s
      start_period: 10s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Next Steps

- **Week 14**: WAL implementation for crash recovery and durability
- **Security**: Add TLS/mTLS for gRPC communication
- **Clustering**: Multi-node deployment with consensus
- **Advanced monitoring**: Distributed tracing with OpenTelemetry
