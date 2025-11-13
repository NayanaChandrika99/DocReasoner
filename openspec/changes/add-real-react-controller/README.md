# Add Real ReAct Controller - Change Documentation

This directory contains the complete specification and implementation guide for adding LLM-driven ReAct controller capabilities to the reasoning service.

## Contents

### Core Documentation

- **[proposal.md](./proposal.md)** - High-level overview of the change, rationale, and impact
- **[design.md](./design.md)** - Detailed design decisions and architecture
- **[tasks.md](./tasks.md)** - Phase-by-phase implementation checklist
- **[specs/react-controller/spec.md](./specs/react-controller/spec.md)** - Formal requirements specification

### Implementation Guides

- **[gepa_implementation.md](./gepa_implementation.md)** - Complete GEPA prompt optimization guide
  - GEPA architecture and workflow
  - Implementation components with full code examples
  - Configuration and usage patterns
  - Integration with prompt registry and MLflow
  - Monitoring, evaluation, and troubleshooting
  
- **[additional_tools.md](./additional_tools.md)** - Extended tool capabilities
  - Medical knowledge tools (PubMed, ICD-10, drug interactions)
  - Policy analysis tools (cross-references, temporal analysis)
  - Evidence synthesis tools (confidence aggregation, contradiction detection)
  - Multi-agent collaboration framework
  - Implementation patterns and examples

## Quick Navigation

### For Implementation

1. Start with [proposal.md](./proposal.md) for context
2. Review [design.md](./design.md) for architectural decisions
3. Follow [tasks.md](./tasks.md) for step-by-step implementation
4. Reference [specs/react-controller/spec.md](./specs/react-controller/spec.md) for requirements

### For GEPA Optimization

1. Read [gepa_implementation.md](./gepa_implementation.md) sections:
   - **Overview** - What is GEPA and why use it
   - **Architecture** - How GEPA works in this system
   - **Implementation Components** - Full code with `PromptOptimizer`, `ReActControllerAdapter`
   - **Configuration** - Settings and parameters
   - **Usage Examples** - Basic usage and automated retraining
   
2. Key GEPA files to implement:
   ```
   src/reasoning_service/services/
   ├── prompt_optimizer.py          # Main orchestrator
   ├── prompt_evaluator.py          # Metrics calculation
   └── prompt_registry.py           # Version management
   
   scripts/
   └── optimize_react_prompt.py     # CLI script
   ```

3. Evaluation metrics (from design decisions):
   - Citation accuracy: 40% weight
   - Reasoning coherence: 30% weight
   - Confidence calibration: 20% weight
   - Status correctness: 10% weight

### For Additional Tools

1. Review [additional_tools.md](./additional_tools.md) for:
   - Medical knowledge integration (PubMed, ICD-10, drugs)
   - Policy analysis capabilities
   - Evidence synthesis tools
   - Multi-agent patterns

2. Implementation pattern:
   ```python
   # 1. Define tool class
   class NewTool:
       def execute(self, ...): ...
   
   # 2. Add tool definition
   def get_new_tool_definition(): ...
   
   # 3. Register in ToolExecutor
   async def execute(self, tool_name, arguments):
       if tool_name == "new_tool":
           return await self.new_tool.execute(...)
   ```

## Key Features

### LLM-Driven Reasoning
- Replace heuristic logic with actual LLM reasoning
- Dynamic tool selection based on case context
- True ReAct pattern: Thought → Action → Observation
- Complete reasoning traces for auditability

### Multi-Provider Support
- OpenAI (GPT-4o-mini, GPT-4o)
- Anthropic (Claude models)
- vLLM (self-hosted models)
- Unified interface across providers

### Tool System
- **Core tools**: pi_search, facts_get, spans_tighten, finish
- **Medical tools**: PubMed search, ICD-10 lookup, drug interactions
- **Policy tools**: Cross-references, temporal analysis
- **Synthesis tools**: Confidence aggregation, contradiction detection

### GEPA Optimization
- Autonomous prompt improvement through evolutionary search
- Multi-objective optimization (4 metrics)
- Textual feedback for LLM reflection
- Pareto-based candidate selection
- Automated retraining on quality degradation

### Safety & Monitoring
- Error handling with retry logic
- Fallback to heuristic controller
- Token budget tracking
- Prometheus metrics
- Cost controls

## Implementation Timeline

### Phase 1: Foundation (Week 1)
- LLM client abstraction
- Tool schemas and handlers
- Configuration setup

### Phase 2: Core ReAct Loop (Week 2)
- System prompt
- ReAct loop implementation
- Message history management
- Error handling

### Phase 3: Testing (Week 3)
- Unit tests with mocked LLM
- Integration tests
- Reasoning trace validation

### Phase 4: Optimization (Week 4)
- Tool result caching
- Prometheus metrics
- Token counting
- **GEPA prompt optimizer**

### Phase 5: Migration (Weeks 5-7)
- Shadow mode
- Fallback mechanism
- A/B testing
- Quality monitoring

## GEPA Optimization Workflow

