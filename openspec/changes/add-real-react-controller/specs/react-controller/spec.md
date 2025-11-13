## ADDED Requirements

### Requirement: LLM-Driven ReAct Controller

The system SHALL use an LLM to dynamically reason about policy verification tasks using the ReAct (Reasoning and Acting) pattern. The controller MUST interleave reasoning (thought) with tool calls (action) and observations, continuing until sufficient information is gathered to make a determination.

#### Scenario: Successful evaluation with tool calls

- **WHEN** a case bundle is evaluated against a policy criterion
- **THEN** the controller uses LLM reasoning to select and call tools (pi_search, facts_get, spans_tighten)
- **AND** the controller generates a reasoning trace showing thought → action → observation cycles
- **AND** the controller calls finish() with structured decision (status, rationale, confidence, citations)

#### Scenario: Agent abstains on low confidence

- **WHEN** the LLM determines confidence < 0.65
- **THEN** the controller returns UNCERTAIN status
- **AND** the reasoning trace explains why information is insufficient

#### Scenario: Tool execution error recovery

- **WHEN** a tool call fails (e.g., PageIndex timeout)
- **THEN** the controller attempts recovery or falls back to heuristic controller
- **AND** the error is recorded in reasoning trace with reason_code

#### Scenario: Maximum iterations reached

- **WHEN** the ReAct loop exceeds the maximum iteration limit (default: 10)
- **THEN** the controller returns UNCERTAIN status
- **AND** the reasoning trace includes all attempted steps
- **AND** reason_code indicates "max_iterations_reached"

### Requirement: Multi-Provider LLM Support

The system SHALL support multiple LLM providers (OpenAI, Anthropic, vLLM) through a unified client interface. The provider SHALL be configurable via environment variable or configuration file.

#### Scenario: OpenAI provider usage

- **WHEN** LLM_PROVIDER=openai is configured
- **THEN** the system uses OpenAI API with function calling
- **AND** tool calls are parsed in OpenAI format
- **AND** responses include tool_calls array with function name and arguments

#### Scenario: Anthropic provider usage

- **WHEN** LLM_PROVIDER=anthropic is configured
- **THEN** the system uses Anthropic Messages API with tool use
- **AND** tool calls are parsed in Anthropic format
- **AND** responses include content blocks with type="tool_use"

#### Scenario: vLLM provider usage

- **WHEN** LLM_PROVIDER=vllm is configured with LLM_BASE_URL pointing to vLLM server
- **THEN** the system uses OpenAI-compatible API endpoint
- **AND** tool calls are parsed in OpenAI format
- **AND** authentication uses placeholder API key

### Requirement: Tool Calling System

The system SHALL provide tools for policy search, fact retrieval, span tightening, and decision submission. Each tool SHALL have a strict JSON schema defining its parameters and return values.

#### Scenario: Policy search tool

- **WHEN** LLM calls pi_search(query="lumbar MRI requirements")
- **THEN** the system executes PageIndex LLM Tree Search
- **AND** returns node_ids, page_refs, relevant paragraphs, search_trajectory
- **AND** results are cached for potential reuse within the same evaluation

#### Scenario: Fact retrieval tool

- **WHEN** LLM calls facts_get(field_name="patient_age")
- **THEN** the system retrieves field value from case bundle
- **AND** returns value, confidence, doc_id, page, bbox
- **AND** handles field name variations (normalizes to lowercase with underscores)

#### Scenario: Span tightening tool

- **WHEN** LLM calls spans_tighten(node_id="1.2.3", query="age requirement")
- **THEN** the system uses BM25 ranking to narrow spans within the selected node
- **AND** returns ranked list of most relevant paragraphs
- **AND** returns error if FTS5 service not configured or node not found

#### Scenario: Finish tool

- **WHEN** LLM calls finish(status="met", rationale="...", confidence=0.9, ...)
- **THEN** the controller stops the ReAct loop
- **AND** builds CriterionResult with provided arguments
- **AND** maps status string to DecisionStatus enum
- **AND** validates confidence is between 0.0 and 1.0

### Requirement: Reasoning Trace

The system SHALL generate a complete reasoning trace showing all ReAct steps (thought, action, observation). The trace SHALL be included in the CriterionResult and SHALL match the ReasoningStep schema.

#### Scenario: Trace includes all iterations

- **WHEN** evaluation completes after N iterations
- **THEN** reasoning_trace contains N ReasoningStep entries
- **AND** each step includes step number, action type, and observation
- **AND** observations are truncated to 500 characters if longer

#### Scenario: Trace shows tool call details

- **WHEN** LLM calls a tool during evaluation
- **THEN** the reasoning trace includes an entry with action matching the tool name
- **AND** the observation includes tool result summary or error message

#### Scenario: Trace includes finish call

