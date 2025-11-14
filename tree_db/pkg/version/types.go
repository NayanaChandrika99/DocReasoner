// ABOUTME: Version management data model
// ABOUTME: Supports temporal queries and version tracking

package version

import "time"

// Version represents a document version snapshot
type Version struct {
	PolicyID    string    // Policy identifier
	VersionID   string    // Version identifier (semantic version or timestamp-based)
	DocumentID  string    // Reference to document
	CreatedAt   time.Time // Version creation time
	CreatedBy   string    // User/system that created version
	Description string    // Version description/changelog
	Tags        []string  // Version tags (e.g., "latest", "stable", "draft")
	Metadata    map[string]string
}

// VersionQuery options for temporal queries
type VersionQuery struct {
	PolicyID  string
	AsOfTime  *time.Time // Get version as of this time
	VersionID *string    // Get specific version
	Tag       *string    // Get version by tag
}

// VersionHistory represents the timeline of versions
type VersionHistory struct {
	PolicyID string
	Versions []*Version
}
