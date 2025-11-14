// ABOUTME: Tests for version management
// ABOUTME: Verifies temporal queries and version tracking

package version

import (
	"os"
	"testing"
	"time"

	"github.com/nainya/treestore/pkg/storage"
)

func setupTestVersionStore(t *testing.T) (*VersionStore, *storage.KV, string) {
	path := "/tmp/test_versionstore_" + t.Name() + ".db"
	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}

	vs := NewVersionStore(kv)
	return vs, kv, path
}

func TestCreateAndGetVersion(t *testing.T) {
	vs, kv, path := setupTestVersionStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	version := &Version{
		PolicyID:    "policy1",
		VersionID:   "v1.0.0",
		DocumentID:  "doc1",
		CreatedAt:   now,
		CreatedBy:   "user1",
		Description: "Initial version",
		Tags:        []string{"latest", "stable"},
		Metadata:    map[string]string{"source": "import"},
	}

	// Create version
	if err := vs.CreateVersion(version); err != nil {
		t.Fatalf("Failed to create version: %v", err)
	}

	// Retrieve version
	retrieved, err := vs.GetVersion("policy1", "v1.0.0")
	if err != nil {
		t.Fatalf("Failed to get version: %v", err)
	}

	if retrieved.VersionID != "v1.0.0" {
		t.Errorf("Expected v1.0.0, got %s", retrieved.VersionID)
	}

	if retrieved.DocumentID != "doc1" {
		t.Errorf("Expected doc1, got %s", retrieved.DocumentID)
	}

	if len(retrieved.Tags) != 2 {
		t.Errorf("Expected 2 tags, got %d", len(retrieved.Tags))
	}

	if retrieved.Metadata["source"] != "import" {
		t.Errorf("Expected metadata source=import, got %s", retrieved.Metadata["source"])
	}
}

func TestGetLatestVersion(t *testing.T) {
	vs, kv, path := setupTestVersionStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create multiple versions
	v1 := &Version{
		PolicyID:   "policy1",
		VersionID:  "v1.0.0",
		DocumentID: "doc1",
		CreatedAt:  now.Add(-2 * time.Hour),
		CreatedBy:  "user1",
	}

	v2 := &Version{
		PolicyID:   "policy1",
		VersionID:  "v2.0.0",
		DocumentID: "doc2",
		CreatedAt:  now.Add(-1 * time.Hour),
		CreatedBy:  "user1",
	}

	v3 := &Version{
		PolicyID:   "policy1",
		VersionID:  "v3.0.0",
		DocumentID: "doc3",
		CreatedAt:  now,
		CreatedBy:  "user1",
		Tags:       []string{"latest"},
	}

	vs.CreateVersion(v1)
	vs.CreateVersion(v2)
	vs.CreateVersion(v3)

	// Get latest
	latest, err := vs.GetLatestVersion("policy1")
	if err != nil {
		t.Fatalf("Failed to get latest version: %v", err)
	}

	if latest.VersionID != "v3.0.0" {
		t.Errorf("Expected v3.0.0 as latest, got %s", latest.VersionID)
	}
}

func TestGetVersionAsOf(t *testing.T) {
	vs, kv, path := setupTestVersionStore(t)
	defer os.Remove(path)
	defer kv.Close()

	baseTime := time.Now().Add(-3 * time.Hour)

	// Create versions at different times
	v1 := &Version{
		PolicyID:   "policy1",
		VersionID:  "v1.0.0",
		DocumentID: "doc1",
		CreatedAt:  baseTime,
		CreatedBy:  "user1",
	}

	v2 := &Version{
		PolicyID:   "policy1",
		VersionID:  "v2.0.0",
		DocumentID: "doc2",
		CreatedAt:  baseTime.Add(1 * time.Hour),
		CreatedBy:  "user1",
	}

	v3 := &Version{
		PolicyID:   "policy1",
		VersionID:  "v3.0.0",
		DocumentID: "doc3",
		CreatedAt:  baseTime.Add(2 * time.Hour),
		CreatedBy:  "user1",
	}

	vs.CreateVersion(v1)
	vs.CreateVersion(v2)
	vs.CreateVersion(v3)

	// Query as of time between v1 and v2
	asOf := baseTime.Add(30 * time.Minute)
	version, err := vs.GetVersionAsOf("policy1", asOf)
	if err != nil {
		t.Fatalf("Failed to get version as of: %v", err)
	}

	if version.VersionID != "v1.0.0" {
		t.Errorf("Expected v1.0.0, got %s", version.VersionID)
	}

	// Query as of time between v2 and v3
	asOf = baseTime.Add(90 * time.Minute)
	version, err = vs.GetVersionAsOf("policy1", asOf)
	if err != nil {
		t.Fatalf("Failed to get version as of: %v", err)
	}

	if version.VersionID != "v2.0.0" {
		t.Errorf("Expected v2.0.0, got %s", version.VersionID)
	}

	// Query as of current time (should get v3)
	asOf = time.Now()
	version, err = vs.GetVersionAsOf("policy1", asOf)
	if err != nil {
		t.Fatalf("Failed to get version as of: %v", err)
	}

	if version.VersionID != "v3.0.0" {
		t.Errorf("Expected v3.0.0, got %s", version.VersionID)
	}
}

