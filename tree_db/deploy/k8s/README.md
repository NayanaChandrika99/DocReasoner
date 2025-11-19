# TreeStore Kubernetes Deployment

This directory contains Kubernetes manifests for deploying TreeStore in a production environment.

## Prerequisites

- Kubernetes cluster (1.20+)
- kubectl configured
- Docker image built and pushed to registry
- Persistent storage provisioner

## Quick Deploy

```bash
# Apply all manifests
kubectl apply -k .

# Or apply individually
kubectl apply -f namespace.yaml
kubectl apply -f pvc.yaml
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

## Verify Deployment

```bash
# Check pod status
kubectl get pods -n treestore

# Check service
kubectl get svc -n treestore

# View logs
kubectl logs -f -n treestore deployment/treestore

# Check health
kubectl port-forward -n treestore svc/treestore 9090:9090
curl http://localhost:9090/health
```

## Configuration

### ConfigMap

Edit `configmap.yaml` to adjust settings:
- `GRPC_PORT`: gRPC server port (default: 50051)
- `METRICS_PORT`: Metrics/observability port (default: 9090)
- `DB_PATH`: Database file path (default: /data/treestore.db)
- `LOG_LEVEL`: Logging level (default: info)
- `LOG_PRETTY`: Pretty-print logs (default: false)

### Resources

Edit `deployment.yaml` to adjust resource requests/limits:
```yaml
resources:
  requests:
    cpu: 500m      # Increase for higher load
    memory: 512Mi  # Increase for larger datasets
  limits:
    cpu: 2000m
    memory: 2Gi
```

### Storage

Edit `pvc.yaml` to adjust storage size:
```yaml
resources:
  requests:
    storage: 10Gi  # Increase based on data size
```

## Accessing TreeStore

### From within the cluster

Use the service DNS name:
```
treestore.treestore.svc.cluster.local:50051
```

### From outside the cluster

Create a NodePort or LoadBalancer service, or use port-forwarding:

```bash
# Port forward gRPC
kubectl port-forward -n treestore svc/treestore 50051:50051

# Port forward metrics
kubectl port-forward -n treestore svc/treestore 9090:9090
```

## Monitoring

TreeStore exposes Prometheus metrics on port 9090:

```bash
# Access metrics
kubectl port-forward -n treestore svc/treestore 9090:9090
curl http://localhost:9090/metrics
```

### ServiceMonitor (for Prometheus Operator)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: treestore
  namespace: treestore
spec:
  selector:
    matchLabels:
      app: treestore
  endpoints:
  - port: metrics
    interval: 30s
```

## Scaling Considerations

**IMPORTANT**: TreeStore currently supports only 1 replica due to:
- No WAL implementation (crash recovery not implemented)
- No distributed locking
- Copy-on-write without coordination

The deployment uses `strategy: Recreate` to ensure only one pod runs at a time.

**Future improvements needed for HA:**
- Implement WAL (Week 14)
- Add distributed locking (Raft/etcd)
- Implement read replicas
- Use StatefulSet instead of Deployment

## Troubleshooting

### Pod won't start

```bash
# Check events
kubectl describe pod -n treestore -l app=treestore

# Check PVC
kubectl get pvc -n treestore

# Check logs
kubectl logs -n treestore -l app=treestore
```

### Database corruption

```bash
# Backup current database
kubectl exec -n treestore deployment/treestore -- cp /data/treestore.db /data/treestore.db.backup

# Restore from backup
kubectl exec -n treestore deployment/treestore -- cp /data/treestore.db.backup /data/treestore.db

# Or delete PVC and start fresh (DATA LOSS!)
kubectl delete pvc -n treestore treestore-data
```

### Performance issues

```bash
# Check resource usage
kubectl top pods -n treestore

# Increase resources in deployment.yaml
# Restart deployment
kubectl rollout restart -n treestore deployment/treestore
```

## Cleanup

```bash
# Delete all resources
kubectl delete -k .

# Or delete namespace (deletes everything)
kubectl delete namespace treestore
```

**WARNING**: Deleting the PVC will delete all data!
