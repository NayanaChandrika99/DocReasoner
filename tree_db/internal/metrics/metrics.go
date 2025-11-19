// Package metrics provides Prometheus metrics for TreeStore
package metrics

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Metrics holds all Prometheus metrics for TreeStore
type Metrics struct {
	// gRPC request metrics
	GrpcRequestsTotal   *prometheus.CounterVec
	GrpcRequestDuration *prometheus.HistogramVec
	GrpcRequestsInFlight prometheus.Gauge

	// Database metrics
	DbOperationsTotal   *prometheus.CounterVec
	DbOperationDuration *prometheus.HistogramVec
	DbSizeBytes         prometheus.Gauge
	DbNodesTotal        prometheus.Gauge
	DbDocumentsTotal    prometheus.Gauge

	// Node operation metrics
	NodeRetrievalsTotal  prometheus.Counter
	NodeStoragesTotal    prometheus.Counter
	SearchQueriesTotal   prometheus.Counter
	SearchResultsTotal   prometheus.Counter
	SubtreeQueriesTotal  prometheus.Counter

	// Version metrics
	VersionQueriesTotal prometheus.Counter
	TemporalLookupsTotal prometheus.Counter

	// Server metrics
	ServerUptimeSeconds prometheus.Gauge
	ServerStartTime     time.Time
}

// NewMetrics creates and registers all Prometheus metrics
func NewMetrics() *Metrics {
	m := &Metrics{
		ServerStartTime: time.Now(),
	}

	// gRPC request metrics
	m.GrpcRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "treestore_grpc_requests_total",
			Help: "Total number of gRPC requests",
		},
		[]string{"method", "status"},
	)

	m.GrpcRequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "treestore_grpc_request_duration_seconds",
			Help:    "Duration of gRPC requests in seconds",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"method"},
	)

	m.GrpcRequestsInFlight = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "treestore_grpc_requests_in_flight",
			Help: "Number of gRPC requests currently being processed",
		},
	)

	// Database metrics
	m.DbOperationsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "treestore_db_operations_total",
			Help: "Total number of database operations",
		},
		[]string{"operation", "status"},
	)

	m.DbOperationDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "treestore_db_operation_duration_seconds",
			Help:    "Duration of database operations in seconds",
			Buckets: []float64{.001, .005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10},
		},
		[]string{"operation"},
	)

	m.DbSizeBytes = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "treestore_db_size_bytes",
			Help: "Current database size in bytes",
		},
	)

	m.DbNodesTotal = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "treestore_db_nodes_total",
			Help: "Total number of nodes in database",
		},
	)

	m.DbDocumentsTotal = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "treestore_db_documents_total",
			Help: "Total number of documents in database",
		},
	)

	// Node operation metrics
	m.NodeRetrievalsTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "treestore_node_retrievals_total",
			Help: "Total number of node retrievals",
		},
	)

	m.NodeStoragesTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "treestore_node_storages_total",
			Help: "Total number of node storage operations",
		},
	)

	m.SearchQueriesTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "treestore_search_queries_total",
			Help: "Total number of search queries",
		},
	)

	m.SearchResultsTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "treestore_search_results_total",
			Help: "Total number of search results returned",
		},
	)

	m.SubtreeQueriesTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "treestore_subtree_queries_total",
			Help: "Total number of subtree queries",
		},
	)

	// Version metrics
	m.VersionQueriesTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "treestore_version_queries_total",
			Help: "Total number of version queries",
		},
	)

	m.TemporalLookupsTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "treestore_temporal_lookups_total",
			Help: "Total number of temporal (point-in-time) queries",
		},
	)

	// Server metrics
	m.ServerUptimeSeconds = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "treestore_server_uptime_seconds",
			Help: "Server uptime in seconds",
		},
	)

	// Start uptime updater
	go m.updateUptime()

	return m
}

// updateUptime periodically updates the server uptime metric
func (m *Metrics) updateUptime() {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		m.ServerUptimeSeconds.Set(time.Since(m.ServerStartTime).Seconds())
	}
}

// RecordGrpcRequest records a gRPC request with its status
func (m *Metrics) RecordGrpcRequest(method string, status string, duration time.Duration) {
	m.GrpcRequestsTotal.WithLabelValues(method, status).Inc()
	m.GrpcRequestDuration.WithLabelValues(method).Observe(duration.Seconds())
}

// RecordDbOperation records a database operation
func (m *Metrics) RecordDbOperation(operation string, status string, duration time.Duration) {
	m.DbOperationsTotal.WithLabelValues(operation, status).Inc()
	m.DbOperationDuration.WithLabelValues(operation).Observe(duration.Seconds())
}

// UpdateDbStats updates database statistics
func (m *Metrics) UpdateDbStats(sizeBytes int64, nodeCount int64, docCount int64) {
	m.DbSizeBytes.Set(float64(sizeBytes))
	m.DbNodesTotal.Set(float64(nodeCount))
	m.DbDocumentsTotal.Set(float64(docCount))
}
