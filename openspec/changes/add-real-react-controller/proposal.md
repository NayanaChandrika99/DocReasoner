# Change: Add Real ReAct Controller

## Why

The current ReActController in `src/reasoning_service/services/controller.py` uses hard-coded heuristic logic (if/else rules, string matching) rather than true LLM-driven reasoning. This limits adaptability, reasoning quality, and alignment with the architecture specified in `docs/plan.md`, which calls for an LLM-powered agent that dynamically selects tools and reasons about policy verification tasks.

## What Changes

- Replace heuristic-based decision logic with LLM-driven ReAct loop that dynamically reasons about cases
- Add unified LLM client abstraction supporting OpenAI, Anthropic, and vLLM providers
- Implement tool calling system with four tools: `pi_search`, `facts_get`, `spans_tighten`, and `finish`
- Generate actual LLM reasoning traces (thought → action → observation cycles) instead of predetermined steps
- Add dynamic tool selection where the LLM decides which tools to call and when
- Maintain backward compatibility during migration through shadow mode and fallback mechanisms
- Add comprehensive error handling, monitoring, and cost controls

**BREAKING**: The internal implementation changes significantly, but API contracts remain compatible. Existing code using `ReActController.evaluate_case()` will continue to work, though behavior may differ.

## Impact

- **Affected specs**: New capability `react-controller` (no existing spec to modify)
- **Affected code**:
  - `src/reasoning_service/services/controller.py` - Core controller implementation
  - `src/controller/react_controller.py` - Sync CLI controller (may need alignment later)
- **New files**:
  - `src/reasoning_service/services/llm_client.py` - LLM provider abstraction
  - `src/reasoning_service/services/tools.py` - Tool schema definitions
  - `src/reasoning_service/services/tool_handlers.py` - Tool execution logic
  - `src/reasoning_service/services/react_controller.py` - New ReAct loop implementation
  - `src/reasoning_service/prompts/react_system_prompt.py` - System prompt for LLM
  - `src/reasoning_service/services/react_optimizer.py` - Caching and optimization
  - `src/reasoning_service/services/prompt_optimizer.py` - GEPA prompt optimization for autonomous retraining
  - `src/reasoning_service/observability/react_metrics.py` - Prometheus metrics
- **Configuration changes**: Add LLM provider settings to `src/reasoning_service/config.py`
- **Testing**: New unit tests (`tests/unit/test_real_react_controller.py`) and integration tests (`tests/integration/test_react_real_policy.py`)
- **Dependencies**: New optional dependencies for OpenAI (`openai`), Anthropic (`anthropic`), vLLM compatibility, and DSPy (`dspy-ai`) for GEPA prompt optimization
- **Migration**: 7-week phased rollout (shadow mode → A/B testing → full migration) with fallback to heuristic controller