func TestGetVersionByTag(t *testing.T) {
	vs, kv, path := setupTestVersionStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	v1 := &Version{
		PolicyID:   "policy1",
		VersionID:  "v1.0.0",
		DocumentID: "doc1",
		CreatedAt:  now.Add(-1 * time.Hour),
		CreatedBy:  "user1",
		Tags:       []string{"stable"},
	}

	v2 := &Version{
		PolicyID:   "policy1",
		VersionID:  "v2.0.0",
		DocumentID: "doc2",
		CreatedAt:  now,
		CreatedBy:  "user1",
		Tags:       []string{"latest", "beta"},
	}

	vs.CreateVersion(v1)
	vs.CreateVersion(v2)

	// Get by tag "stable"
	version, err := vs.GetVersionByTag("policy1", "stable")
	if err != nil {
		t.Fatalf("Failed to get version by tag: %v", err)
	}

	if version.VersionID != "v1.0.0" {
		t.Errorf("Expected v1.0.0, got %s", version.VersionID)
	}

	// Get by tag "latest"
	version, err = vs.GetVersionByTag("policy1", "latest")
	if err != nil {
		t.Fatalf("Failed to get version by tag: %v", err)
	}

	if version.VersionID != "v2.0.0" {
		t.Errorf("Expected v2.0.0, got %s", version.VersionID)
	}

	// Get by tag "beta"
	version, err = vs.GetVersionByTag("policy1", "beta")
	if err != nil {
		t.Fatalf("Failed to get version by tag: %v", err)
	}

	if version.VersionID != "v2.0.0" {
		t.Errorf("Expected v2.0.0, got %s", version.VersionID)
	}
}

func TestListVersions(t *testing.T) {
	vs, kv, path := setupTestVersionStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create 5 versions
	for i := 1; i <= 5; i++ {
		v := &Version{
			PolicyID:   "policy1",
			VersionID:  "v" + string(rune('0'+i)) + ".0.0",
			DocumentID: "doc" + string(rune('0'+i)),
			CreatedAt:  now.Add(time.Duration(i) * time.Minute),
			CreatedBy:  "user1",
		}
		vs.CreateVersion(v)
	}

	// List all versions
	versions, err := vs.ListVersions("policy1", 0)
	if err != nil {
		t.Fatalf("Failed to list versions: %v", err)
	}

	if len(versions) != 5 {
		t.Errorf("Expected 5 versions, got %d", len(versions))
	}

	// List with limit
	versions, err = vs.ListVersions("policy1", 3)
	if err != nil {
		t.Fatalf("Failed to list versions with limit: %v", err)
	}

	if len(versions) != 3 {
		t.Errorf("Expected 3 versions, got %d", len(versions))
	}
}

func TestGetVersionHistory(t *testing.T) {
	vs, kv, path := setupTestVersionStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create versions
	v1 := &Version{
		PolicyID:    "policy1",
		VersionID:   "v1.0.0",
		DocumentID:  "doc1",
		CreatedAt:   now.Add(-2 * time.Hour),
		CreatedBy:   "user1",
		Description: "Initial release",
	}

	v2 := &Version{
		PolicyID:    "policy1",
		VersionID:   "v2.0.0",
		DocumentID:  "doc2",
		CreatedAt:   now.Add(-1 * time.Hour),
		CreatedBy:   "user2",
		Description: "Major update",
	}

	vs.CreateVersion(v1)
	vs.CreateVersion(v2)

	// Get history
	history, err := vs.GetVersionHistory("policy1")
	if err != nil {
		t.Fatalf("Failed to get version history: %v", err)
	}

	if history.PolicyID != "policy1" {
		t.Errorf("Expected policy1, got %s", history.PolicyID)
	}

	if len(history.Versions) != 2 {
		t.Errorf("Expected 2 versions in history, got %d", len(history.Versions))
	}

	// Verify chronological order
	if history.Versions[0].VersionID != "v1.0.0" {
		t.Errorf("Expected v1.0.0 first, got %s", history.Versions[0].VersionID)
	}

	if history.Versions[1].VersionID != "v2.0.0" {
		t.Errorf("Expected v2.0.0 second, got %s", history.Versions[1].VersionID)
	}
}

func TestVersionNotFound(t *testing.T) {
	vs, kv, path := setupTestVersionStore(t)
	defer os.Remove(path)
	defer kv.Close()

	// Try to get non-existent version
	_, err := vs.GetVersion("policy1", "v99.0.0")
	if err == nil {
		t.Error("Expected error for non-existent version")
	}

	// Try to get latest when no versions exist
	_, err = vs.GetLatestVersion("nonexistent")
	if err == nil {
		t.Error("Expected error for policy with no versions")
	}

	// Try to get by non-existent tag
	_, err = vs.GetVersionByTag("policy1", "nonexistent")
	if err == nil {
		t.Error("Expected error for non-existent tag")
	}
}
