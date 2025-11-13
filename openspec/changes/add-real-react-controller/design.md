# Design: Real ReAct Controller

## Context

The current ReActController in `src/reasoning_service/services/controller.py` implements a fixed workflow:
1. Think (heuristic query extraction)
2. Retrieve (call RetrievalService)
3. Read (string matching for requirements)
4. Link Evidence (simple containment checks)
5. Decide (rule-based status determination)

This approach lacks the dynamic reasoning capabilities specified in `docs/plan.md`, which calls for an LLM-powered agent that adapts its strategy per case and generates actual reasoning traces.

The project uses PageIndex for policy retrieval (LLM Tree Search) and has a well-defined schema (`CriterionResult`, `CaseBundle`, `ReasoningStep`) that we must maintain compatibility with.

## Goals

- **LLM-driven reasoning**: Replace hard-coded logic with actual LLM reasoning about policy verification
- **Dynamic tool selection**: LLM decides which tools to call and when, not a fixed sequence
- **Production-ready**: Error handling, monitoring, cost controls, fallback mechanisms
- **Backward compatible**: API contracts remain unchanged during migration
- **Auditable**: Complete reasoning traces showing LLM's thought process

## Non-Goals

- **Not replacing retrieval service**: PageIndex integration remains unchanged
- **Not changing API contracts**: `CriterionResult` schema stays the same
- **Not unifying sync/async controllers immediately**: Keep both paths initially, align later
- **Not implementing streaming**: Defer to future optimization phase
- **Not adding new retrieval methods**: Focus on controller reasoning, not retrieval

## Decisions

### Decision: Function Calling Format

**What**: Use OpenAI function calling format as the primary interface, with adapters for Anthropic and vLLM.

**Why**: 
- OpenAI format is well-documented and widely supported
- Most OSS models (via vLLM) support OpenAI-compatible APIs
- Anthropic has clear mapping to OpenAI format
- Enables strict JSON schema validation

**Alternatives considered**:
- Text-based tool calling: Less structured, harder to validate
- LangChain tool abstraction: Adds dependency, overkill for our needs
- Custom format: Non-standard, harder to maintain

### Decision: Tool Calling vs Text-Based

**What**: Use structured function calling rather than text-based tool invocation.

**Why**:
- Guarantees structured outputs (JSON schemas)
- Easier to validate and parse
- Better error handling (invalid schemas caught early)
- Clearer reasoning traces (explicit tool calls vs text parsing)

**Trade-offs**:
- Requires models with function calling support (most modern models have this)
- Slightly more complex implementation

### Decision: Message History Management

**What**: Track full conversation history including system prompt, user prompt, assistant messages with tool calls, and tool result messages.

**Why**:
- LLM needs context of previous tool calls to reason effectively
- Enables multi-step reasoning (e.g., search policy → get fact → compare)
- Required for proper tool call ID tracking
- Supports debugging and auditing

**Implementation**:
- Maintain list of message dictionaries
- Append assistant messages with `tool_calls` array
- Append tool result messages with matching `tool_call_id`
- Handle provider-specific message formats

### Decision: Error Classification and Retry Strategy

**What**: Classify errors as transient (retry with backoff) vs permanent (fail fast), with fallback to heuristic controller.

**Why**:
- Transient errors (rate limits, timeouts) should be retried
- Permanent errors (invalid API key, schema violations) should fail fast
- Fallback ensures system remains operational

**Classification**:
- **Transient**: Rate limit errors, network timeouts, temporary API outages
  - Strategy: Exponential backoff (1s, 2s, 4s), max 3 retries
- **Permanent**: Invalid API key, malformed tool schemas, LLM rejection
  - Strategy: Return UNCERTAIN with reason_code, optionally fallback to heuristic

### Decision: Dual Controller Strategy

**What**: Keep both sync CLI controller (`src/controller/react_controller.py`) and async API controller (`src/reasoning_service/services/controller.py`) initially, align later.

**Why**:
- Minimizes risk by not changing both paths simultaneously
- Allows independent testing and validation
- Enables gradual migration
- Reduces scope of initial implementation

**Future**: After async controller is proven, consider unifying or creating shared core.

### Decision: Tool Result Caching

**What**: Cache tool results within a single evaluation to avoid redundant calls.

**Why**:
- `pi_search` with same query may be called multiple times
- `facts_get` results are stable within an evaluation
- Reduces latency and cost
- Simple to implement (in-memory cache per evaluation)

**Scope**: Cache per `_evaluate_criterion()` call, cleared after evaluation completes.

### Decision: FTS5 Service Integration

**What**: Treat FTS5 as optional service passed to `ToolExecutor`, integrate with existing `src/retrieval/fts5_fallback.py` module.

**Why**:
- FTS5 fallback exists but isn't fully integrated
- Making it optional allows graceful degradation
- Can be enhanced later without breaking changes

