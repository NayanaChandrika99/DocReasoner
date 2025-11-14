// ABOUTME: Metadata store implementation with flexible indexing
// ABOUTME: Supports multi-attribute queries and custom properties

package metadata

import (
	"fmt"

	"github.com/nainya/treestore/pkg/storage"
)

// Prefixes for metadata storage
const (
	PREFIX_METADATA          = uint32(7000)
	PREFIX_METADATA_ENTITY   = uint32(7100) // Index by (entityType, entityID, key)
	PREFIX_METADATA_KEY      = uint32(7200) // Index by (key, entityType, entityID)
	PREFIX_METADATA_VALUE    = uint32(7300) // Index by (key, value, entityType, entityID)
	PREFIX_METADATA_COMPOUND = uint32(7400) // Compound index for multi-attribute queries
)

// MetadataStore manages custom metadata and attributes
type MetadataStore struct {
	kv *storage.KV
}

// NewMetadataStore creates a new metadata store
func NewMetadataStore(kv *storage.KV) *MetadataStore {
	return &MetadataStore{kv: kv}
}

// SetMetadata stores or updates a metadata entry
func (ms *MetadataStore) SetMetadata(entry *MetadataEntry) error {
	tx := ms.kv.Begin()

	// Primary key: (entityType, entityID, key)
	key := storage.EncodeKey(PREFIX_METADATA, []storage.Value{
		storage.NewBytesValue([]byte(entry.EntityType)),
		storage.NewBytesValue([]byte(entry.EntityID)),
		storage.NewBytesValue([]byte(entry.Key)),
	})

	val := storage.EncodeValues([]storage.Value{
		storage.NewBytesValue([]byte(entry.EntityType)),
		storage.NewBytesValue([]byte(entry.EntityID)),
		storage.NewBytesValue([]byte(entry.Key)),
		storage.NewBytesValue([]byte(entry.Value)),
		storage.NewBytesValue([]byte(entry.ValueType)),
		storage.NewTimeValue(entry.CreatedAt),
		storage.NewTimeValue(entry.UpdatedAt),
	})

	tx.Set(key, val)

	// Entity index: (entityType, entityID, key)
	entityKey := storage.EncodeKey(PREFIX_METADATA_ENTITY, []storage.Value{
		storage.NewBytesValue([]byte(entry.EntityType)),
		storage.NewBytesValue([]byte(entry.EntityID)),
		storage.NewBytesValue([]byte(entry.Key)),
	})
	tx.Set(entityKey, []byte{})

	// Key index: (key, entityType, entityID)
	keyIndex := storage.EncodeKey(PREFIX_METADATA_KEY, []storage.Value{
		storage.NewBytesValue([]byte(entry.Key)),
		storage.NewBytesValue([]byte(entry.EntityType)),
		storage.NewBytesValue([]byte(entry.EntityID)),
	})
	tx.Set(keyIndex, []byte{})

	// Value index: (key, value, entityType, entityID)
	valueIndex := storage.EncodeKey(PREFIX_METADATA_VALUE, []storage.Value{
		storage.NewBytesValue([]byte(entry.Key)),
		storage.NewBytesValue([]byte(entry.Value)),
		storage.NewBytesValue([]byte(entry.EntityType)),
		storage.NewBytesValue([]byte(entry.EntityID)),
	})
	tx.Set(valueIndex, []byte{})

	return tx.Commit()
}

// GetMetadata retrieves a specific metadata entry
func (ms *MetadataStore) GetMetadata(entityType, entityID, key string) (*MetadataEntry, error) {
	metaKey := storage.EncodeKey(PREFIX_METADATA, []storage.Value{
		storage.NewBytesValue([]byte(entityType)),
		storage.NewBytesValue([]byte(entityID)),
		storage.NewBytesValue([]byte(key)),
	})

	val, ok := ms.kv.Get(metaKey)
	if !ok {
		return nil, fmt.Errorf("metadata not found: %s/%s/%s", entityType, entityID, key)
	}

	vals, err := storage.DecodeValues(val)
	if err != nil {
		return nil, err
	}

	return parseMetadataVals(vals)
}

// GetAllMetadata retrieves all metadata for an entity
func (ms *MetadataStore) GetAllMetadata(entityType, entityID string) (map[string]string, error) {
	startKey := storage.EncodeKey(PREFIX_METADATA_ENTITY, []storage.Value{
		storage.NewBytesValue([]byte(entityType)),
		storage.NewBytesValue([]byte(entityID)),
	})

	result := make(map[string]string)

	ms.kv.Scan(startKey, func(key, val []byte) bool {
		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 3 {
			return true
		}

		// Check if still in same entity
		if string(vals[0].Str) != entityType || string(vals[1].Str) != entityID {
			return false
		}

		metaKey := string(vals[2].Str)
		entry, err := ms.GetMetadata(entityType, entityID, metaKey)
		if err == nil {
			result[metaKey] = entry.Value
		}

		return true
	})

	return result, nil
}

