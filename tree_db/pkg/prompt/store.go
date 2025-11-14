// ABOUTME: Prompt store implementation for conversation management
// ABOUTME: Handles message storage and conversation retrieval

package prompt

import (
	"fmt"

	"github.com/nainya/treestore/pkg/storage"
)

// Prefixes for prompt storage
const (
	PREFIX_CONVERSATION        = uint32(8000)
	PREFIX_MESSAGE             = uint32(8100)
	PREFIX_CONVERSATION_USER   = uint32(8200) // Index by (userID, startedAt, conversationID)
	PREFIX_CONVERSATION_TIME   = uint32(8300) // Index by (startedAt, conversationID)
	PREFIX_CONVERSATION_TAG    = uint32(8400) // Index by (tag, conversationID)
	PREFIX_MESSAGE_CONV        = uint32(8500) // Index by (conversationID, timestamp, messageID)
)

// PromptStore manages conversations and messages
type PromptStore struct {
	kv *storage.KV
}

// NewPromptStore creates a new prompt store
func NewPromptStore(kv *storage.KV) *PromptStore {
	return &PromptStore{kv: kv}
}

// CreateConversation stores a new conversation
func (ps *PromptStore) CreateConversation(conv *Conversation) error {
	tx := ps.kv.Begin()

	// Primary key: conversationID
	key := storage.EncodeKey(PREFIX_CONVERSATION, []storage.Value{
		storage.NewBytesValue([]byte(conv.ConversationID)),
	})

	val := storage.EncodeValues([]storage.Value{
		storage.NewBytesValue([]byte(conv.ConversationID)),
		storage.NewBytesValue([]byte(conv.UserID)),
		storage.NewBytesValue([]byte(conv.Title)),
		storage.NewTimeValue(conv.StartedAt),
		storage.NewTimeValue(conv.LastMessageAt),
		storage.NewInt64Value(int64(conv.MessageCount)),
		storage.NewBytesValue(encodeStringArray(conv.Tags)),
		storage.NewBytesValue(encodeMetadata(conv.Metadata)),
	})

	tx.Set(key, val)

	// User index: (userID, startedAt, conversationID)
	userKey := storage.EncodeKey(PREFIX_CONVERSATION_USER, []storage.Value{
		storage.NewBytesValue([]byte(conv.UserID)),
		storage.NewTimeValue(conv.StartedAt),
		storage.NewBytesValue([]byte(conv.ConversationID)),
	})
	tx.Set(userKey, []byte{})

	// Time index: (startedAt, conversationID)
	timeKey := storage.EncodeKey(PREFIX_CONVERSATION_TIME, []storage.Value{
		storage.NewTimeValue(conv.StartedAt),
		storage.NewBytesValue([]byte(conv.ConversationID)),
	})
	tx.Set(timeKey, []byte{})

	// Tag indexes
	for _, tag := range conv.Tags {
		tagKey := storage.EncodeKey(PREFIX_CONVERSATION_TAG, []storage.Value{
			storage.NewBytesValue([]byte(tag)),
			storage.NewBytesValue([]byte(conv.ConversationID)),
		})
		tx.Set(tagKey, []byte{})
	}

	return tx.Commit()
}

// AddMessage appends a message to a conversation
func (ps *PromptStore) AddMessage(msg *Message) error {
	tx := ps.kv.Begin()

	// Primary key: messageID
	key := storage.EncodeKey(PREFIX_MESSAGE, []storage.Value{
		storage.NewBytesValue([]byte(msg.MessageID)),
	})

	val := storage.EncodeValues([]storage.Value{
		storage.NewBytesValue([]byte(msg.MessageID)),
		storage.NewBytesValue([]byte(msg.ConversationID)),
		storage.NewBytesValue([]byte(msg.Role)),
		storage.NewBytesValue([]byte(msg.Content)),
		storage.NewTimeValue(msg.Timestamp),
		storage.NewBytesValue(encodeMetadata(msg.Metadata)),
	})

	tx.Set(key, val)

	// Conversation message index: (conversationID, timestamp, messageID)
	convKey := storage.EncodeKey(PREFIX_MESSAGE_CONV, []storage.Value{
		storage.NewBytesValue([]byte(msg.ConversationID)),
		storage.NewTimeValue(msg.Timestamp),
		storage.NewBytesValue([]byte(msg.MessageID)),
	})
	tx.Set(convKey, []byte{})

	// Update conversation's last message time and count
	conv, err := ps.GetConversation(msg.ConversationID)
	if err == nil {
		conv.LastMessageAt = msg.Timestamp
		conv.MessageCount++
		ps.updateConversation(tx, conv)
	}

	return tx.Commit()
}

