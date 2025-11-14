// ABOUTME: Tests for composite key encoding
// ABOUTME: Verifies order-preserving properties and roundtrip encoding

package storage

import (
	"bytes"
	"testing"
	"time"
)

func TestEncodeInt64(t *testing.T) {
	vals := []Value{
		NewInt64Value(-1000),
		NewInt64Value(-1),
		NewInt64Value(0),
		NewInt64Value(1),
		NewInt64Value(1000),
	}

	// Encode all values
	encoded := make([][]byte, len(vals))
	for i, v := range vals {
		encoded[i] = EncodeValues([]Value{v})
	}

	// Verify ordering
	for i := 0; i < len(encoded)-1; i++ {
		if bytes.Compare(encoded[i], encoded[i+1]) >= 0 {
			t.Errorf("Order violated: %d should be < %d", vals[i].I64, vals[i+1].I64)
		}
	}

	// Verify roundtrip
	for i, enc := range encoded {
		decoded, err := DecodeValues(enc)
		if err != nil {
			t.Fatalf("Failed to decode: %v", err)
		}
		if len(decoded) != 1 {
			t.Fatalf("Expected 1 value, got %d", len(decoded))
		}
		if decoded[0].I64 != vals[i].I64 {
			t.Errorf("Roundtrip failed: expected %d, got %d", vals[i].I64, decoded[0].I64)
		}
	}
}

func TestEncodeBytes(t *testing.T) {
	vals := []Value{
		NewBytesValue([]byte("")),
		NewBytesValue([]byte("a")),
		NewBytesValue([]byte("aa")),
		NewBytesValue([]byte("ab")),
		NewBytesValue([]byte("b")),
	}

	// Encode all values
	encoded := make([][]byte, len(vals))
	for i, v := range vals {
		encoded[i] = EncodeValues([]Value{v})
	}

	// Verify ordering
	for i := 0; i < len(encoded)-1; i++ {
		if bytes.Compare(encoded[i], encoded[i+1]) >= 0 {
			t.Errorf("Order violated: %s should be < %s", vals[i].Str, vals[i+1].Str)
		}
	}

	// Verify roundtrip
	for i, enc := range encoded {
		decoded, err := DecodeValues(enc)
		if err != nil {
			t.Fatalf("Failed to decode: %v", err)
		}
		if len(decoded) != 1 {
			t.Fatalf("Expected 1 value, got %d", len(decoded))
		}
		if !bytes.Equal(decoded[0].Str, vals[i].Str) {
			t.Errorf("Roundtrip failed: expected %s, got %s", vals[i].Str, decoded[0].Str)
		}
	}
}

func TestEncodeComposite(t *testing.T) {
	// Test composite keys with ordering
	keys := [][]Value{
		{NewBytesValue([]byte("a")), NewInt64Value(1)},
		{NewBytesValue([]byte("a")), NewInt64Value(2)},
		{NewBytesValue([]byte("b")), NewInt64Value(1)},
		{NewBytesValue([]byte("b")), NewInt64Value(2)},
	}

	// Encode all keys
	encoded := make([][]byte, len(keys))
	for i, k := range keys {
		encoded[i] = EncodeValues(k)
	}

	// Verify ordering
	for i := 0; i < len(encoded)-1; i++ {
		if bytes.Compare(encoded[i], encoded[i+1]) >= 0 {
			t.Errorf("Order violated at index %d", i)
		}
	}

	// Verify roundtrip
	for i, enc := range encoded {
		decoded, err := DecodeValues(enc)
		if err != nil {
			t.Fatalf("Failed to decode: %v", err)
		}
		if len(decoded) != len(keys[i]) {
			t.Fatalf("Expected %d values, got %d", len(keys[i]), len(decoded))
		}
		for j := range decoded {
			if decoded[j].Type != keys[i][j].Type {
				t.Errorf("Type mismatch at index %d,%d", i, j)
			}
		}
	}
}

func TestEncodeKeyWithPrefix(t *testing.T) {
	prefix := uint32(100)
	vals := []Value{
		NewBytesValue([]byte("test")),
		NewInt64Value(42),
	}

	encoded := EncodeKey(prefix, vals)

	// Extract prefix
	extractedPrefix := ExtractPrefix(encoded)
	if extractedPrefix != prefix {
		t.Errorf("Expected prefix %d, got %d", prefix, extractedPrefix)
	}

	// Extract values
	extractedVals, err := ExtractValues(encoded)
	if err != nil {
		t.Fatalf("Failed to extract values: %v", err)
	}

	if len(extractedVals) != len(vals) {
		t.Fatalf("Expected %d values, got %d", len(vals), len(extractedVals))
	}

	if !bytes.Equal(extractedVals[0].Str, vals[0].Str) {
		t.Errorf("Value 0 mismatch")
	}
	if extractedVals[1].I64 != vals[1].I64 {
		t.Errorf("Value 1 mismatch")
	}
}

func TestEncodeTime(t *testing.T) {
	now := time.Now()
	times := []Value{
		NewTimeValue(now.Add(-time.Hour)),
		NewTimeValue(now),
		NewTimeValue(now.Add(time.Hour)),
	}

	// Encode all times
	encoded := make([][]byte, len(times))
	for i, v := range times {
		encoded[i] = EncodeValues([]Value{v})
	}

	// Verify ordering
	for i := 0; i < len(encoded)-1; i++ {
		if bytes.Compare(encoded[i], encoded[i+1]) >= 0 {
			t.Errorf("Time order violated at index %d", i)
		}
	}

	// Verify roundtrip (note: precision is seconds)
	for i, enc := range encoded {
		decoded, err := DecodeValues(enc)
		if err != nil {
			t.Fatalf("Failed to decode: %v", err)
		}
		if len(decoded) != 1 {
			t.Fatalf("Expected 1 value, got %d", len(decoded))
		}
		if decoded[0].Time.Unix() != times[i].Time.Unix() {
			t.Errorf("Time roundtrip failed")
		}
	}
}

func TestEscapeString(t *testing.T) {
	tests := []struct {
		input []byte
		name  string
	}{
		{[]byte("normal"), "normal string"},
		{[]byte{0x00}, "null byte"},
		{[]byte{0xFF}, "0xFF byte"},
		{[]byte{0x00, 0xFF}, "null and 0xFF"},
		{[]byte("test\x00string"), "embedded null"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			escaped := escapeString(tt.input)
			unescaped := unescapeString(escaped)

			if !bytes.Equal(unescaped, tt.input) {
				t.Errorf("Escape/unescape failed for %v", tt.input)
			}
		})
	}
}

func TestPartialKeyEncoding(t *testing.T) {
	prefix := uint32(1)

	// Partial key for (a, b) > (1, +∞)
	key1 := EncodeKeyPartial(prefix, []Value{NewInt64Value(1)}, CMP_GT)

	// Partial key for (a, b) >= (1, -∞)
	key2 := EncodeKeyPartial(prefix, []Value{NewInt64Value(1)}, CMP_GE)

	// key2 should be less than key1 because -∞ < +∞
	if bytes.Compare(key2, key1) >= 0 {
		t.Error("Expected key2 < key1")
	}

	// Full key (1, 0) should be between them
	fullKey := EncodeKey(prefix, []Value{NewInt64Value(1), NewInt64Value(0)})

	if bytes.Compare(key2, fullKey) >= 0 {
		t.Error("Expected key2 <= fullKey")
	}
	if bytes.Compare(fullKey, key1) >= 0 {
		t.Error("Expected fullKey < key1")
	}
}