// DeleteMetadata removes a metadata entry
func (ms *MetadataStore) DeleteMetadata(entityType, entityID, key string) error {
	// Get entry first to clean up indexes
	entry, err := ms.GetMetadata(entityType, entityID, key)
	if err != nil {
		return err
	}

	tx := ms.kv.Begin()

	// Delete primary
	primaryKey := storage.EncodeKey(PREFIX_METADATA, []storage.Value{
		storage.NewBytesValue([]byte(entityType)),
		storage.NewBytesValue([]byte(entityID)),
		storage.NewBytesValue([]byte(key)),
	})
	tx.Del(primaryKey)

	// Delete entity index
	entityKey := storage.EncodeKey(PREFIX_METADATA_ENTITY, []storage.Value{
		storage.NewBytesValue([]byte(entityType)),
		storage.NewBytesValue([]byte(entityID)),
		storage.NewBytesValue([]byte(key)),
	})
	tx.Del(entityKey)

	// Delete key index
	keyIndex := storage.EncodeKey(PREFIX_METADATA_KEY, []storage.Value{
		storage.NewBytesValue([]byte(key)),
		storage.NewBytesValue([]byte(entityType)),
		storage.NewBytesValue([]byte(entityID)),
	})
	tx.Del(keyIndex)

	// Delete value index
	valueIndex := storage.EncodeKey(PREFIX_METADATA_VALUE, []storage.Value{
		storage.NewBytesValue([]byte(key)),
		storage.NewBytesValue([]byte(entry.Value)),
		storage.NewBytesValue([]byte(entityType)),
		storage.NewBytesValue([]byte(entityID)),
	})
	tx.Del(valueIndex)

	return tx.Commit()
}

// QueryByKey finds all entities with a specific metadata key
func (ms *MetadataStore) QueryByKey(key string, entityType *string, limit int) ([]*MetadataEntry, error) {
	var startKey []byte
	if entityType != nil {
		startKey = storage.EncodeKey(PREFIX_METADATA_KEY, []storage.Value{
			storage.NewBytesValue([]byte(key)),
			storage.NewBytesValue([]byte(*entityType)),
		})
	} else {
		startKey = storage.EncodeKey(PREFIX_METADATA_KEY, []storage.Value{
			storage.NewBytesValue([]byte(key)),
		})
	}

	var results []*MetadataEntry
	count := 0

	ms.kv.Scan(startKey, func(k, val []byte) bool {
		if limit > 0 && count >= limit {
			return false
		}

		vals, err := storage.ExtractValues(k)
		if err != nil || len(vals) < 3 {
			return true
		}

		// Check if still in same key
		if string(vals[0].Str) != key {
			return false
		}

		// If entityType filter specified, check it
		if entityType != nil && string(vals[1].Str) != *entityType {
			return true
		}

		eType := string(vals[1].Str)
		eID := string(vals[2].Str)

		entry, err := ms.GetMetadata(eType, eID, key)
		if err == nil {
			results = append(results, entry)
			count++
		}

		return true
	})

	return results, nil
}

// QueryByKeyValue finds all entities with a specific key-value pair
func (ms *MetadataStore) QueryByKeyValue(key, value string, entityType *string, limit int) ([]*MetadataEntry, error) {
	var startKey []byte
	if entityType != nil {
		startKey = storage.EncodeKey(PREFIX_METADATA_VALUE, []storage.Value{
			storage.NewBytesValue([]byte(key)),
			storage.NewBytesValue([]byte(value)),
			storage.NewBytesValue([]byte(*entityType)),
		})
	} else {
		startKey = storage.EncodeKey(PREFIX_METADATA_VALUE, []storage.Value{
			storage.NewBytesValue([]byte(key)),
			storage.NewBytesValue([]byte(value)),
		})
	}

	var results []*MetadataEntry
	count := 0

	ms.kv.Scan(startKey, func(k, val []byte) bool {
		if limit > 0 && count >= limit {
			return false
		}

		vals, err := storage.ExtractValues(k)
		if err != nil || len(vals) < 4 {
			return true
		}

		// Check if still in same key-value
		if string(vals[0].Str) != key || string(vals[1].Str) != value {
			return false
		}

		// If entityType filter specified, check it
		if entityType != nil && string(vals[2].Str) != *entityType {
			return true
		}

		eType := string(vals[2].Str)
		eID := string(vals[3].Str)

		entry, err := ms.GetMetadata(eType, eID, key)
		if err == nil {
			results = append(results, entry)
			count++
		}

		return true
	})

	return results, nil
}

// QueryMultiple finds entities matching multiple key-value pairs
func (ms *MetadataStore) QueryMultiple(filters map[string]string, entityType *string, limit int) ([]string, error) {
	if len(filters) == 0 {
		return []string{}, nil
	}

	// Get entities for first filter
	var firstKey, firstValue string
	for k, v := range filters {
		firstKey = k
		firstValue = v
		break
	}

	entries, err := ms.QueryByKeyValue(firstKey, firstValue, entityType, 0)
	if err != nil {
		return nil, err
	}

	// Build candidate set
	candidates := make(map[string]bool)
	for _, entry := range entries {
		candidates[entry.EntityID] = true
	}

	// Filter by remaining criteria
	for key, value := range filters {
		if key == firstKey {
			continue
		}

		// Check each candidate
		for entityID := range candidates {
			var eType string
			if entityType != nil {
				eType = *entityType
			} else {
				// Need to determine entityType from previous entry
				for _, e := range entries {
					if e.EntityID == entityID {
						eType = e.EntityType
						break
					}
				}
			}

			entry, err := ms.GetMetadata(eType, entityID, key)
			if err != nil || entry.Value != value {
				delete(candidates, entityID)
			}
		}
	}

	// Collect results
	results := make([]string, 0, len(candidates))
	for entityID := range candidates {
		results = append(results, entityID)
		if limit > 0 && len(results) >= limit {
			break
		}
	}

	return results, nil
}

// Helper functions

func parseMetadataVals(vals []storage.Value) (*MetadataEntry, error) {
	if len(vals) < 7 {
		return nil, fmt.Errorf("incomplete metadata data")
	}

	return &MetadataEntry{
		EntityType: string(vals[0].Str),
		EntityID:   string(vals[1].Str),
		Key:        string(vals[2].Str),
		Value:      string(vals[3].Str),
		ValueType:  string(vals[4].Str),
		CreatedAt:  vals[5].Time,
		UpdatedAt:  vals[6].Time,
	}, nil
}
