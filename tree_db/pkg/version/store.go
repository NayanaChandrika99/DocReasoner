// ABOUTME: Version store implementation with temporal queries
// ABOUTME: Manages document versions with time-based access

package version

import (
	"fmt"
	"time"

	"github.com/nainya/treestore/pkg/storage"
)

// Prefixes for version storage
const (
	PREFIX_VERSION        = uint32(6000)
	PREFIX_VERSION_TIME   = uint32(6100) // Index by (policyID, createdAt, versionID)
	PREFIX_VERSION_TAG    = uint32(6200) // Index by (policyID, tag, versionID)
	PREFIX_LATEST_VERSION = uint32(6300) // Track latest version per policy
)

// VersionStore manages document versions
type VersionStore struct {
	kv *storage.KV
}

// NewVersionStore creates a new version store
func NewVersionStore(kv *storage.KV) *VersionStore {
	return &VersionStore{kv: kv}
}

// CreateVersion stores a new version
func (vs *VersionStore) CreateVersion(v *Version) error {
	tx := vs.kv.Begin()

	// Primary key: (policyID, versionID)
	key := storage.EncodeKey(PREFIX_VERSION, []storage.Value{
		storage.NewBytesValue([]byte(v.PolicyID)),
		storage.NewBytesValue([]byte(v.VersionID)),
	})

	// Encode version data
	val := storage.EncodeValues([]storage.Value{
		storage.NewBytesValue([]byte(v.PolicyID)),
		storage.NewBytesValue([]byte(v.VersionID)),
		storage.NewBytesValue([]byte(v.DocumentID)),
		storage.NewTimeValue(v.CreatedAt),
		storage.NewBytesValue([]byte(v.CreatedBy)),
		storage.NewBytesValue([]byte(v.Description)),
		storage.NewBytesValue(encodeStringArray(v.Tags)),
		storage.NewBytesValue(encodeMetadata(v.Metadata)),
	})

	tx.Set(key, val)

	// Time-based index: (policyID, createdAt, versionID)
	timeKey := storage.EncodeKey(PREFIX_VERSION_TIME, []storage.Value{
		storage.NewBytesValue([]byte(v.PolicyID)),
		storage.NewTimeValue(v.CreatedAt),
		storage.NewBytesValue([]byte(v.VersionID)),
	})
	tx.Set(timeKey, []byte{})

	// Tag indexes: (policyID, tag, versionID)
	for _, tag := range v.Tags {
		tagKey := storage.EncodeKey(PREFIX_VERSION_TAG, []storage.Value{
			storage.NewBytesValue([]byte(v.PolicyID)),
			storage.NewBytesValue([]byte(tag)),
			storage.NewBytesValue([]byte(v.VersionID)),
		})
		tx.Set(tagKey, []byte{})
	}

	// Update latest version pointer
	latestKey := storage.EncodeKey(PREFIX_LATEST_VERSION, []storage.Value{
		storage.NewBytesValue([]byte(v.PolicyID)),
	})
	tx.Set(latestKey, []byte(v.VersionID))

	return tx.Commit()
}

// GetVersion retrieves a specific version
func (vs *VersionStore) GetVersion(policyID, versionID string) (*Version, error) {
	key := storage.EncodeKey(PREFIX_VERSION, []storage.Value{
		storage.NewBytesValue([]byte(policyID)),
		storage.NewBytesValue([]byte(versionID)),
	})

	val, ok := vs.kv.Get(key)
	if !ok {
		return nil, fmt.Errorf("version not found: %s/%s", policyID, versionID)
	}

	vals, err := storage.DecodeValues(val)
	if err != nil {
		return nil, err
	}

	return parseVersionVals(vals)
}

// GetLatestVersion returns the most recent version for a policy
func (vs *VersionStore) GetLatestVersion(policyID string) (*Version, error) {
	latestKey := storage.EncodeKey(PREFIX_LATEST_VERSION, []storage.Value{
		storage.NewBytesValue([]byte(policyID)),
	})

	versionIDBytes, ok := vs.kv.Get(latestKey)
	if !ok {
		return nil, fmt.Errorf("no versions found for policy: %s", policyID)
	}

	versionID := string(versionIDBytes)
	return vs.GetVersion(policyID, versionID)
}

// GetVersionAsOf returns the version that was current at a specific time
func (vs *VersionStore) GetVersionAsOf(policyID string, asOfTime time.Time) (*Version, error) {
	// Scan time index to find the latest version before asOfTime
	startKey := storage.EncodeKey(PREFIX_VERSION_TIME, []storage.Value{
		storage.NewBytesValue([]byte(policyID)),
	})

	var latestVersion *Version
	var latestTime time.Time

	vs.kv.Scan(startKey, func(key, val []byte) bool {
		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 3 {
			return true
		}

		// Check if still in same policy
		if string(vals[0].Str) != policyID {
			return false
		}

		createdAt := vals[1].Time
		versionID := string(vals[2].Str)

		// Only consider versions created before or at asOfTime
		if createdAt.After(asOfTime) {
			return true
		}

		// Track the latest version before asOfTime
		if latestVersion == nil || createdAt.After(latestTime) {
			version, err := vs.GetVersion(policyID, versionID)
			if err == nil {
				latestVersion = version
				latestTime = createdAt
			}
		}

		return true
	})

	if latestVersion == nil {
		return nil, fmt.Errorf("no version found for %s as of %s", policyID, asOfTime)
	}

	return latestVersion, nil
}

