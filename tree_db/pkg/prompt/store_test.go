// ABOUTME: Tests for prompt/conversation storage
// ABOUTME: Verifies message and conversation management

package prompt

import (
	"os"
	"testing"
	"time"

	"github.com/nainya/treestore/pkg/storage"
)

func setupTestPromptStore(t *testing.T) (*PromptStore, *storage.KV, string) {
	path := "/tmp/test_promptstore_" + t.Name() + ".db"
	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}

	ps := NewPromptStore(kv)
	return ps, kv, path
}

func TestCreateAndGetConversation(t *testing.T) {
	ps, kv, path := setupTestPromptStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	conv := &Conversation{
		ConversationID: "conv1",
		UserID:         "user1",
		Title:          "Test Conversation",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
		Tags:           []string{"test", "demo"},
		Metadata:       map[string]string{"source": "test"},
	}

	// Create conversation
	if err := ps.CreateConversation(conv); err != nil {
		t.Fatalf("Failed to create conversation: %v", err)
	}

	// Retrieve conversation
	retrieved, err := ps.GetConversation("conv1")
	if err != nil {
		t.Fatalf("Failed to get conversation: %v", err)
	}

	if retrieved.ConversationID != "conv1" {
		t.Errorf("Expected conv1, got %s", retrieved.ConversationID)
	}

	if retrieved.UserID != "user1" {
		t.Errorf("Expected user1, got %s", retrieved.UserID)
	}

	if len(retrieved.Tags) != 2 {
		t.Errorf("Expected 2 tags, got %d", len(retrieved.Tags))
	}
}

func TestAddAndGetMessage(t *testing.T) {
	ps, kv, path := setupTestPromptStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create conversation first
	conv := &Conversation{
		ConversationID: "conv1",
		UserID:         "user1",
		Title:          "Test",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
	}
	ps.CreateConversation(conv)

	// Add message
	msg := &Message{
		MessageID:      "msg1",
		ConversationID: "conv1",
		Role:           "user",
		Content:        "Hello, world!",
		Timestamp:      now,
		Metadata:       map[string]string{"type": "text"},
	}

	if err := ps.AddMessage(msg); err != nil {
		t.Fatalf("Failed to add message: %v", err)
	}

	// Retrieve message
	retrieved, err := ps.GetMessage("msg1")
	if err != nil {
		t.Fatalf("Failed to get message: %v", err)
	}

	if retrieved.Content != "Hello, world!" {
		t.Errorf("Expected 'Hello, world!', got '%s'", retrieved.Content)
	}

	if retrieved.Role != "user" {
		t.Errorf("Expected role='user', got '%s'", retrieved.Role)
	}

	// Verify conversation was updated
	conv, err = ps.GetConversation("conv1")
	if err != nil {
		t.Fatalf("Failed to get updated conversation: %v", err)
	}

	if conv.MessageCount != 1 {
		t.Errorf("Expected message count=1, got %d", conv.MessageCount)
	}
}

func TestGetMessages(t *testing.T) {
	ps, kv, path := setupTestPromptStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create conversation
	conv := &Conversation{
		ConversationID: "conv1",
		UserID:         "user1",
		Title:          "Test",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
	}
	ps.CreateConversation(conv)

	// Add multiple messages
	messages := []*Message{
		{
			MessageID:      "msg1",
			ConversationID: "conv1",
			Role:           "user",
			Content:        "First message",
			Timestamp:      now,
		},
		{
			MessageID:      "msg2",
			ConversationID: "conv1",
			Role:           "assistant",
			Content:        "Second message",
			Timestamp:      now.Add(1 * time.Minute),
		},
		{
			MessageID:      "msg3",
			ConversationID: "conv1",
			Role:           "user",
			Content:        "Third message",
			Timestamp:      now.Add(2 * time.Minute),
		},
	}

	for _, msg := range messages {
		ps.AddMessage(msg)
	}

	// Get all messages
	retrieved, err := ps.GetMessages("conv1")
	if err != nil {
		t.Fatalf("Failed to get messages: %v", err)
	}

	if len(retrieved) != 3 {
		t.Errorf("Expected 3 messages, got %d", len(retrieved))
	}

	// Verify chronological order
	if retrieved[0].MessageID != "msg1" {
		t.Errorf("Expected msg1 first, got %s", retrieved[0].MessageID)
	}

	if retrieved[2].MessageID != "msg3" {
		t.Errorf("Expected msg3 last, got %s", retrieved[2].MessageID)
	}
}

func TestGetConversationWithMessages(t *testing.T) {
	ps, kv, path := setupTestPromptStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create conversation
	conv := &Conversation{
		ConversationID: "conv1",
		UserID:         "user1",
		Title:          "Test Conversation",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
	}
	ps.CreateConversation(conv)

	// Add messages
	ps.AddMessage(&Message{
		MessageID:      "msg1",
		ConversationID: "conv1",
		Role:           "user",
		Content:        "Hello",
		Timestamp:      now,
	})

	ps.AddMessage(&Message{
		MessageID:      "msg2",
		ConversationID: "conv1",
		Role:           "assistant",
		Content:        "Hi there!",
		Timestamp:      now.Add(1 * time.Minute),
	})

	// Get conversation with messages
	result, err := ps.GetConversationWithMessages("conv1")
	if err != nil {
		t.Fatalf("Failed to get conversation with messages: %v", err)
	}

	if result.Conversation.ConversationID != "conv1" {
		t.Errorf("Expected conv1, got %s", result.Conversation.ConversationID)
	}

	if len(result.Messages) != 2 {
		t.Errorf("Expected 2 messages, got %d", len(result.Messages))
	}
}

