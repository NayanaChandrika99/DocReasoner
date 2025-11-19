package wal

import (
	"encoding/binary"
	"io"
	"os"
)

// Reader reads WAL entries from log files
type Reader struct {
	files   []string // Log files to read
	current int      // Current file index
	fd      *os.File // Current file descriptor
	offset  int64    // Current offset in file
}

// NewReader creates a WAL reader for the given log files
func NewReader(files []string) *Reader {
	return &Reader{
		files:   files,
		current: 0,
	}
}

// Open opens the reader
func (r *Reader) Open() error {
	if len(r.files) == 0 {
		return ErrLogNotFound
	}

	// Open first file
	fd, err := os.Open(r.files[0])
	if err != nil {
		return err
	}

	r.fd = fd
	r.offset = 0
	return nil
}

// Next reads the next entry
func (r *Reader) Next() (*Entry, error) {
	for {
		// Try reading from current file
		entry, err := r.readEntryFromCurrent()
		if err == nil {
			return entry, nil
		}

		// EOF on current file - move to next
		if err == io.EOF {
			if err := r.nextFile(); err != nil {
				return nil, err // No more files
			}
			continue
		}

		// Corrupted entry - skip and continue
		if err == ErrCorrupted || err == ErrTruncated {
			// Try to skip corrupted entry by finding next valid header
			if err := r.skipToNextEntry(); err != nil {
				return nil, err
			}
			continue
		}

		return nil, err
	}
}

// readEntryFromCurrent reads an entry from the current file
func (r *Reader) readEntryFromCurrent() (*Entry, error) {
	if r.fd == nil {
		return nil, io.EOF
	}

	// Read header
	header := make([]byte, EntryHeaderSize)
	n, err := r.fd.Read(header)
	if err != nil {
		return nil, err
	}
	if n < EntryHeaderSize {
		return nil, io.EOF
	}

	// Parse lengths
	keyLen := binary.LittleEndian.Uint32(header[24:28])
	valLen := binary.LittleEndian.Uint32(header[28:32])

	// Read rest of entry
	dataLen := int(keyLen) + int(valLen) + 4
	data := make([]byte, EntryHeaderSize+dataLen)
	copy(data, header)

	n, err = io.ReadFull(r.fd, data[EntryHeaderSize:])
	if err != nil {
		return nil, err
	}

	r.offset += int64(EntryHeaderSize + dataLen)

	// Decode entry
	return DecodeEntry(data)
}

// nextFile moves to the next log file
func (r *Reader) nextFile() error {
	if r.fd != nil {
		r.fd.Close()
		r.fd = nil
	}

	r.current++
	if r.current >= len(r.files) {
		return io.EOF // No more files
	}

	// Open next file
	fd, err := os.Open(r.files[r.current])
	if err != nil {
		return err
	}

	r.fd = fd
	r.offset = 0
	return nil
}

// skipToNextEntry attempts to skip corrupted data and find next valid entry
func (r *Reader) skipToNextEntry() error {
	// Simple strategy: skip 1KB and try again
	// More sophisticated: scan for valid header magic
	_, err := r.fd.Seek(1024, io.SeekCurrent)
	if err != nil {
		return err
	}
	r.offset += 1024
	return nil
}

// Close closes the reader
func (r *Reader) Close() error {
	if r.fd != nil {
		return r.fd.Close()
	}
	return nil
}

// ReadAll reads all entries from all files
func ReadAll(files []string) ([]*Entry, error) {
	reader := NewReader(files)
	if err := reader.Open(); err != nil {
		return nil, err
	}
	defer reader.Close()

	var entries []*Entry
	for {
		entry, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		entries = append(entries, entry)
	}

	return entries, nil
}