**Implementation**: Check if `fts5_service` is provided, return error if `spans_tighten` called without it.

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│              ReActController (LLM)                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  System Prompt → User Prompt → LLM → Tool Calls       │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│  │  THINK   │───▶│  ACTION  │───▶│OBSERVATION│      │
│  │ (LLM)    │    │(tool call│    │ (result)  │        │
│  └──────────┘    └──────────┘    └──────────┘        │
│       │               │                 │               │
│       └───────────────┴─────────────────┘               │
│                       │                                 │
│                       ▼                                 │
│              Loop until finish()                        │
│                                                         │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │      ToolExecutor             │
    ├───────────────────────────────┤
    │  - pi_search() → RetrievalService│
    │  - facts_get() → CaseBundle   │
    │  - spans_tighten() → FTS5     │
    │  - finish() → Build Result    │
    └───────────────────────────────┘
```

### Key Components

1. **LLMClient** (`src/reasoning_service/services/llm_client.py`)
   - Unified interface for OpenAI/Anthropic/vLLM
   - Handles provider-specific API calls and response parsing
   - Manages authentication and base URLs

2. **ToolExecutor** (`src/reasoning_service/services/tool_handlers.py`)
   - Executes tools called by LLM
   - Integrates with RetrievalService and CaseBundle
   - Returns JSON-formatted results
   - Caches results within evaluation

3. **ReActController** (`src/reasoning_service/services/react_controller.py`)
   - Main orchestration loop
   - Manages message history
   - Detects finish() calls
   - Builds CriterionResult objects

4. **System Prompt** (`src/reasoning_service/prompts/react_system_prompt.py`)
   - Defines agent role and behavior
   - Explains ReAct pattern
   - Documents available tools
   - Sets decision rules and confidence guidelines

### Integration Points

- **RetrievalService**: Existing async interface, returns `RetrievalResult`
- **CaseBundle**: Pydantic model with VLM-extracted fields
- **CriterionResult**: Output schema matching existing API contracts
- **Config**: Settings for LLM provider, model, API keys

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM hallucination | High | Strict JSON schemas, validate all citations, abstention rules (confidence < 0.65) |
| Increased latency | Medium | Caching, prompt optimization, use faster models (gpt-4o-mini), parallel tool calls where possible |
| API rate limits | Medium | Exponential backoff, queue management, fallback to heuristic |
| Cost explosion | Low | Token budgets per evaluation, monitoring, alerts, use cheaper models |
| Tool calling errors | Medium | Robust error handling, validate schemas, fallback to heuristic |
| Schema incompatibility | Medium | Verify RetrievalResult structure early, adapt if needed |
| Dual controller divergence | Low | Document alignment plan, test both paths |

## Migration Strategy

### Phase 1: Shadow Mode (Week 5)
- Deploy new controller alongside old one
- Run both, compare outputs
- Log discrepancies
- No user-facing changes
- **Success criteria**: No regressions, reasonable quality

### Phase 2: A/B Testing (Week 6)
- Route 10% traffic to new controller
- Monitor quality metrics (citation accuracy, confidence calibration)
- Gradually increase to 50% if metrics good
- **Success criteria**: Quality metrics match or exceed heuristic controller

### Phase 3: Full Migration (Week 7)
- Route 100% to new controller
- Keep old controller as fallback
- Monitor for regressions
- **Success criteria**: Stable operation, no increase in error rates

### Rollback Plan
- Feature flag to switch back to heuristic controller
- Fallback mechanism automatically triggers on errors
- Can revert within minutes if critical issues arise

## Open Questions

1. **Sync/Async Controller Unification**: Should we unify immediately or defer? 
   - **Decision**: Defer to post-migration phase
   - **Rationale**: Reduces initial scope, allows independent validation

2. **FTS5 Service Integration**: Separate service or part of RetrievalService?
   - **Decision**: Optional parameter to ToolExecutor
   - **Rationale**: Allows graceful degradation, can enhance later

3. **Prompt Versioning**: How to track and A/B test prompt variations?
   - **Decision**: Add `prompt_id` to responses, store versions in config
   - **Rationale**: Enables experimentation without code changes

4. **Prompt Optimization**: How to continuously improve prompts?
   - **Decision**: Integrate GEPA (Genetic Pareto) optimizer from DSPy library
   - **Rationale**: Enables autonomous agent retraining through evolutionary prompt optimization
   - **Implementation**: Use GEPA's evolutionary algorithm to generate and evaluate prompt candidates, selecting best performers using Pareto optimization
   - **Evaluation Metrics**: Citation accuracy (40%), reasoning coherence (30%), confidence calibration (20%), status correctness (10%)
   - **Trigger**: Automated optimization when quality metrics degrade, or manual trigger for improvement
   - **Reference**: See `gepa_implementation.md` for complete implementation guide with code examples, configuration, and usage patterns

5. **Token Budget Enforcement**: Hard limit or soft warning?
   - **Decision**: Soft warning initially, hard limit in production
   - **Rationale**: Allows iteration during development, prevents cost overruns in production

6. **Reasoning Trace Detail Level**: Full LLM thoughts or summarized?
   - **Decision**: Include full observations (truncated if >500 chars)
   - **Rationale**: Better for auditing, can summarize later if needed

## Performance Considerations

- **Target latency**: P50 < 8s, P95 < 20s (vs current ~0.5s heuristic)
- **Cost target**: < $0.05 per evaluation (gpt-4o-mini, ~4 iterations avg)
- **Iteration limit**: Max 10 iterations to prevent infinite loops
- **Token budget**: ~6000 tokens per evaluation (input + output)

## Security Considerations

- **API keys**: Stored in environment variables, never logged
- **PHI handling**: Reasoning traces may contain case data, ensure proper access controls
- **Input validation**: Validate all tool arguments against schemas
- **Output sanitization**: Ensure citations don't leak sensitive policy details