```
┌─────────────────────────────────────────────────────┐
│           GEPA Optimization Pipeline                 │
├─────────────────────────────────────────────────────┤
│                                                       │
│  1. Quality Monitor                                  │
│     └─> Detect degradation (citation < 0.85, etc.)  │
│                                                       │
│  2. Trigger Optimization                             │
│     └─> Load test cases from fixtures                │
│     └─> Initialize GEPA with current prompt          │
│                                                       │
│  3. Evolutionary Search                              │
│     ├─> Generate candidates (reflection LLM)         │
│     ├─> Evaluate on training set                     │
│     ├─> Calculate 4 metrics + aggregate              │
│     ├─> Generate textual feedback                    │
│     ├─> Reflect and mutate                           │
│     └─> Pareto selection                             │
│                                                       │
│  4. Validation                                       │
│     └─> Evaluate best candidate on validation set    │
│                                                       │
│  5. Approval Workflow                                │
│     ├─> Register in prompt registry                  │
│     ├─> Request manual review                        │
│     └─> Activate when approved                       │
│                                                       │
└─────────────────────────────────────────────────────┘
```

## Usage Examples

### Basic ReAct Evaluation

```python
from reasoning_service.services.react_controller import ReActController
from reasoning_service.services.llm_client import LLMClient
from reasoning_service.services.retrieval import RetrievalService

# Initialize
llm_client = LLMClient(model="gpt-4o-mini")
retrieval_service = RetrievalService(pageindex_client)

controller = ReActController(
    llm_client=llm_client,
    retrieval_service=retrieval_service,
)

# Evaluate case
results = await controller.evaluate_case(
    case_bundle=case_bundle,
    policy_document_id="pi-doc-123",
)
```

### Running GEPA Optimization

```bash
# Install DSPy
pip install dspy-ai

# Run optimization script
python scripts/optimize_react_prompt.py \
    --trainset tests/data/cases/ \
    --max-iterations 150 \
    --target-score 0.8
```

### Using Additional Tools

```python
# Add PubMed search to ReAct controller
from reasoning_service.services.medical_tools import PubMedSearchTool

pubmed_tool = PubMedSearchTool()
executor = ToolExecutor(
    retrieval_service=retrieval_service,
    case_bundle=case_bundle,
    pubmed_tool=pubmed_tool,  # Add new tool
)
```

## Configuration

### Required Environment Variables

```bash
# LLM Configuration
LLM_PROVIDER=openai  # openai, anthropic, vllm
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...
LLM_BASE_URL=http://localhost:8000  # For vLLM

# GEPA Configuration
GEPA_ENABLED=true
GEPA_AUTO_MODE=medium  # light, medium, heavy
GEPA_MAX_ITERATIONS=150
GEPA_TARGET_SCORE=0.8
GEPA_REFLECTION_MODEL=gpt-4o
GEPA_TASK_MODEL=gpt-4o-mini

# Metric Weights
GEPA_CITATION_WEIGHT=0.4
GEPA_REASONING_WEIGHT=0.3
GEPA_CONFIDENCE_WEIGHT=0.2
GEPA_STATUS_WEIGHT=0.1
```

### Dependencies

Add to `pyproject.toml`:

```toml
[tool.poetry.dependencies]
# Existing dependencies...
openai = "^1.0.0"
anthropic = "^0.18.0"
dspy-ai = "^2.4.0"  # For GEPA optimization

[tool.poetry.group.dev.dependencies]
# Testing
pytest-asyncio = "^0.23.0"
```

## Testing Strategy

### Unit Tests
- Mock LLM responses
- Test tool execution
- Verify reasoning trace format
- Test error handling

### Integration Tests
- Real PageIndex integration
- Real LLM calls (gated by API key)
- End-to-end flow validation
- Performance benchmarking

### GEPA Optimization Tests
- Metric calculation accuracy
- Feedback generation quality
- Prompt registry integration
- Version management

## Monitoring

### Key Metrics

```promql
# ReAct controller performance
react_evaluations_total
react_tool_calls_total{tool_name="pi_search"}
react_iterations
react_latency_seconds

# GEPA optimization
gepa_optimizations_total{status="success"}
gepa_optimization_duration_seconds
gepa_prompt_score{metric_type="aggregate"}
```

### Quality Dashboards

1. **Citation Accuracy** - Track % with valid policy citations
2. **Reasoning Quality** - Average reasoning trace length/diversity
3. **Confidence Calibration** - Correlation between confidence and correctness
4. **Status Accuracy** - Correct met/missing/uncertain determinations

## Troubleshooting

### Common Issues

**GEPA not improving scores:**
- Check evaluation metrics align with quality goals
- Increase `max_metric_calls` for more exploration
- Review feedback generation specificity
- Try different reflection model

**High latency:**
- Enable tool result caching
- Reduce max_iterations
- Use faster model (gpt-4o-mini instead of gpt-4o)
- Implement parallel tool calls

**Poor reasoning quality:**
- Review system prompt clarity
- Add more examples in prompt
- Adjust confidence thresholds
- Run GEPA optimization

## References

- [GEPA Paper](https://arxiv.org/abs/2507.19457) - Reflective Prompt Evolution
- [ReAct Paper](https://arxiv.org/abs/2210.03629) - Reasoning and Acting pattern
- [DSPy Documentation](https://dspy.ai/) - Programming LLMs
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling) - Tool use format
- [PageIndex](https://docs.pageindex.ai/) - Policy retrieval system

## Support

For questions or issues:
1. Review relevant documentation sections above
2. Check troubleshooting guide in `gepa_implementation.md`
3. Review test cases for usage examples
4. Consult design decisions in `design.md`

---

**Status**: In Progress (Phase 1-4 complete, Phase 5 pending)
**Last Updated**: 2025-11-13
**Version**: 0.1.0

