// TreeStore gRPC Server with Observability
// Provides remote access to hierarchical document storage
package main

import (
	"context"
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	"github.com/nainya/treestore/internal/logger"
	"github.com/nainya/treestore/internal/metrics"
	"github.com/nainya/treestore/internal/server"
	pb "github.com/nainya/treestore/proto"
)

var (
	grpcPort       = flag.Int("port", 50051, "The gRPC server port")
	metricsPort    = flag.Int("metrics-port", 9090, "The metrics/observability HTTP port")
	dbPath         = flag.String("db", "treestore.db", "Database file path")
	logLevel       = flag.String("log-level", "info", "Log level (debug, info, warn, error)")
	logPretty      = flag.Bool("log-pretty", true, "Pretty-print logs (disable for production)")
	enableProfiling = flag.Bool("enable-profiling", true, "Enable pprof profiling endpoints")
)

func main() {
	flag.Parse()

	// Initialize structured logger
	logger.InitGlobalLogger(logger.Config{
		Level:      *logLevel,
		Pretty:     *logPretty,
		WithCaller: false,
	})
	log := logger.GetGlobalLogger()

	log.Info("TreeStore gRPC Server v1.0.0").
		Str("database", *dbPath).
		Int("grpc_port", *grpcPort).
		Int("metrics_port", *metricsPort).
		Msg("Starting TreeStore")

	// Initialize Prometheus metrics
	m := metrics.NewMetrics()
	log.Info("Prometheus metrics initialized").Send()

	// Create gRPC listener
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", *grpcPort))
	if err != nil {
		log.Fatal("Failed to create gRPC listener").Err(err).Send()
	}

	// Initialize TreeStore server
	log.Info("Initializing TreeStore database").Str("path", *dbPath).Send()
	treeStoreServer, err := server.NewServer(*dbPath)
	if err != nil {
		log.Fatal("Failed to create TreeStore server").Err(err).Send()
	}
	defer treeStoreServer.Close()

	// Create gRPC server with interceptors
	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(100*1024*1024), // 100 MB
		grpc.MaxSendMsgSize(100*1024*1024), // 100 MB
		grpc.UnaryInterceptor(server.GrpcMetricsInterceptor(m, log)),
	)

	// Register service
	pb.RegisterTreeStoreServiceServer(grpcServer, treeStoreServer)

	// Register reflection service for grpcurl/grpcui
	reflection.Register(grpcServer)
	log.Info("gRPC reflection enabled").Send()

	// Start observability HTTP server (metrics + pprof)
	obsServer := server.NewObservabilityServer(*metricsPort, log)
	go func() {
		if err := obsServer.Start(); err != nil {
			log.Error("Observability server failed").Err(err).Send()
		}
	}()

	// Wait a moment for HTTP server to start
	time.Sleep(100 * time.Millisecond)

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	go func() {
		<-sigChan
		log.Info("Received shutdown signal").Send()
		log.LogServerShutdown()

		// Graceful shutdown
		log.Info("Stopping gRPC server...").Send()
		grpcServer.GracefulStop()

		// Shutdown observability server
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := obsServer.Shutdown(ctx); err != nil {
			log.Error("Failed to shutdown observability server").Err(err).Send()
		}
	}()

	// Start gRPC server
	log.LogServerStart(*grpcPort, *dbPath)
	log.Info("gRPC server starting").Int("port", *grpcPort).Send()
	log.LogServerReady(*grpcPort)

	log.Info("TreeStore server ready to accept connections").
		Int("grpc_port", *grpcPort).
		Int("metrics_port", *metricsPort).
		Str("metrics_endpoint", fmt.Sprintf("http://localhost:%d/metrics", *metricsPort)).
		Str("health_endpoint", fmt.Sprintf("http://localhost:%d/health", *metricsPort)).
		Str("pprof_endpoint", fmt.Sprintf("http://localhost:%d/debug/pprof/", *metricsPort)).
		Msg("Server ready")

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatal("Failed to serve gRPC").Err(err).Send()
	}

	log.Info("TreeStore server stopped").Send()
}