func TestListConversationsByUser(t *testing.T) {
	ps, kv, path := setupTestPromptStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create conversations for different users
	convs := []*Conversation{
		{
			ConversationID: "conv1",
			UserID:         "user1",
			Title:          "Conv 1",
			StartedAt:      now.Add(-2 * time.Hour),
			LastMessageAt:  now.Add(-2 * time.Hour),
			MessageCount:   0,
		},
		{
			ConversationID: "conv2",
			UserID:         "user1",
			Title:          "Conv 2",
			StartedAt:      now.Add(-1 * time.Hour),
			LastMessageAt:  now.Add(-1 * time.Hour),
			MessageCount:   0,
		},
		{
			ConversationID: "conv3",
			UserID:         "user2",
			Title:          "Conv 3",
			StartedAt:      now,
			LastMessageAt:  now,
			MessageCount:   0,
		},
	}

	for _, c := range convs {
		ps.CreateConversation(c)
	}

	// List conversations for user1
	user1Convs, err := ps.ListConversationsByUser("user1", 0)
	if err != nil {
		t.Fatalf("Failed to list conversations: %v", err)
	}

	if len(user1Convs) != 2 {
		t.Errorf("Expected 2 conversations for user1, got %d", len(user1Convs))
	}

	// List conversations for user2
	user2Convs, err := ps.ListConversationsByUser("user2", 0)
	if err != nil {
		t.Fatalf("Failed to list conversations: %v", err)
	}

	if len(user2Convs) != 1 {
		t.Errorf("Expected 1 conversation for user2, got %d", len(user2Convs))
	}
}

func TestListConversationsByTag(t *testing.T) {
	ps, kv, path := setupTestPromptStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create conversations with different tags
	convs := []*Conversation{
		{
			ConversationID: "conv1",
			UserID:         "user1",
			Title:          "Conv 1",
			StartedAt:      now,
			LastMessageAt:  now,
			MessageCount:   0,
			Tags:           []string{"work", "important"},
		},
		{
			ConversationID: "conv2",
			UserID:         "user1",
			Title:          "Conv 2",
			StartedAt:      now,
			LastMessageAt:  now,
			MessageCount:   0,
			Tags:           []string{"work"},
		},
		{
			ConversationID: "conv3",
			UserID:         "user1",
			Title:          "Conv 3",
			StartedAt:      now,
			LastMessageAt:  now,
			MessageCount:   0,
			Tags:           []string{"personal"},
		},
	}

	for _, c := range convs {
		ps.CreateConversation(c)
	}

	// List conversations with "work" tag
	workConvs, err := ps.ListConversationsByTag("work", 0)
	if err != nil {
		t.Fatalf("Failed to list conversations by tag: %v", err)
	}

	if len(workConvs) != 2 {
		t.Errorf("Expected 2 conversations with 'work' tag, got %d", len(workConvs))
	}

	// List conversations with "important" tag
	importantConvs, err := ps.ListConversationsByTag("important", 0)
	if err != nil {
		t.Fatalf("Failed to list conversations by tag: %v", err)
	}

	if len(importantConvs) != 1 {
		t.Errorf("Expected 1 conversation with 'important' tag, got %d", len(importantConvs))
	}
}

func TestDeleteConversation(t *testing.T) {
	ps, kv, path := setupTestPromptStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create conversation
	conv := &Conversation{
		ConversationID: "conv1",
		UserID:         "user1",
		Title:          "Test",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
	}
	ps.CreateConversation(conv)

	// Add messages
	ps.AddMessage(&Message{
		MessageID:      "msg1",
		ConversationID: "conv1",
		Role:           "user",
		Content:        "Hello",
		Timestamp:      now,
	})

	ps.AddMessage(&Message{
		MessageID:      "msg2",
		ConversationID: "conv1",
		Role:           "assistant",
		Content:        "Hi",
		Timestamp:      now.Add(1 * time.Minute),
	})

	// Delete conversation
	if err := ps.DeleteConversation("conv1"); err != nil {
		t.Fatalf("Failed to delete conversation: %v", err)
	}

	// Verify conversation is deleted
	_, err := ps.GetConversation("conv1")
	if err == nil {
		t.Error("Expected error for deleted conversation")
	}

	// Verify messages are deleted
	_, err = ps.GetMessage("msg1")
	if err == nil {
		t.Error("Expected error for deleted message")
	}

	_, err = ps.GetMessage("msg2")
	if err == nil {
		t.Error("Expected error for deleted message")
	}
}

func TestConversationNotFound(t *testing.T) {
	ps, kv, path := setupTestPromptStore(t)
	defer os.Remove(path)
	defer kv.Close()

	// Try to get non-existent conversation
	_, err := ps.GetConversation("nonexistent")
	if err == nil {
		t.Error("Expected error for non-existent conversation")
	}

	// Try to get non-existent message
	_, err = ps.GetMessage("nonexistent")
	if err == nil {
		t.Error("Expected error for non-existent message")
	}
}
