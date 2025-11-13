# Getting Started with TreeStore

This guide will help you begin implementing TreeStore from scratch, including all four specialized stores (DocumentStore, VersionStore, MetadataStore, PromptStore).

---

## Prerequisites

### Required Software
- **Go 1.21+** - [Install Go](https://go.dev/doc/install)
- **Protocol Buffers Compiler** - For gRPC code generation
  ```bash
  # macOS
  brew install protobuf
  brew install protoc-gen-go
  brew install protoc-gen-go-grpc
  
  # Linux
  apt-get install -y protobuf-compiler
  go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
  go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
  ```
- **Git** - Version control
- **Make** - Build automation
- **Docker** (optional) - For containerization

### Recommended Tools
- **Go IDE** - VS Code with Go extension, GoLand, or Vim with go plugins
- **grpcurl** - Test gRPC APIs: `brew install grpcurl`
- **Prometheus + Grafana** (later) - Observability
- **Python 3.9+** - For testing integration with reasoning-service

### Knowledge Prerequisites
- Go programming basics
- Basic understanding of databases
- Familiarity with trees (binary trees, at least)
- gRPC concepts (learn as you go is fine)
- Understanding of your ReAct controller tools (pi_search, temporal_lookup, etc.)

---

## Step 1: Initial Setup

### Create Project Structure

```bash
cd /Users/nainy/Documents/Personal/reasoning-service/tree_db

# Initialize Go module
go mod init github.com/yourusername/treestore

# Create directory structure (including new stores)
mkdir -p pkg/{btree,storage,wal,index,txn,document,version,metadata,prompt,fts,api,kv}
mkdir -p internal/{config,metrics,util}
mkdir -p cmd/treestore
mkdir -p test/{unit,integration,benchmark,testdata}
mkdir -p proto
mkdir -p client/python/treestore
mkdir -p scripts
mkdir -p docs/{api,deployment,development}
mkdir -p deploy/{docker,k8s,systemd}

echo "✅ Directory structure created (with extended stores)!"
```

### Create Initial Files

```bash
# Makefile
cat > Makefile << 'EOF'
.PHONY: all build test clean

all: build

build:
	@echo "Building TreeStore..."
	go build -o build/bin/treestore cmd/treestore/main.go

test:
	@echo "Running tests..."
	go test ./... -v -cover

test-unit:
	go test ./pkg/... -v -short

test-integration:
	go test ./test/integration/... -v

bench:
	go test ./test/benchmark/... -bench=. -benchmem

fmt:
	go fmt ./...

lint:
	golangci-lint run

clean:
	rm -rf build/
	rm -rf data/

run:
	go run cmd/treestore/main.go
EOF

# .gitignore
cat > .gitignore << 'EOF'
# Binaries
build/
*.exe
*.dll
*.so
*.dylib

# Test
*.test
*.prof
*.out
coverage.txt

# Data
data/
*.db
*.log
*.wal

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Generated
*.pb.go
*_pb2.py
EOF

echo "✅ Initial files created!"
```

---

## Step 2: Study the Book

Before writing code, read the foundational material:

### Week 1 Reading
1. **Build Your Own Database** - Chapters 1-3
   - Introduction
   - From Files To Databases
   - Indexing Data Structures

2. **Understand B+Trees**
   - How they differ from B-Trees
   - Internal vs leaf nodes
   - Splitting and merging

### Take Notes
Create a `notes.md` file:

```bash
cat > notes.md << 'EOF'
# Learning Notes

## Week 1: B+Tree Fundamentals

### Key Concepts
- [ ] B+Tree vs B-Tree
- [ ] Node structure (internal vs leaf)
- [ ] Insertion algorithm
- [ ] Splitting logic
- [ ] Fanout calculations

### Questions
- What's optimal page size?
- How to handle variable-length values?
- When to split vs when to merge?

### References
- Build Your Own Database, Ch 5
- [Link to other resources]
EOF
```

---

## Step 3: Week 1 - Implement Basic B+Tree

### Day 1-2: Node Structure

Create `pkg/btree/node.go`:

```go
package btree

import (
	"bytes"
)

// Node represents a B+Tree node
type Node struct {
	isLeaf   bool
	keys     [][]byte   // Keys (sorted)
	values   [][]byte   // Values (leaf nodes only)
	children []*Node    // Child pointers (internal nodes only)
	next     *Node      // Next leaf pointer (leaf nodes only)
	parent   *Node      // Parent pointer (for traversal)
}

// NewLeafNode creates a new leaf node
func NewLeafNode() *Node {
	return &Node{
		isLeaf: true,
		keys:   make([][]byte, 0),
		values: make([][]byte, 0),
	}
}

// NewInternalNode creates a new internal node
func NewInternalNode() *Node {
	return &Node{
		isLeaf:   false,
		keys:     make([][]byte, 0),
		children: make([]*Node, 0),
	}
}

// Find returns the index where key should be inserted/found
func (n *Node) Find(key []byte) int {
	// Binary search
	left, right := 0, len(n.keys)
	for left < right {
		mid := (left + right) / 2
		cmp := bytes.Compare(key, n.keys[mid])
		if cmp < 0 {
			right = mid
		} else if cmp > 0 {
			left = mid + 1
		} else {
			return mid
		}
	}
	return left
}

// IsFull checks if node needs splitting
func (n *Node) IsFull(maxKeys int) bool {
	return len(n.keys) >= maxKeys
}
```

**Task:** Complete the node structure and write tests.

```bash
# Create test file
cat > pkg/btree/node_test.go << 'EOF'
package btree

import (
	"testing"
)

func TestNewLeafNode(t *testing.T) {
	node := NewLeafNode()
	if !node.isLeaf {
		t.Error("Expected leaf node")
	}
	if len(node.keys) != 0 {
		t.Error("Expected empty keys")
	}
}

func TestNodeFind(t *testing.T) {
	node := NewLeafNode()
	node.keys = [][]byte{
		[]byte("a"),
		[]byte("c"),
		[]byte("e"),
	}
	
	tests := []struct {
		key      []byte
		expected int
	}{
		{[]byte("a"), 0},
		{[]byte("b"), 1},
		{[]byte("d"), 2},
		{[]byte("f"), 3},
	}
	
	for _, tt := range tests {
		idx := node.Find(tt.key)
		if idx != tt.expected {
			t.Errorf("Find(%s) = %d, want %d", tt.key, idx, tt.expected)
		}
	}
}
EOF

# Run tests
go test ./pkg/btree/... -v
```

### Day 3-4: B+Tree Structure and Insert

Create `pkg/btree/btree.go`:

```go
package btree

import (
	"bytes"
	"fmt"
)

const (
	DefaultMaxKeys = 100  // Max keys per node
)

type BTree struct {
	root    *Node
	maxKeys int
	size    int  // Total number of key-value pairs
}

func NewBTree(maxKeys int) *BTree {
	if maxKeys < 3 {
		maxKeys = DefaultMaxKeys
	}
	return &BTree{
		root:    NewLeafNode(),
		maxKeys: maxKeys,
		size:    0,
	}
}

// Get retrieves a value by key
func (bt *BTree) Get(key []byte) ([]byte, error) {
	node := bt.findLeaf(key)
	idx := node.Find(key)
	
	if idx < len(node.keys) && bytes.Equal(node.keys[idx], key) {
		return node.values[idx], nil
	}
	
	return nil, fmt.Errorf("key not found")
}

// findLeaf returns the leaf node that should contain the key
func (bt *BTree) findLeaf(key []byte) *Node {
	node := bt.root
	
	for !node.isLeaf {
		idx := node.Find(key)
		if idx >= len(node.children) {
			idx = len(node.children) - 1
		}
		node = node.children[idx]
	}
	
	return node
}

// Insert adds or updates a key-value pair
func (bt *BTree) Insert(key, value []byte) error {
	// TODO: Implement insertion with splitting
	// Hint: Follow the book's algorithm
	return fmt.Errorf("not implemented")
}
```

**Your task:** Implement the `Insert` method following the book.

### Day 5: Test Your B+Tree

```go
// pkg/btree/btree_test.go
func TestBTreeInsertAndGet(t *testing.T) {
	bt := NewBTree(5)
	
	// Insert some data
	bt.Insert([]byte("key1"), []byte("value1"))
	bt.Insert([]byte("key2"), []byte("value2"))
	bt.Insert([]byte("key3"), []byte("value3"))
	
	// Retrieve data
	val, err := bt.Get([]byte("key2"))
	if err != nil {
		t.Fatalf("Get failed: %v", err)
	}
	if string(val) != "value2" {
		t.Errorf("Expected value2, got %s", val)
	}
}

func TestBTreeSplitting(t *testing.T) {
	bt := NewBTree(3)  // Small max keys to force splits
	
	// Insert enough to cause splits
	for i := 0; i < 10; i++ {
		key := []byte(fmt.Sprintf("key%02d", i))
		val := []byte(fmt.Sprintf("val%02d", i))
		err := bt.Insert(key, val)
		if err != nil {
			t.Fatalf("Insert failed: %v", err)
		}
	}
	
	// Verify all values
	for i := 0; i < 10; i++ {
		key := []byte(fmt.Sprintf("key%02d", i))
		val, err := bt.Get(key)
		if err != nil {
			t.Errorf("Failed to get %s: %v", key, err)
		}
		expected := []byte(fmt.Sprintf("val%02d", i))
		if !bytes.Equal(val, expected) {
			t.Errorf("Got %s, expected %s", val, expected)
		}
	}
}
```

---

## Step 4: Track Your Progress

Use the provided `PROGRESS.md` file to track completion:

```bash
# Mark tasks complete as you go
vim PROGRESS.md  # or your preferred editor
```

---

## Daily Development Workflow

### Morning Routine
1. Review yesterday's code
2. Read relevant book chapter
3. Plan today's tasks
4. Write tests first (TDD style)

### During Development
```bash
# Run tests frequently
make test

# Check formatting
make fmt

# Benchmark performance
make bench
```

### Evening Routine
1. Commit your code
   ```bash
   git add .
   git commit -m "Week 1 Day X: Implemented Y"
   ```
2. Update progress tracker
3. Note any blockers or questions

---

## Getting Help

### When Stuck

1. **Read the book again** - Often the answer is there
2. **Check reference implementations**
   ```bash
   # Clone for reference only
   cd ~/references
   git clone https://github.com/hashicorp/go-memdb
   git clone https://github.com/dgraph-io/badger
   ```
3. **Debug systematically**
   ```bash
   # Add logging
   import "log"
   log.Printf("Node state: %+v", node)
   
   # Use Go debugger
   go install github.com/go-delve/delve/cmd/dlv@latest
   dlv test ./pkg/btree -- -test.run TestInsert
   ```

### Resources
- [Go Documentation](https://go.dev/doc/)
- [Build Your Own Database](https://build-your-own.org/database/)
- [Database Internals Book](https://www.databass.dev/)

---

## Implementation Phases Overview

### **Phase 1: Core Database (Weeks 1-3)**
Focus: B+Tree, WAL, transactions - the foundation

### **Phase 2: Document Layer (Weeks 4-6)**
Focus: Secondary indexes, document operations, full-text search

### **Phase 3: Extended Stores (Weeks 7-9)** 🆕
Focus: VersionStore, MetadataStore, PromptStore for tool support

### **Phase 4: API & Integration (Weeks 10-11)**
Focus: gRPC API, Python client, integration with reasoning-service

### **Phase 5: Production (Weeks 12-13)**
Focus: Observability, optimization, deployment

---

## Week 1 Checklist

Track your progress:

- [ ] **Day 1:** Setup complete, read chapters 1-3, understand extended architecture
- [ ] **Day 2:** Node structure implemented with tests
- [ ] **Day 3:** Basic Insert logic (without splitting)
- [ ] **Day 4:** Splitting logic implemented
- [ ] **Day 5:** All insertion tests passing
- [ ] **Weekend:** Review, refactor, understand how stores will integrate

---

## Common Pitfalls to Avoid

### 1. Don't Skip Tests
❌ "I'll write tests later"  
✅ Write tests as you code (TDD)

### 2. Don't Optimize Prematurely
❌ Worrying about performance on Day 1  
✅ Make it work, then make it fast

### 3. Don't Copy-Paste Blindly
❌ Copying code without understanding  
✅ Type it out, understand each line

### 4. Don't Skip the Book
❌ "I'll figure it out myself"  
✅ Stand on the shoulders of giants

---

## Success Metrics for Week 1

By end of Week 1, you should have:
- [ ] Working B+Tree with Insert and Get
- [ ] At least 10 unit tests passing
- [ ] Basic benchmarks showing performance
- [ ] Code committed to Git
- [ ] Notes documenting your learning

---

## Extended Features Preview

### Week 7: VersionStore (Temporal Queries)

After completing core B+Tree, you'll add temporal query support:

```go
// pkg/version/store.go
package version

type VersionStore struct {
    btree *BTree  // Reuse your B+Tree!
}

// Key insight: Same B+Tree, different key encoding
// Key format: (policy_id, effective_date, version_id)
func (vs *VersionStore) GetVersionAsOf(
    policyID string,
    asOfDate time.Time,
) (*PolicyVersion, error) {
    // Range scan to find version effective on date
    startKey := encodeKey(policyID, time.Time{}, "")
    endKey := encodeKey(policyID, asOfDate, "~")
    
    iter := vs.btree.RangeScan(startKey, endKey)
    return getLastVersion(iter), nil
}
```

**Why this is cool:** You're reusing the B+Tree you built in Weeks 1-3!

### Week 8: MetadataStore (Tool Results)

Store outputs from your ReAct tools:

```go
// pkg/metadata/trajectory.go
package metadata

type SearchTrajectory struct {
    CaseID       string
    Query        string
    NodesVisited []string
    Thinking     string
    Confidence   float64
}

func (ms *MetadataStore) StoreTrajectory(
    traj *SearchTrajectory,
) error {
    key := encodeKey(traj.CaseID, traj.Timestamp)
    value := serialize(traj)
    return ms.btree.Insert(key, value)
}
```

**Why this is cool:** Same B+Tree infrastructure, different data model!

### Week 9: PromptStore (Versioning)

Track which prompts produced which decisions:

```go
// pkg/prompt/store.go
package prompt

func (ps *PromptStore) RecordUsage(
    caseID string,
    promptID string,
    version string,
) error {
    usage := &PromptUsage{
        CaseID:    caseID,
        PromptID:  promptID,
        Version:   version,
        Timestamp: time.Now(),
    }
    return ps.btree.Insert(encodeKey(usage), serialize(usage))
}
```

**Pattern recognition:** Everything uses the same B+Tree primitives you build in Phase 1!

---

## Integration Testing with Your Tools

### Test pi_search Tool Integration

```go
// test/integration/tool_pi_search_test.go
func TestPiSearchToolIntegration(t *testing.T) {
    // 1. Store PageIndex document
    client.StoreDocument(policyID, tree)
    
    // 2. Perform tree search (simulating pi_search tool)
    nodes := client.GetSubtree(policyID, rootNodeID, 2)
    
    // 3. Store trajectory
    client.StoreTrajectory(&SearchTrajectory{
        CaseID:       "test_case",
        Query:        "What are age requirements?",
        NodesVisited: selectedNodeIDs,
        Thinking:     "Age is typically in eligibility section...",
    })
    
    // 4. Verify retrieval
    trajectories := client.GetTrajectories("test_case")
    assert.Equal(t, 1, len(trajectories))
}
```

### Test temporal_lookup Tool Integration

```go
// test/integration/tool_temporal_lookup_test.go
func TestTemporalLookupToolIntegration(t *testing.T) {
    // Store multiple versions
    client.StoreDocument(policyID, "2023-01", tree_v1)
    client.StoreDocument(policyID, "2024-01", tree_v2)
    
    // Query as of specific date (simulating temporal_lookup tool)
    version := client.GetVersionAsOf(policyID, "2023-06-15")
    
    assert.Equal(t, "2023-01", version.VersionID)
}
```

### Test policy_xref Tool Integration

```go
// test/integration/tool_policy_xref_test.go
func TestPolicyXrefToolIntegration(t *testing.T) {
    // Store cross-references
    client.StoreCrossReference(&CrossReference{
        FromNodeID:   "0042",
        ToNodeID:     "0087",
        RelationType: "see_also",
        Reason:       "Related eligibility criteria",
    })
    
    // Query cross-references (simulating policy_xref tool)
    refs := client.GetCrossReferences(policyID, "0042")
    
    assert.Equal(t, 1, len(refs))
    assert.Equal(t, "0087", refs[0].ToNodeID)
}
```

---

## Next Steps

### **Immediate (This Week):**
1. Review IMPLEMENTATION_PLAN.md for Week 1 details
2. Read "Build Your Own Database" Chapters 1-3
3. Set up development environment
4. Start implementing Node structure

### **After Week 3 (Core Complete):**
1. Review how DocumentStore uses your B+Tree
2. Plan secondary indexes (Week 4)
3. Understand how extended stores will reuse same infrastructure

### **After Week 6 (Document Layer Complete):**
1. Design VersionStore key encoding
2. Plan MetadataStore schema
3. Sketch PromptStore integration

### **Key Insight:**
The hard work is Weeks 1-3 (B+Tree, WAL, transactions). Everything else is **applying** that foundation to different use cases!

**Remember:** This is a marathon, not a sprint. Take your time to understand deeply. The extended stores (Weeks 7-9) are easier because you're reusing what you built in Weeks 1-6!

---

## Questions?

Create an `issues.md` file to track questions:

```bash
cat > issues.md << 'EOF'
# Issues and Questions

## Week 1

### Q1: How to handle variable-length keys?
Status: Open
Ideas: Prefix with length, or use fixed-size pages with overflow

### Q2: What's the optimal fanout for 4KB pages?
Status: Researching
Notes: Depends on key/value sizes
EOF
```

Good luck! 🚀