// GetVersionByTag returns the version with a specific tag
func (vs *VersionStore) GetVersionByTag(policyID, tag string) (*Version, error) {
	startKey := storage.EncodeKey(PREFIX_VERSION_TAG, []storage.Value{
		storage.NewBytesValue([]byte(policyID)),
		storage.NewBytesValue([]byte(tag)),
	})

	var versionID string
	found := false

	vs.kv.Scan(startKey, func(key, val []byte) bool {
		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 3 {
			return true
		}

		// Check if still in same policy/tag
		if string(vals[0].Str) != policyID || string(vals[1].Str) != tag {
			return false
		}

		versionID = string(vals[2].Str)
		found = true
		return false // Found it, stop scanning
	})

	if !found {
		return nil, fmt.Errorf("no version found with tag %s for policy %s", tag, policyID)
	}

	return vs.GetVersion(policyID, versionID)
}

// ListVersions returns all versions for a policy, ordered by creation time
func (vs *VersionStore) ListVersions(policyID string, limit int) ([]*Version, error) {
	startKey := storage.EncodeKey(PREFIX_VERSION_TIME, []storage.Value{
		storage.NewBytesValue([]byte(policyID)),
	})

	var versions []*Version
	count := 0

	vs.kv.Scan(startKey, func(key, val []byte) bool {
		if limit > 0 && count >= limit {
			return false
		}

		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 3 {
			return true
		}

		// Check if still in same policy
		if string(vals[0].Str) != policyID {
			return false
		}

		versionID := string(vals[2].Str)
		version, err := vs.GetVersion(policyID, versionID)
		if err == nil {
			versions = append(versions, version)
			count++
		}

		return true
	})

	return versions, nil
}

// GetVersionHistory returns the complete version history for a policy
func (vs *VersionStore) GetVersionHistory(policyID string) (*VersionHistory, error) {
	versions, err := vs.ListVersions(policyID, 0) // 0 = no limit
	if err != nil {
		return nil, err
	}

	return &VersionHistory{
		PolicyID: policyID,
		Versions: versions,
	}, nil
}

// Helper functions

func parseVersionVals(vals []storage.Value) (*Version, error) {
	if len(vals) < 8 {
		return nil, fmt.Errorf("incomplete version data")
	}

	tags, err := decodeStringArray(vals[6].Str)
	if err != nil {
		tags = []string{}
	}

	metadata, err := decodeMetadata(vals[7].Str)
	if err != nil {
		metadata = make(map[string]string)
	}

	return &Version{
		PolicyID:    string(vals[0].Str),
		VersionID:   string(vals[1].Str),
		DocumentID:  string(vals[2].Str),
		CreatedAt:   vals[3].Time,
		CreatedBy:   string(vals[4].Str),
		Description: string(vals[5].Str),
		Tags:        tags,
		Metadata:    metadata,
	}, nil
}

func encodeStringArray(arr []string) []byte {
	if len(arr) == 0 {
		return []byte{}
	}

	result := []byte{}
	result = append(result, byte(len(arr)))
	for _, s := range arr {
		result = append(result, byte(len(s)))
		result = append(result, []byte(s)...)
	}
	return result
}

func decodeStringArray(data []byte) ([]string, error) {
	if len(data) == 0 {
		return []string{}, nil
	}

	pos := 0
	count := int(data[pos])
	pos++

	result := make([]string, 0, count)
	for i := 0; i < count; i++ {
		if pos >= len(data) {
			return nil, fmt.Errorf("incomplete string array")
		}

		length := int(data[pos])
		pos++

		if pos+length > len(data) {
			return nil, fmt.Errorf("incomplete string at pos %d", pos)
		}

		result = append(result, string(data[pos:pos+length]))
		pos += length
	}

	return result, nil
}

func encodeMetadata(m map[string]string) []byte {
	if len(m) == 0 {
		return []byte{}
	}

	result := []byte{byte(len(m))}
	for k, v := range m {
		result = append(result, byte(len(k)))
		result = append(result, []byte(k)...)
		result = append(result, byte(len(v)))
		result = append(result, []byte(v)...)
	}
	return result
}

func decodeMetadata(data []byte) (map[string]string, error) {
	if len(data) == 0 {
		return make(map[string]string), nil
	}

	pos := 0
	count := int(data[pos])
	pos++

	result := make(map[string]string)
	for i := 0; i < count; i++ {
		if pos >= len(data) {
			return nil, fmt.Errorf("incomplete metadata")
		}

		// Read key
		keyLen := int(data[pos])
		pos++
		if pos+keyLen > len(data) {
			return nil, fmt.Errorf("incomplete key at pos %d", pos)
		}
		key := string(data[pos : pos+keyLen])
		pos += keyLen

		// Read value
		if pos >= len(data) {
			return nil, fmt.Errorf("incomplete value for key %s", key)
		}
		valLen := int(data[pos])
		pos++
		if pos+valLen > len(data) {
			return nil, fmt.Errorf("incomplete value at pos %d", pos)
		}
		val := string(data[pos : pos+valLen])
		pos += valLen

		result[key] = val
	}

	return result, nil
}
