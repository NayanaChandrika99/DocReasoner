// TreeStore gRPC Server
// Provides remote access to hierarchical document storage
package main

import (
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	"github.com/nainya/treestore/internal/server"
	pb "github.com/nainya/treestore/proto"
)

var (
	port   = flag.Int("port", 50051, "The server port")
	dbPath = flag.String("db", "treestore.db", "Database file path")
)

func main() {
	flag.Parse()

	log.Printf("TreeStore gRPC Server v1.0.0")
	log.Printf("Database: %s", *dbPath)
	log.Printf("Port: %d", *port)

	// Create gRPC server
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", *port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	// Initialize TreeStore server
	treeStoreServer, err := server.NewServer(*dbPath)
	if err != nil {
		log.Fatalf("Failed to create server: %v", err)
	}
	defer treeStoreServer.Close()

	// Create gRPC server with options
	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(100 * 1024 * 1024), // 100 MB
		grpc.MaxSendMsgSize(100 * 1024 * 1024), // 100 MB
	)

	// Register service
	pb.RegisterTreeStoreServiceServer(grpcServer, treeStoreServer)

	// Register reflection service for grpcurl/grpcui
	reflection.Register(grpcServer)

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	go func() {
		<-sigChan
		log.Println("Shutting down gracefully...")
		grpcServer.GracefulStop()
	}()

	// Start server
	log.Printf("Server listening on :%d", *port)
	log.Printf("Ready to accept connections...")
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
