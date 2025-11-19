// Observability middleware and HTTP server for metrics and profiling
package server

import (
	"context"
	"fmt"
	"net/http"
	"net/http/pprof"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"google.golang.org/grpc"

	"github.com/nainya/treestore/internal/logger"
	"github.com/nainya/treestore/internal/metrics"
)

// GrpcMetricsInterceptor creates a gRPC interceptor for metrics and logging
func GrpcMetricsInterceptor(m *metrics.Metrics, log *logger.Logger) grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req interface{},
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (interface{}, error) {
		start := time.Now()
		m.GrpcRequestsInFlight.Inc()
		defer m.GrpcRequestsInFlight.Dec()

		// Call the handler
		resp, err := handler(ctx, req)

		// Record metrics
		duration := time.Since(start)
		status := "success"
		if err != nil {
			status = "error"
		}

		m.RecordGrpcRequest(info.FullMethod, status, duration)

		// Log request
		log.LogGrpcRequest(info.FullMethod, duration, err)

		return resp, err
	}
}

// ObservabilityServer provides HTTP endpoints for metrics and profiling
type ObservabilityServer struct {
	server *http.Server
	log    *logger.Logger
}

// NewObservabilityServer creates a new HTTP server for observability
func NewObservabilityServer(port int, log *logger.Logger) *ObservabilityServer {
	mux := http.NewServeMux()

	// Prometheus metrics endpoint
	mux.Handle("/metrics", promhttp.Handler())

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"healthy","service":"treestore"}`))
	})

	// Readiness check endpoint
	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ready"}`))
	})

	// pprof endpoints for profiling
	mux.HandleFunc("/debug/pprof/", pprof.Index)
	mux.HandleFunc("/debug/pprof/cmdline", pprof.Cmdline)
	mux.HandleFunc("/debug/pprof/profile", pprof.Profile)
	mux.HandleFunc("/debug/pprof/symbol", pprof.Symbol)
	mux.HandleFunc("/debug/pprof/trace", pprof.Trace)
	mux.Handle("/debug/pprof/heap", pprof.Handler("heap"))
	mux.Handle("/debug/pprof/goroutine", pprof.Handler("goroutine"))
	mux.Handle("/debug/pprof/threadcreate", pprof.Handler("threadcreate"))
	mux.Handle("/debug/pprof/block", pprof.Handler("block"))
	mux.Handle("/debug/pprof/mutex", pprof.Handler("mutex"))
	mux.Handle("/debug/pprof/allocs", pprof.Handler("allocs"))

	server := &http.Server{
		Addr:         fmt.Sprintf(":%d", port),
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	return &ObservabilityServer{
		server: server,
		log:    log,
	}
}

// Start starts the observability HTTP server
func (o *ObservabilityServer) Start() error {
	o.log.Info("Starting observability server").
		Str("addr", o.server.Addr).
		Msg("Observability endpoints available")

	o.log.Info("Endpoints:").
		Str("metrics", fmt.Sprintf("http://%s/metrics", o.server.Addr)).
		Str("health", fmt.Sprintf("http://%s/health", o.server.Addr)).
		Str("pprof", fmt.Sprintf("http://%s/debug/pprof/", o.server.Addr)).
		Send()

	if err := o.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("observability server failed: %w", err)
	}

	return nil
}

// Shutdown gracefully shuts down the observability server
func (o *ObservabilityServer) Shutdown(ctx context.Context) error {
	o.log.Info("Shutting down observability server").Send()
	return o.server.Shutdown(ctx)
}
