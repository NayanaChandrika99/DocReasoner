// Package wal implements Write-Ahead Logging for durability and crash recovery
package wal

import "errors"

var (
	// ErrCorrupted indicates a corrupted WAL entry (CRC mismatch)
	ErrCorrupted = errors.New("wal: corrupted entry")

	// ErrInvalidEntry indicates an invalid WAL entry format
	ErrInvalidEntry = errors.New("wal: invalid entry")

	// ErrLogClosed indicates an operation on a closed WAL
	ErrLogClosed = errors.New("wal: log closed")

	// ErrLogNotFound indicates WAL files don't exist
	ErrLogNotFound = errors.New("wal: log not found")

	// ErrInvalidLSN indicates an invalid Log Sequence Number
	ErrInvalidLSN = errors.New("wal: invalid LSN")

	// ErrTruncated indicates a truncated WAL entry
	ErrTruncated = errors.New("wal: truncated entry")
)
