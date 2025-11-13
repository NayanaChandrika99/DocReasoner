# Implementation Tasks

## Phase 1: Foundation (Week 1)

- [ ] 1.1 Create LLM client abstraction (`src/reasoning_service/services/llm_client.py`)
  - Support OpenAI, Anthropic, and vLLM providers
  - Implement unified `call_with_tools()` interface
  - Add response parsing for each provider format
  - Handle tool calling format differences

- [ ] 1.2 Add LLM configuration to `src/reasoning_service/config.py`
  - Add `llm_provider` field (default: "openai")
  - Add `llm_model` field (default: "gpt-4o-mini")
  - Add `llm_api_key` field (from environment)
  - Add `llm_base_url` field (for vLLM)
  - Update `.env.development.template` with new variables

- [ ] 1.3 Define tool schemas (`src/reasoning_service/services/tools.py`)
  - Create `get_tool_definitions()` returning OpenAI function calling format
  - Define `pi_search` tool (query, top_k)
  - Define `facts_get` tool (field_name)
  - Define `spans_tighten` tool (node_id, query)
  - Define `finish` tool (status, rationale, confidence, policy_section, policy_pages, evidence_doc_id, evidence_page)
  - Use strict JSON schemas for all tools

- [ ] 1.4 Implement tool handlers (`src/reasoning_service/services/tool_handlers.py`)
  - Create `ToolExecutor` class
  - Implement `execute()` method routing to specific handlers
  - Implement `_pi_search()` calling `RetrievalService.retrieve()`
  - Implement `_facts_get()` searching case bundle fields
  - Implement `_spans_tighten()` using FTS5 service (if available)
  - Add error handling and JSON result formatting
  - Cache retrieval results for potential reuse

- [ ] 1.5 Verify RetrievalService interface compatibility
  - Confirm `RetrievalService.retrieve()` returns `RetrievalResult` with expected fields
  - Verify `node_refs`, `search_trajectory`, `confidence`, `retrieval_method` are available
  - Test integration with existing retrieval pipeline
  - Document any interface gaps or needed adjustments

## Phase 2: Core ReAct Loop (Week 2)

- [ ] 2.1 Create system prompt (`src/reasoning_service/prompts/react_system_prompt.py`)
  - Write comprehensive `REACT_SYSTEM_PROMPT` constant
  - Define agent role as medical policy verification expert
  - Explain ReAct pattern (Thought → Action → Observation)
  - List all available tools with descriptions
  - Specify output format requirements
  - Include decision rules (met/missing/uncertain)
  - Add confidence guidelines and abstention rules
  - Include example flow demonstrating tool usage

- [ ] 2.2 Implement ReAct controller loop (`src/reasoning_service/services/react_controller.py`)
  - Create `ReActController` class with LLM client and tool executor
  - Implement `evaluate_case()` method orchestrating criterion evaluation
  - Implement `_evaluate_criterion()` with ReAct loop
  - Build message history (system prompt + user prompt + assistant responses + tool results)
  - Call LLM with tools in loop until `finish()` is called
  - Track reasoning trace for each iteration
  - Handle max iterations limit

- [ ] 2.3 Add message history management
  - Maintain conversation state across iterations
  - Append assistant messages with tool calls
  - Append tool result messages with proper `tool_call_id`
  - Handle message format differences between providers
  - Ensure tool call IDs are tracked correctly

- [ ] 2.4 Implement finish() detection and result building
  - Detect when LLM calls `finish()` tool
  - Extract decision arguments from tool call
  - Map status string to `DecisionStatus` enum
  - Build `CriterionResult` with all required fields
  - Extract confidence breakdown from retrieval results
  - Build citation info from policy section and pages
  - Build evidence info if provided
  - Serialize reasoning trace to `ReasoningStep` format

- [ ] 2.5 Add error handling and timeout logic
  - Handle LLM API errors (rate limits, timeouts, invalid responses)
  - Classify errors as transient (retry) vs permanent (fail fast)
  - Implement exponential backoff for retries
  - Handle tool execution errors gracefully
  - Return UNCERTAIN status with error details when appropriate
  - Add reason codes for different error types

