// ABOUTME: Performance benchmarks for storage layer
// ABOUTME: Measures throughput and latency for KV operations

package storage

import (
	"fmt"
	"os"
	"testing"
)

func BenchmarkKVInsert(b *testing.B) {
	path := "/tmp/bench_insert.db"
	defer os.Remove(path)

	kv := &KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		key := []byte(fmt.Sprintf("key%010d", i))
		val := []byte(fmt.Sprintf("value%010d", i))
		if err := kv.Set(key, val); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkKVGet(b *testing.B) {
	path := "/tmp/bench_get.db"
	defer os.Remove(path)

	kv := &KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	// Pre-populate
	numKeys := 10000
	for i := 0; i < numKeys; i++ {
		key := []byte(fmt.Sprintf("key%010d", i))
		val := []byte(fmt.Sprintf("value%010d", i))
		kv.Set(key, val)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		key := []byte(fmt.Sprintf("key%010d", i%numKeys))
		_, ok := kv.Get(key)
		if !ok {
			b.Fatal("key not found")
		}
	}
}

func BenchmarkKVUpdate(b *testing.B) {
	path := "/tmp/bench_update.db"
	defer os.Remove(path)

	kv := &KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	// Pre-populate
	numKeys := 1000
	for i := 0; i < numKeys; i++ {
		key := []byte(fmt.Sprintf("key%010d", i))
		val := []byte(fmt.Sprintf("value%010d", i))
		kv.Set(key, val)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		key := []byte(fmt.Sprintf("key%010d", i%numKeys))
		val := []byte(fmt.Sprintf("newvalue%010d", i))
		if err := kv.Set(key, val); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkKVDelete(b *testing.B) {
	path := "/tmp/bench_delete.db"
	defer os.Remove(path)

	kv := &KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	// Pre-populate more than we'll delete
	numKeys := b.N * 2
	for i := 0; i < numKeys; i++ {
		key := []byte(fmt.Sprintf("key%010d", i))
		val := []byte(fmt.Sprintf("value%010d", i))
		kv.Set(key, val)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		key := []byte(fmt.Sprintf("key%010d", i))
		_, err := kv.Del(key)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkKVScan(b *testing.B) {
	path := "/tmp/bench_scan.db"
	defer os.Remove(path)

	kv := &KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	// Pre-populate
	numKeys := 10000
	for i := 0; i < numKeys; i++ {
		key := []byte(fmt.Sprintf("key%010d", i))
		val := []byte(fmt.Sprintf("value%010d", i))
		kv.Set(key, val)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		count := 0
		kv.Scan([]byte("key"), func(k, v []byte) bool {
			count++
			return count < 100 // Scan first 100
		})
	}
}

func BenchmarkKVTransaction(b *testing.B) {
	path := "/tmp/bench_tx.db"
	defer os.Remove(path)

	kv := &KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		tx := kv.Begin()
		for j := 0; j < 10; j++ {
			key := []byte(fmt.Sprintf("key%010d", i*10+j))
			val := []byte(fmt.Sprintf("value%010d", i*10+j))
			tx.Set(key, val)
		}
		if err := tx.Commit(); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkKVBatchInsert(b *testing.B) {
	sizes := []int{10, 100, 1000}

	for _, size := range sizes {
		b.Run(fmt.Sprintf("batch_%d", size), func(b *testing.B) {
			path := fmt.Sprintf("/tmp/bench_batch_%d.db", size)
			defer os.Remove(path)

			kv := &KV{Path: path}
			if err := kv.Open(); err != nil {
				b.Fatal(err)
			}
			defer kv.Close()

			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				tx := kv.Begin()
				for j := 0; j < size; j++ {
					key := []byte(fmt.Sprintf("key%010d", i*size+j))
					val := []byte(fmt.Sprintf("value%010d", i*size+j))
					tx.Set(key, val)
				}
				if err := tx.Commit(); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}

func BenchmarkEncodeKey(b *testing.B) {
	values := []Value{
		NewBytesValue([]byte("policyID")),
		NewBytesValue([]byte("nodeID")),
		NewInt64Value(12345),
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		EncodeKey(1000, values)
	}
}

func BenchmarkDecodeValues(b *testing.B) {
	values := []Value{
		NewBytesValue([]byte("policyID")),
		NewBytesValue([]byte("nodeID")),
		NewInt64Value(12345),
	}
	encoded := EncodeValues(values)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := DecodeValues(encoded)
		if err != nil {
			b.Fatal(err)
		}
	}
}
