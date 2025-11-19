package wal

import (
	"encoding/binary"
	"fmt"
	"hash/crc32"
	"time"
)

// OpType represents the type of WAL operation
type OpType byte

const (
	// OpInsert represents a key-value insertion
	OpInsert OpType = 1

	// OpDelete represents a key deletion
	OpDelete OpType = 2

	// OpCommit represents a transaction commit marker
	OpCommit OpType = 3

	// OpCheckpoint represents a checkpoint marker
	OpCheckpoint OpType = 4
)

const (
	// EntryHeaderSize is the fixed size of the entry header
	// Layout: LSN(8) + TxnID(8) + OpType(1) + Reserved(7) + KeyLen(4) + ValLen(4) + Timestamp(8)
	EntryHeaderSize = 40
)

// Entry represents a single WAL entry
type Entry struct {
	LSN       uint64    // Log Sequence Number (monotonically increasing)
	TxnID     uint64    // Transaction ID
	OpType    OpType    // Operation type
	Key       []byte    // Key (for INSERT/DELETE)
	Value     []byte    // Value (for INSERT only)
	Timestamp time.Time // Entry timestamp
}

// Encode serializes the entry to bytes with CRC32 checksum
// Format: [Header(40)] [Key] [Value] [CRC32(4)]
func (e *Entry) Encode() []byte {
	keyLen := len(e.Key)
	valLen := len(e.Value)
	totalSize := EntryHeaderSize + keyLen + valLen + 4 // +4 for CRC32

	buf := make([]byte, totalSize)

	// Encode header
	binary.LittleEndian.PutUint64(buf[0:8], e.LSN)
	binary.LittleEndian.PutUint64(buf[8:16], e.TxnID)
	buf[16] = byte(e.OpType)
	// bytes 17-23 are reserved (padding)
	binary.LittleEndian.PutUint32(buf[24:28], uint32(keyLen))
	binary.LittleEndian.PutUint32(buf[28:32], uint32(valLen))
	binary.LittleEndian.PutUint64(buf[32:40], uint64(e.Timestamp.Unix()))

	// Encode key and value
	offset := EntryHeaderSize
	copy(buf[offset:], e.Key)
	offset += keyLen
	copy(buf[offset:], e.Value)
	offset += valLen

	// Compute and append CRC32 checksum (excludes the CRC32 field itself)
	crc := crc32.ChecksumIEEE(buf[:offset])
	binary.LittleEndian.PutUint32(buf[offset:offset+4], crc)

	return buf
}

// DecodeEntry deserializes a WAL entry from bytes
func DecodeEntry(data []byte) (*Entry, error) {
	if len(data) < EntryHeaderSize+4 {
		return nil, ErrTruncated
	}

	// Verify CRC32 checksum
	dataLen := len(data)
	storedCRC := binary.LittleEndian.Uint32(data[dataLen-4:])
	computedCRC := crc32.ChecksumIEEE(data[:dataLen-4])
	if storedCRC != computedCRC {
		return nil, ErrCorrupted
	}

	// Decode header
	entry := &Entry{
		LSN:    binary.LittleEndian.Uint64(data[0:8]),
		TxnID:  binary.LittleEndian.Uint64(data[8:16]),
		OpType: OpType(data[16]),
	}

	keyLen := binary.LittleEndian.Uint32(data[24:28])
	valLen := binary.LittleEndian.Uint32(data[28:32])
	timestamp := binary.LittleEndian.Uint64(data[32:40])
	entry.Timestamp = time.Unix(int64(timestamp), 0)

	// Validate entry size
	expectedSize := EntryHeaderSize + int(keyLen) + int(valLen) + 4
	if len(data) < expectedSize {
		return nil, ErrTruncated
	}

	// Decode key and value
	offset := EntryHeaderSize
	if keyLen > 0 {
		entry.Key = make([]byte, keyLen)
		copy(entry.Key, data[offset:offset+int(keyLen)])
		offset += int(keyLen)
	}

	if valLen > 0 {
		entry.Value = make([]byte, valLen)
		copy(entry.Value, data[offset:offset+int(valLen)])
	}

	return entry, nil
}

// Size returns the encoded size of the entry
func (e *Entry) Size() int {
	return EntryHeaderSize + len(e.Key) + len(e.Value) + 4
}

// String returns a human-readable representation of the entry
func (e *Entry) String() string {
	opName := "UNKNOWN"
	switch e.OpType {
	case OpInsert:
		opName = "INSERT"
	case OpDelete:
		opName = "DELETE"
	case OpCommit:
		opName = "COMMIT"
	case OpCheckpoint:
		opName = "CHECKPOINT"
	}
	return fmt.Sprintf("WAL[LSN=%d TxnID=%d Op=%s KeyLen=%d ValLen=%d]",
		e.LSN, e.TxnID, opName, len(e.Key), len(e.Value))
}
