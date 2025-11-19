package wal

import (
	"fmt"
	"os"
	"time"
)

const (
	// DefaultCheckpointInterval is how often checkpoints are created
	DefaultCheckpointInterval = 10 * time.Minute
)

// Checkpointer manages periodic checkpointing
type Checkpointer struct {
	wal      *WAL
	interval time.Duration
	flushFn  func() error
	stopCh   chan struct{}
	doneCh   chan struct{}
}

// NewCheckpointer creates a checkpointer
func NewCheckpointer(wal *WAL, flushFn func() error) *Checkpointer {
	return &Checkpointer{
		wal:      wal,
		interval: DefaultCheckpointInterval,
		flushFn:  flushFn,
		stopCh:   make(chan struct{}),
		doneCh:   make(chan struct{}),
	}
}

// Start starts the background checkpointing process
func (c *Checkpointer) Start() {
	go c.run()
}

// Stop stops the checkpointer
func (c *Checkpointer) Stop() {
	close(c.stopCh)
	<-c.doneCh // Wait for goroutine to finish
}

// run is the main checkpointing loop
func (c *Checkpointer) run() {
	defer close(c.doneCh)

	ticker := time.NewTicker(c.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if err := c.Checkpoint(); err != nil {
				// Log error but continue
				// In production, use proper logging
			}

		case <-c.stopCh:
			return
		}
	}
}

// Checkpoint performs a checkpoint
func (c *Checkpointer) Checkpoint() error {
	// 1. Flush in-memory state to disk
	if err := c.flushFn(); err != nil {
		return fmt.Errorf("flush failed: %w", err)
	}

	// 2. Write checkpoint marker to WAL
	entry := Entry{
		LSN:       c.wal.NextLSN(),
		TxnID:     0, // Checkpoint doesn't belong to a transaction
		OpType:    OpCheckpoint,
		Timestamp: time.Now(),
	}

	if err := c.wal.Write(entry); err != nil {
		return fmt.Errorf("write checkpoint entry failed: %w", err)
	}

	if err := c.wal.Fsync(); err != nil {
		return fmt.Errorf("fsync checkpoint failed: %w", err)
	}

	// 3. Truncate old log files
	if err := c.truncateOldLogs(); err != nil {
		return fmt.Errorf("truncate failed: %w", err)
	}

	return nil
}

// truncateOldLogs removes log files before the last checkpoint
func (c *Checkpointer) truncateOldLogs() error {
	c.wal.mu.Lock()
	defer c.wal.mu.Unlock()

	files, err := c.wal.findLogFiles()
	if err != nil {
		return err
	}

	// Keep current file + last 2 files
	keepCount := 3
	if len(files) <= keepCount {
		return nil // Nothing to truncate
	}

	// Remove old files
	toRemove := files[:len(files)-keepCount]
	for _, file := range toRemove {
		if err := os.Remove(file); err != nil {
			// Log error but continue
		}
	}

	return nil
}

// SetInterval changes the checkpoint interval
func (c *Checkpointer) SetInterval(interval time.Duration) {
	c.interval = interval
}