- **WHEN** LLM calls finish() to complete evaluation
- **THEN** the reasoning trace includes a final entry showing the decision
- **AND** the observation includes status and rationale summary

### Requirement: Message History Management

The system SHALL maintain a complete conversation history including system prompt, user prompt, assistant messages with tool calls, and tool result messages. The history SHALL be passed to the LLM on each iteration to enable multi-step reasoning.

#### Scenario: History accumulates across iterations

- **WHEN** the ReAct loop executes multiple iterations
- **THEN** each LLM call includes all previous messages
- **AND** assistant messages include tool_calls array
- **AND** tool result messages include matching tool_call_id

#### Scenario: Tool call IDs are tracked

- **WHEN** LLM makes tool calls
- **THEN** each tool call has a unique ID
- **AND** tool results are matched to calls using tool_call_id
- **AND** message history maintains correct ordering

### Requirement: Error Handling and Fallback

The system SHALL handle errors gracefully, classifying them as transient (retryable) or permanent (fail fast). The system SHALL fall back to the heuristic controller when appropriate.

#### Scenario: Transient error retry

- **WHEN** LLM API call fails with rate limit error
- **THEN** the system retries with exponential backoff (1s, 2s, 4s)
- **AND** retries up to 3 times before giving up
- **AND** returns UNCERTAIN with reason_code "rate_limit_exceeded" if all retries fail

#### Scenario: Permanent error fallback

- **WHEN** LLM API call fails with invalid API key error
- **THEN** the system does not retry
- **AND** falls back to heuristic controller if configured
- **AND** returns UNCERTAIN with reason_code "llm_error" if fallback unavailable

#### Scenario: Tool execution error

- **WHEN** tool execution fails (e.g., RetrievalService timeout)
- **THEN** the error is recorded in reasoning trace
- **AND** the controller may attempt alternative tools or return UNCERTAIN
- **AND** reason_code indicates the specific error type

### Requirement: Configuration and Environment

The system SHALL support configuration of LLM provider, model, API keys, and other settings via environment variables and configuration file. Default values SHALL be provided for development.

#### Scenario: Configuration from environment

- **WHEN** LLM_PROVIDER, LLM_MODEL, LLM_API_KEY are set in environment
- **THEN** the system uses these values to initialize LLM client
- **AND** falls back to defaults if variables not set

#### Scenario: Configuration validation

- **WHEN** invalid LLM_PROVIDER is configured
- **THEN** the system raises configuration error at startup
- **AND** provides clear error message listing valid providers

### Requirement: Performance and Cost Controls

The system SHALL enforce performance limits and cost controls to prevent resource exhaustion.

#### Scenario: Maximum iterations limit

- **WHEN** ReAct loop exceeds maximum iterations (default: 10)
- **THEN** the loop terminates
- **AND** returns UNCERTAIN status
- **AND** reason_code indicates "max_iterations_reached"

#### Scenario: Token budget tracking

- **WHEN** evaluation consumes tokens
- **THEN** token usage is tracked (input and output separately)
- **AND** cost is calculated based on provider and model
- **AND** metrics are emitted for monitoring

#### Scenario: Latency monitoring

- **WHEN** evaluation completes
- **THEN** total latency is measured
- **AND** metrics are emitted (histogram for distribution)
- **AND** alerts trigger if latency exceeds thresholds

### Requirement: Autonomous Agent Retraining with GEPA Prompt Optimizer

The system SHALL support autonomous prompt optimization using GEPA (Genetic Pareto) optimizer from DSPy library to continuously improve ReAct controller performance through evolutionary prompt refinement.

#### Scenario: Automated prompt optimization triggered by quality degradation

- **WHEN** quality metrics (citation accuracy, reasoning coherence, confidence calibration) fall below threshold
- **THEN** GEPA optimizer automatically generates prompt candidates
- **AND** evaluates candidates using LLM-as-judge or test suite
- **AND** selects best-performing prompts using Pareto optimization
- **AND** validates optimized prompts before promoting to production
- **AND** stores optimized prompts with version IDs for tracking

#### Scenario: Manual prompt optimization trigger

- **WHEN** administrator triggers prompt optimization manually
- **THEN** GEPA optimizer runs optimization loop with configured parameters
- **AND** generates prompt candidates through evolutionary algorithm
- **AND** evaluates candidates against evaluation dataset from test fixtures
- **AND** returns optimized prompt when target performance threshold reached
- **AND** requires manual approval before promoting to production

#### Scenario: Prompt optimization evaluation metrics

- **WHEN** GEPA optimizer evaluates prompt candidates
- **THEN** metrics include citation accuracy (40%), reasoning coherence (30%), confidence calibration (20%), status correctness (10%)
- **AND** aggregate score calculated as weighted sum of metrics
- **AND** optimization continues until aggregate score exceeds target threshold (default: 0.8) or max iterations reached

