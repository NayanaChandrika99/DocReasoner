// ABOUTME: Prompt and conversation storage data model
// ABOUTME: Supports message history and conversation retrieval

package prompt

import "time"

// Message represents a single message in a conversation
type Message struct {
	MessageID     string            // Unique message identifier
	ConversationID string           // Parent conversation ID
	Role          string            // Role: "user", "assistant", "system"
	Content       string            // Message content
	Timestamp     time.Time         // Message timestamp
	Metadata      map[string]string // Additional metadata
}

// Conversation represents a conversation thread
type Conversation struct {
	ConversationID string            // Unique conversation identifier
	UserID         string            // User identifier
	Title          string            // Conversation title
	StartedAt      time.Time         // Conversation start time
	LastMessageAt  time.Time         // Last message timestamp
	MessageCount   int               // Total message count
	Tags           []string          // Conversation tags
	Metadata       map[string]string // Additional metadata
}

// ConversationWithMessages includes full message history
type ConversationWithMessages struct {
	Conversation *Conversation
	Messages     []*Message
}

// ConversationQuery options for querying conversations
type ConversationQuery struct {
	UserID         *string   // Filter by user
	Tag            *string   // Filter by tag
	StartTime      *time.Time // Conversations started after
	EndTime        *time.Time // Conversations started before
	Limit          int       // Maximum results
	IncludeMessages bool     // Include message history
}