// GetConversation retrieves a conversation by ID
func (ps *PromptStore) GetConversation(conversationID string) (*Conversation, error) {
	key := storage.EncodeKey(PREFIX_CONVERSATION, []storage.Value{
		storage.NewBytesValue([]byte(conversationID)),
	})

	val, ok := ps.kv.Get(key)
	if !ok {
		return nil, fmt.Errorf("conversation not found: %s", conversationID)
	}

	vals, err := storage.DecodeValues(val)
	if err != nil {
		return nil, err
	}

	return parseConversationVals(vals)
}

// GetMessage retrieves a message by ID
func (ps *PromptStore) GetMessage(messageID string) (*Message, error) {
	key := storage.EncodeKey(PREFIX_MESSAGE, []storage.Value{
		storage.NewBytesValue([]byte(messageID)),
	})

	val, ok := ps.kv.Get(key)
	if !ok {
		return nil, fmt.Errorf("message not found: %s", messageID)
	}

	vals, err := storage.DecodeValues(val)
	if err != nil {
		return nil, err
	}

	return parseMessageVals(vals)
}

// GetMessages retrieves all messages for a conversation in chronological order
func (ps *PromptStore) GetMessages(conversationID string) ([]*Message, error) {
	startKey := storage.EncodeKey(PREFIX_MESSAGE_CONV, []storage.Value{
		storage.NewBytesValue([]byte(conversationID)),
	})

	var messages []*Message

	ps.kv.Scan(startKey, func(key, val []byte) bool {
		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 3 {
			return true
		}

		// Check if still in same conversation
		if string(vals[0].Str) != conversationID {
			return false
		}

		messageID := string(vals[2].Str)
		msg, err := ps.GetMessage(messageID)
		if err == nil {
			messages = append(messages, msg)
		}

		return true
	})

	return messages, nil
}

// GetConversationWithMessages retrieves a conversation with all its messages
func (ps *PromptStore) GetConversationWithMessages(conversationID string) (*ConversationWithMessages, error) {
	conv, err := ps.GetConversation(conversationID)
	if err != nil {
		return nil, err
	}

	messages, err := ps.GetMessages(conversationID)
	if err != nil {
		return nil, err
	}

	return &ConversationWithMessages{
		Conversation: conv,
		Messages:     messages,
	}, nil
}

// ListConversationsByUser retrieves conversations for a user
func (ps *PromptStore) ListConversationsByUser(userID string, limit int) ([]*Conversation, error) {
	startKey := storage.EncodeKey(PREFIX_CONVERSATION_USER, []storage.Value{
		storage.NewBytesValue([]byte(userID)),
	})

	var conversations []*Conversation
	count := 0

	ps.kv.Scan(startKey, func(key, val []byte) bool {
		if limit > 0 && count >= limit {
			return false
		}

		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 3 {
			return true
		}

		// Check if still in same user
		if string(vals[0].Str) != userID {
			return false
		}

		conversationID := string(vals[2].Str)
		conv, err := ps.GetConversation(conversationID)
		if err == nil {
			conversations = append(conversations, conv)
			count++
		}

		return true
	})

	return conversations, nil
}

// ListConversationsByTag retrieves conversations with a specific tag
func (ps *PromptStore) ListConversationsByTag(tag string, limit int) ([]*Conversation, error) {
	startKey := storage.EncodeKey(PREFIX_CONVERSATION_TAG, []storage.Value{
		storage.NewBytesValue([]byte(tag)),
	})

	var conversations []*Conversation
	count := 0

	ps.kv.Scan(startKey, func(key, val []byte) bool {
		if limit > 0 && count >= limit {
			return false
		}

		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 2 {
			return true
		}

		// Check if still in same tag
		if string(vals[0].Str) != tag {
			return false
		}

		conversationID := string(vals[1].Str)
		conv, err := ps.GetConversation(conversationID)
		if err == nil {
			conversations = append(conversations, conv)
			count++
		}

		return true
	})

	return conversations, nil
}

