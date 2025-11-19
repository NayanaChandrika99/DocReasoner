// Package logger provides structured logging for TreeStore
package logger

import (
	"io"
	"os"
	"time"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

// Logger wraps zerolog with TreeStore-specific functionality
type Logger struct {
	zlog zerolog.Logger
}

// Config holds logger configuration
type Config struct {
	Level      string // debug, info, warn, error
	Pretty     bool   // pretty-print for development
	Output     io.Writer
	WithCaller bool
}

// NewLogger creates a new structured logger
func NewLogger(cfg Config) *Logger {
	// Set global log level
	level := zerolog.InfoLevel
	switch cfg.Level {
	case "debug":
		level = zerolog.DebugLevel
	case "info":
		level = zerolog.InfoLevel
	case "warn":
		level = zerolog.WarnLevel
	case "error":
		level = zerolog.ErrorLevel
	}
	zerolog.SetGlobalLevel(level)

	// Configure output
	output := cfg.Output
	if output == nil {
		output = os.Stdout
	}

	// Pretty printing for development
	if cfg.Pretty {
		output = zerolog.ConsoleWriter{
			Out:        output,
			TimeFormat: time.RFC3339,
		}
	}

	// Create logger
	zlog := zerolog.New(output).
		With().
		Timestamp().
		Str("service", "treestore").
		Logger()

	// Add caller information if requested
	if cfg.WithCaller {
		zlog = zlog.With().Caller().Logger()
	}

	return &Logger{zlog: zlog}
}

// GetZerolog returns the underlying zerolog logger
func (l *Logger) GetZerolog() *zerolog.Logger {
	return &l.zlog
}

// Info logs an info message
func (l *Logger) Info(msg string) *zerolog.Event {
	return l.zlog.Info().Str("msg", msg)
}

// Debug logs a debug message
func (l *Logger) Debug(msg string) *zerolog.Event {
	return l.zlog.Debug().Str("msg", msg)
}

// Warn logs a warning message
func (l *Logger) Warn(msg string) *zerolog.Event {
	return l.zlog.Warn().Str("msg", msg)
}

// Error logs an error message
func (l *Logger) Error(msg string) *zerolog.Event {
	return l.zlog.Error().Str("msg", msg)
}

// Fatal logs a fatal message and exits
func (l *Logger) Fatal(msg string) *zerolog.Event {
	return l.zlog.Fatal().Str("msg", msg)
}

// WithFields returns a logger with additional fields
func (l *Logger) WithFields(fields map[string]interface{}) *Logger {
	ctx := l.zlog.With()
	for k, v := range fields {
		ctx = ctx.Interface(k, v)
	}
	return &Logger{zlog: ctx.Logger()}
}

// GrpcLogger returns a logger for gRPC operations
func (l *Logger) GrpcLogger(method string) *Logger {
	return &Logger{
		zlog: l.zlog.With().
			Str("component", "grpc").
			Str("method", method).
			Logger(),
	}
}

// DbLogger returns a logger for database operations
func (l *Logger) DbLogger(operation string) *Logger {
	return &Logger{
		zlog: l.zlog.With().
			Str("component", "database").
			Str("operation", operation).
			Logger(),
	}
}

// RequestLogger logs gRPC request with structured fields
func (l *Logger) LogGrpcRequest(method string, duration time.Duration, err error) {
	event := l.zlog.Info().
		Str("component", "grpc").
		Str("method", method).
		Dur("duration_ms", duration)

	if err != nil {
		event = l.zlog.Error().
			Str("component", "grpc").
			Str("method", method).
			Dur("duration_ms", duration).
			Err(err)
	}

	event.Msg("gRPC request completed")
}

// LogDbOperation logs database operation with structured fields
func (l *Logger) LogDbOperation(operation string, duration time.Duration, recordCount int, err error) {
	event := l.zlog.Debug().
		Str("component", "database").
		Str("operation", operation).
		Dur("duration_ms", duration).
		Int("record_count", recordCount)

	if err != nil {
		event = l.zlog.Error().
			Str("component", "database").
			Str("operation", operation).
			Dur("duration_ms", duration).
			Err(err)
	}

	event.Msg("Database operation completed")
}

// LogServerStart logs server startup
func (l *Logger) LogServerStart(port int, dbPath string) {
	l.zlog.Info().
		Str("event", "server_start").
		Int("port", port).
		Str("database", dbPath).
		Msg("TreeStore server starting")
}

// LogServerReady logs when server is ready
func (l *Logger) LogServerReady(port int) {
	l.zlog.Info().
		Str("event", "server_ready").
		Int("port", port).
		Msg("TreeStore server ready to accept connections")
}

// LogServerShutdown logs server shutdown
func (l *Logger) LogServerShutdown() {
	l.zlog.Info().
		Str("event", "server_shutdown").
		Msg("TreeStore server shutting down")
}

// Global logger instance
var globalLogger *Logger

// InitGlobalLogger initializes the global logger
func InitGlobalLogger(cfg Config) {
	globalLogger = NewLogger(cfg)
	log.Logger = *globalLogger.GetZerolog()
}

// GetGlobalLogger returns the global logger instance
func GetGlobalLogger() *Logger {
	if globalLogger == nil {
		// Initialize with defaults if not set
		InitGlobalLogger(Config{
			Level:  "info",
			Pretty: true,
		})
	}
	return globalLogger
}
