// ABOUTME: Order-preserving encoding for composite keys
// ABOUTME: Supports multiple data types with lexicographic ordering

package storage

import (
	"encoding/binary"
	"fmt"
	"time"
)

// Value types for composite keys
const (
	TYPE_BYTES  = 1
	TYPE_INT64  = 2
	TYPE_UINT64 = 3
	TYPE_TIME   = 4 // Stored as int64 Unix timestamp
)

// Value represents a single value in a composite key
type Value struct {
	Type uint8
	Str  []byte
	I64  int64
	U64  uint64
	Time time.Time
}

// NewBytesValue creates a bytes value
func NewBytesValue(data []byte) Value {
	return Value{Type: TYPE_BYTES, Str: data}
}

// NewInt64Value creates an int64 value
func NewInt64Value(i int64) Value {
	return Value{Type: TYPE_INT64, I64: i}
}

// NewUint64Value creates a uint64 value
func NewUint64Value(u uint64) Value {
	return Value{Type: TYPE_UINT64, U64: u}
}

// NewTimeValue creates a time value
func NewTimeValue(t time.Time) Value {
	return Value{Type: TYPE_TIME, Time: t}
}

// EncodeValues encodes multiple values in order-preserving format
// Each value is tagged with its type to prevent collisions with 0xFF
func EncodeValues(vals []Value) []byte {
	out := make([]byte, 0, 256)
	for _, v := range vals {
		out = append(out, byte(v.Type)) // Type tag (doesn't start with 0xFF)

		switch v.Type {
		case TYPE_INT64:
			// Flip sign bit for proper ordering
			var buf [8]byte
			u := uint64(v.I64) + (1 << 63)
			binary.BigEndian.PutUint64(buf[:], u)
			out = append(out, buf[:]...)

		case TYPE_UINT64:
			// Direct big-endian encoding
			var buf [8]byte
			binary.BigEndian.PutUint64(buf[:], v.U64)
			out = append(out, buf[:]...)

		case TYPE_TIME:
			// Encode as Unix timestamp (int64)
			var buf [8]byte
			u := uint64(v.Time.Unix()) + (1 << 63)
			binary.BigEndian.PutUint64(buf[:], u)
			out = append(out, buf[:]...)

		case TYPE_BYTES:
			// Escape and null-terminate
			out = append(out, escapeString(v.Str)...)
			out = append(out, 0)

		default:
			panic(fmt.Sprintf("unknown type: %d", v.Type))
		}
	}
	return out
}

// escapeString escapes null bytes and 0xFF for embedding in keys
func escapeString(s []byte) []byte {
	// Count escapes needed
	escapes := 0
	for _, b := range s {
		if b == 0 || b == 0xFF {
			escapes++
		}
	}

	if escapes == 0 {
		return s
	}

	// Allocate with room for escapes
	out := make([]byte, 0, len(s)+escapes)
	for _, b := range s {
		if b == 0 {
			out = append(out, 0xFE, 0x00) // Escape 0x00 as 0xFE 0x00
		} else if b == 0xFF {
			out = append(out, 0xFE, 0xFF) // Escape 0xFF as 0xFE 0xFF
		} else {
			out = append(out, b)
		}
	}
	return out
}

// unescapeString reverses escapeString
func unescapeString(s []byte) []byte {
	out := make([]byte, 0, len(s))
	for i := 0; i < len(s); i++ {
		if s[i] == 0xFE && i+1 < len(s) {
			// Unescape sequence
			out = append(out, s[i+1])
			i++ // Skip next byte
		} else {
			out = append(out, s[i])
		}
	}
	return out
}

// DecodeValues decodes values from encoded format
func DecodeValues(data []byte) ([]Value, error) {
	vals := make([]Value, 0, 4)
	pos := 0

	for pos < len(data) {
		if pos >= len(data) {
			break
		}

		typ := data[pos]
		pos++

		switch typ {
		case TYPE_INT64:
			if pos+8 > len(data) {
				return nil, fmt.Errorf("incomplete int64 at pos %d", pos)
			}
			u := binary.BigEndian.Uint64(data[pos : pos+8])
			i := int64(u - (1 << 63))
			vals = append(vals, NewInt64Value(i))
			pos += 8

		case TYPE_UINT64:
			if pos+8 > len(data) {
				return nil, fmt.Errorf("incomplete uint64 at pos %d", pos)
			}
			u := binary.BigEndian.Uint64(data[pos : pos+8])
			vals = append(vals, NewUint64Value(u))
			pos += 8

		case TYPE_TIME:
			if pos+8 > len(data) {
				return nil, fmt.Errorf("incomplete time at pos %d", pos)
			}
			u := binary.BigEndian.Uint64(data[pos : pos+8])
			i := int64(u - (1 << 63))
			vals = append(vals, NewTimeValue(time.Unix(i, 0)))
			pos += 8

		case TYPE_BYTES:
			// Find null terminator
			end := pos
			for end < len(data) && data[end] != 0 {
				end++
			}
			if end >= len(data) {
				return nil, fmt.Errorf("unterminated string at pos %d", pos)
			}
			str := unescapeString(data[pos:end])
			vals = append(vals, NewBytesValue(str))
			pos = end + 1 // Skip null terminator

		default:
			return nil, fmt.Errorf("unknown type: %d at pos %d", typ, pos-1)
		}
	}

	return vals, nil
}

// EncodeKey encodes a composite key with prefix
func EncodeKey(prefix uint32, vals []Value) []byte {
	// 4-byte prefix
	var buf [4]byte
	binary.BigEndian.PutUint32(buf[:], prefix)
	out := append([]byte{}, buf[:]...)

	// Order-preserving encoded values
	out = append(out, EncodeValues(vals)...)
	return out
}

// EncodeKeyPartial encodes a partial key for range queries
// Missing columns are encoded as +/- infinity based on comparison
func EncodeKeyPartial(prefix uint32, vals []Value, cmp int) []byte {
	out := EncodeKey(prefix, vals)

	// CMP_GT (>) and CMP_LE (<=) need +infinity for missing columns
	// CMP_LT (<) and CMP_GE (>=) use -infinity (empty string)
	if cmp == CMP_GT || cmp == CMP_LE {
		out = append(out, 0xFF) // Unreachable +infinity
	}
	// else: -infinity is just the empty suffix

	return out
}

// Comparison operators
const (
	CMP_GE = 1 // >=
	CMP_GT = 2 // >
	CMP_LT = 3 // <
	CMP_LE = 4 // <=
)

// ExtractPrefix extracts the prefix from an encoded key
func ExtractPrefix(key []byte) uint32 {
	if len(key) < 4 {
		return 0
	}
	return binary.BigEndian.Uint32(key[:4])
}

// ExtractValues extracts and decodes values from an encoded key
func ExtractValues(key []byte) ([]Value, error) {
	if len(key) < 4 {
		return nil, fmt.Errorf("key too short")
	}
	return DecodeValues(key[4:])
}