// DeleteConversation removes a conversation and all its messages
func (ps *PromptStore) DeleteConversation(conversationID string) error {
	// Get conversation first
	conv, err := ps.GetConversation(conversationID)
	if err != nil {
		return err
	}

	// Get all messages
	messages, err := ps.GetMessages(conversationID)
	if err != nil {
		return err
	}

	tx := ps.kv.Begin()

	// Delete all messages
	for _, msg := range messages {
		msgKey := storage.EncodeKey(PREFIX_MESSAGE, []storage.Value{
			storage.NewBytesValue([]byte(msg.MessageID)),
		})
		tx.Del(msgKey)

		convMsgKey := storage.EncodeKey(PREFIX_MESSAGE_CONV, []storage.Value{
			storage.NewBytesValue([]byte(msg.ConversationID)),
			storage.NewTimeValue(msg.Timestamp),
			storage.NewBytesValue([]byte(msg.MessageID)),
		})
		tx.Del(convMsgKey)
	}

	// Delete conversation
	convKey := storage.EncodeKey(PREFIX_CONVERSATION, []storage.Value{
		storage.NewBytesValue([]byte(conversationID)),
	})
	tx.Del(convKey)

	// Delete user index
	userKey := storage.EncodeKey(PREFIX_CONVERSATION_USER, []storage.Value{
		storage.NewBytesValue([]byte(conv.UserID)),
		storage.NewTimeValue(conv.StartedAt),
		storage.NewBytesValue([]byte(conversationID)),
	})
	tx.Del(userKey)

	// Delete time index
	timeKey := storage.EncodeKey(PREFIX_CONVERSATION_TIME, []storage.Value{
		storage.NewTimeValue(conv.StartedAt),
		storage.NewBytesValue([]byte(conversationID)),
	})
	tx.Del(timeKey)

	// Delete tag indexes
	for _, tag := range conv.Tags {
		tagKey := storage.EncodeKey(PREFIX_CONVERSATION_TAG, []storage.Value{
			storage.NewBytesValue([]byte(tag)),
			storage.NewBytesValue([]byte(conversationID)),
		})
		tx.Del(tagKey)
	}

	return tx.Commit()
}

// Helper functions

func (ps *PromptStore) updateConversation(tx *storage.KVTX, conv *Conversation) {
	key := storage.EncodeKey(PREFIX_CONVERSATION, []storage.Value{
		storage.NewBytesValue([]byte(conv.ConversationID)),
	})

	val := storage.EncodeValues([]storage.Value{
		storage.NewBytesValue([]byte(conv.ConversationID)),
		storage.NewBytesValue([]byte(conv.UserID)),
		storage.NewBytesValue([]byte(conv.Title)),
		storage.NewTimeValue(conv.StartedAt),
		storage.NewTimeValue(conv.LastMessageAt),
		storage.NewInt64Value(int64(conv.MessageCount)),
		storage.NewBytesValue(encodeStringArray(conv.Tags)),
		storage.NewBytesValue(encodeMetadata(conv.Metadata)),
	})

	tx.Set(key, val)
}

func parseConversationVals(vals []storage.Value) (*Conversation, error) {
	if len(vals) < 8 {
		return nil, fmt.Errorf("incomplete conversation data")
	}

	tags, _ := decodeStringArray(vals[6].Str)
	metadata, _ := decodeMetadata(vals[7].Str)

	return &Conversation{
		ConversationID: string(vals[0].Str),
		UserID:         string(vals[1].Str),
		Title:          string(vals[2].Str),
		StartedAt:      vals[3].Time,
		LastMessageAt:  vals[4].Time,
		MessageCount:   int(vals[5].I64),
		Tags:           tags,
		Metadata:       metadata,
	}, nil
}

func parseMessageVals(vals []storage.Value) (*Message, error) {
	if len(vals) < 6 {
		return nil, fmt.Errorf("incomplete message data")
	}

	metadata, _ := decodeMetadata(vals[5].Str)

	return &Message{
		MessageID:      string(vals[0].Str),
		ConversationID: string(vals[1].Str),
		Role:           string(vals[2].Str),
		Content:        string(vals[3].Str),
		Timestamp:      vals[4].Time,
		Metadata:       metadata,
	}, nil
}

func encodeStringArray(arr []string) []byte {
	if len(arr) == 0 {
		return []byte{}
	}

	result := []byte{byte(len(arr))}
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