## Phase 3: Testing (Week 3)

- [ ] 3.1 Write unit tests with mocked LLM (`tests/unit/test_real_react_controller.py`)
  - Mock `LLMClient` to return controlled responses
  - Test successful evaluation flow with multiple tool calls
  - Test finish() detection and result building
  - Test error handling (LLM failures, tool failures)
  - Test max iterations limit
  - Test confidence < 0.65 → UNCERTAIN logic
  - Verify reasoning trace format matches schema

- [ ] 3.2 Create integration test scaffold (`tests/integration/test_react_real_policy.py`)
  - Create test that requires real API keys (marked with `@pytest.mark.skipif`)
  - Test with real PageIndex document
  - Test end-to-end flow with real LLM (gpt-4o-mini)
  - Verify citations, confidence, and reasoning trace quality
  - Add verbose output for manual inspection

- [ ] 3.3 Add test fixtures matching existing `tests/data/cases/` format
  - Create test cases covering straightforward, synthesis, conflict scenarios
  - Ensure fixtures include expected citations and reasoning summaries
  - Add difficulty tags for test categorization
  - Verify fixtures work with both old and new controller

- [ ] 3.4 Validate reasoning trace format matches `ReasoningStep` schema
  - Ensure trace entries have `step`, `action`, `observation` fields
  - Verify action values match expected types
  - Check observation truncation for long results
  - Test serialization to JSON format

## Phase 4: Optimization (Week 4)

- [ ] 4.1 Implement tool result caching (`src/reasoning_service/services/react_optimizer.py`)
  - Create `ReActOptimizer` class with cache
  - Implement `get_cache_key()` using tool name and arguments hash
  - Implement `execute_with_cache()` wrapper
  - Cache `pi_search` results within evaluation
  - Cache `facts_get` results (should be stable)
  - Add cache invalidation strategy

- [ ] 4.2 Add Prometheus metrics (`src/reasoning_service/observability/react_metrics.py`)
  - Create counters: `react_evaluations_total`, `react_tool_calls_total`, `react_errors_total`
  - Create histograms: `react_iterations`, `react_latency_seconds`, `react_llm_tokens`
  - Create gauge: `react_active_evaluations`
  - Instrument controller to emit metrics
  - Add labels for status, criterion, tool_name, error_type

- [ ] 4.3 Implement token counting and cost tracking
  - Track input and output tokens per LLM call
  - Calculate cost based on provider and model
  - Add token budget limits per evaluation
  - Log token usage for monitoring
  - Add cost alerts for budget overruns

- [ ] 4.4 Add prompt versioning system
  - Store prompt version ID in responses
  - Track prompt changes over time
  - Enable A/B testing of prompt variations
  - Add prompt version to `AuthReviewResponse.prompt_id`

