package wal

import (
	"fmt"
	"os"
)

// ReplayFunc is called for each operation that needs to be replayed
type ReplayFunc func(op OpType, key, value []byte) error

// Recovery manages crash recovery from WAL
type Recovery struct {
	wal *WAL
}

// NewRecovery creates a recovery manager
func NewRecovery(wal *WAL) *Recovery {
	return &Recovery{wal: wal}
}

// Recover replays the WAL and calls the replay function for each committed operation
func (r *Recovery) Recover(replay ReplayFunc) error {
	// Find all log files
	files, err := r.wal.findLogFiles()
	if err != nil {
		if os.IsNotExist(err) {
			return nil // No WAL files = fresh start
		}
		return err
	}

	// Read all entries
	entries, err := ReadAll(files)
	if err != nil {
		return fmt.Errorf("failed to read WAL entries: %w", err)
	}

	// Group entries by transaction
	transactions := r.groupByTransaction(entries)

	// Find last checkpoint
	lastCheckpoint := r.findLastCheckpoint(entries)

	// Replay committed transactions after last checkpoint
	for _, txn := range transactions {
		// Skip if transaction started before last checkpoint
		if lastCheckpoint != nil && txn.StartLSN < lastCheckpoint.LSN {
			continue
		}

		// Only replay committed transactions
		if !txn.Committed {
			continue
		}

		// Replay all operations in this transaction
		for _, entry := range txn.Entries {
			if entry.OpType == OpInsert || entry.OpType == OpDelete {
				if err := replay(entry.OpType, entry.Key, entry.Value); err != nil {
					return fmt.Errorf("replay failed at LSN %d: %w", entry.LSN, err)
				}
			}
		}
	}

	return nil
}

// Transaction represents a group of WAL entries for a single transaction
type Transaction struct {
	TxnID     uint64
	StartLSN  uint64
	Entries   []*Entry
	Committed bool
}

// groupByTransaction groups WAL entries by transaction ID
func (r *Recovery) groupByTransaction(entries []*Entry) []*Transaction {
	txnMap := make(map[uint64]*Transaction)
	var txnList []*Transaction

	for _, entry := range entries {
		// Skip checkpoint entries
		if entry.OpType == OpCheckpoint {
			continue
		}

		// Get or create transaction
		txn, exists := txnMap[entry.TxnID]
		if !exists {
			txn = &Transaction{
				TxnID:    entry.TxnID,
				StartLSN: entry.LSN,
				Entries:  make([]*Entry, 0),
			}
			txnMap[entry.TxnID] = txn
			txnList = append(txnList, txn)
		}

		// Add entry to transaction
		if entry.OpType == OpCommit {
			txn.Committed = true
		} else {
			txn.Entries = append(txn.Entries, entry)
		}
	}

	return txnList
}

// findLastCheckpoint finds the last checkpoint entry
func (r *Recovery) findLastCheckpoint(entries []*Entry) *Entry {
	for i := len(entries) - 1; i >= 0; i-- {
		if entries[i].OpType == OpCheckpoint {
			return entries[i]
		}
	}
	return nil
}

// Stats returns recovery statistics
type RecoveryStats struct {
	TotalEntries       int
	CommittedTxns      int
	UncommittedTxns    int
	ReplayedOperations int
	LastCheckpointLSN  uint64
}

// RecoverWithStats performs recovery and returns statistics
func (r *Recovery) RecoverWithStats(replay ReplayFunc) (*RecoveryStats, error) {
	stats := &RecoveryStats{}

	// Find all log files
	files, err := r.wal.findLogFiles()
	if err != nil {
		if os.IsNotExist(err) {
			return stats, nil
		}
		return nil, err
	}

	// Read all entries
	entries, err := ReadAll(files)
	if err != nil {
		return nil, err
	}

	stats.TotalEntries = len(entries)

	// Group by transaction
	transactions := r.groupByTransaction(entries)

	// Find last checkpoint
	lastCheckpoint := r.findLastCheckpoint(entries)
	if lastCheckpoint != nil {
		stats.LastCheckpointLSN = lastCheckpoint.LSN
	}

	// Count and replay
	for _, txn := range transactions {
		if lastCheckpoint != nil && txn.StartLSN < lastCheckpoint.LSN {
			continue
		}

		if txn.Committed {
			stats.CommittedTxns++
			for _, entry := range txn.Entries {
				if entry.OpType == OpInsert || entry.OpType == OpDelete {
					if err := replay(entry.OpType, entry.Key, entry.Value); err != nil {
						return stats, err
					}
					stats.ReplayedOperations++
				}
			}
		} else {
			stats.UncommittedTxns++
		}
	}

	return stats, nil
}