- [ ] 4.5 Integrate GEPA prompt optimizer from DSPy for autonomous agent retraining
  - **Reference**: See `gepa_implementation.md` for complete implementation guide
  - Install DSPy library (`pip install dspy-ai` or add to `pyproject.toml`)
  - Create prompt optimization module (`src/reasoning_service/services/prompt_optimizer.py`)
    - Implement `PromptOptimizer` class with GEPA integration
    - Implement `ReActControllerAdapter` for DSPy GEPA interface
    - Implement `OptimizationConfig` dataclass for configuration
    - Implement `EvaluationResult` dataclass for metrics tracking
  - Create prompt evaluator (`src/reasoning_service/services/prompt_evaluator.py`)
    - Implement metric calculators for each evaluation dimension
    - Implement feedback generation for GEPA reflection
    - Implement reflective dataset builder for optimization
  - Create prompt registry (`src/reasoning_service/services/prompt_registry.py`)
    - Implement `PromptRegistry` for version management
    - Implement `PromptVersion` dataclass for versioned prompts
    - Implement approval workflow for optimized prompts
    - Implement A/B testing infrastructure
  - Define evaluation metrics for ReAct controller:
    - Citation accuracy (40%): Correct policy section/page references
    - Reasoning coherence (30%): Quality of reasoning trace clarity (length, diversity, observation quality)
    - Confidence calibration (20%): Correlation between confidence and correctness
    - Status correctness (10%): Correct met/missing/uncertain decisions
  - Implement GEPA optimization loop:
    - Initialize GEPA optimizer with reflection model (gpt-4o) and evaluation criteria
    - Create evaluation dataset from test fixtures (`tests/data/cases/`)
    - Run evolutionary algorithm to generate prompt candidates with reflection
    - Evaluate candidates using multi-objective metrics
    - Generate textual feedback for GEPA reflection (not just scores)
    - Select best-performing prompts using Pareto optimization
    - Iterate until target performance threshold (e.g., 0.8 aggregate score) or max iterations (150)
    - Cache evaluation results to avoid redundant API calls
  - Integrate with prompt versioning system (store optimized prompts with version IDs)
  - Add configuration to `src/reasoning_service/config.py`:
    - `GEPA_ENABLED`: Enable/disable GEPA optimization
    - `GEPA_AUTO_MODE`: light, medium, heavy (controls budget)
    - `GEPA_MAX_ITERATIONS`: Maximum optimization iterations (default: 150)
    - `GEPA_TARGET_SCORE`: Performance threshold to stop optimization (default: 0.8)
    - `GEPA_REFLECTION_MODEL`: Model for reflection (default: gpt-4o)
    - `GEPA_TASK_MODEL`: Model being optimized (default: gpt-4o-mini)
    - Metric weights for citation, reasoning, confidence, status
  - Create optimization script (`scripts/optimize_react_prompt.py`)
    - Load test cases from fixtures
    - Initialize optimizer with configuration
    - Run optimization with seed prompt
    - Save results and best prompt
    - Display metrics and improvement summary
  - Create quality monitor (`src/reasoning_service/services/quality_monitor.py`)
    - Monitor recent decision quality from database
    - Calculate aggregate quality metrics
    - Trigger optimization when quality degrades below threshold
    - Implement approval workflow for optimized prompts
    - Support manual review and approval before production
  - Add Prometheus metrics for optimization:
    - `gepa_optimizations_total`: Counter for optimization runs
    - `gepa_optimization_duration_seconds`: Histogram for optimization time
    - `gepa_prompt_score`: Gauge for current prompt quality
    - `gepa_evaluations_per_run`: Histogram for evaluation counts
  - Create documentation and examples:
    - Basic usage example in `gepa_implementation.md`
    - Automated retraining example
    - Troubleshooting guide
    - Integration patterns

## Phase 5: Migration (Weeks 5-7)

- [ ] 5.1 Implement shadow mode (run both controllers, compare outputs)
  - Add feature flag to enable shadow mode
  - Run new ReAct controller alongside old heuristic controller
  - Log both results for comparison
  - Compare status, confidence, citations, reasoning traces
  - Generate discrepancy reports
  - No user-facing changes during shadow mode

- [ ] 5.2 Add fallback mechanism to heuristic controller
  - Implement `evaluate_with_fallback()` wrapper
  - Try new ReAct controller first
  - Check result quality (confidence, reasoning trace completeness)
  - Fall back to heuristic if quality too low or errors occur
  - Log fallback events for analysis
  - Return appropriate reason codes

- [ ] 5.3 Create A/B testing infrastructure
  - Add routing logic to split traffic (10% → 50% → 100%)
  - Track quality metrics per controller version
  - Compare citation accuracy, reasoning coherence, confidence calibration
  - Monitor performance metrics (latency, cost, error rates)
  - Create dashboards for comparison

- [ ] 5.4 Monitor quality metrics and iterate
  - Set up alerts for quality degradation
  - Review discrepancy reports weekly
  - Tune prompts based on failure patterns
  - Adjust confidence thresholds if needed
  - Iterate on tool definitions based on usage patterns
  - Document lessons learned

