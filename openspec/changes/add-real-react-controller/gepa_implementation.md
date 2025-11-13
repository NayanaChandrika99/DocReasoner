# GEPA Implementation Guide for ReActController Optimization

This document provides a comprehensive guide to implementing GEPA (Genetic-Pareto) prompt optimization for the ReActController in the medical policy verification system.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Implementation Components](#implementation-components)
4. [Configuration](#configuration)
5. [Usage Examples](#usage-examples)
6. [Integration Points](#integration-points)
7. [Monitoring and Evaluation](#monitoring-and-evaluation)

## Overview

### What is GEPA?

**GEPA (Genetic-Pareto)** is a reflective optimizer from DSPy that uses LLM-based reflection to evolve prompts through evolutionary search. Unlike traditional optimization approaches, GEPA leverages textual feedback (not just scalar scores) to guide the search process.

**Key Features:**
- **Reflective Evolution**: Uses LLM to analyze feedback and propose improvements
- **Textual Feedback Support**: Leverages detailed feedback about failures
- **Pareto-based Selection**: Tracks multiple objectives simultaneously
- **Component-level Optimization**: Can optimize individual prompts or entire programs
- **Few-Shot Efficiency**: Achieves high performance with minimal evaluations

### Why GEPA for Medical Policy Verification?

Medical policy verification requires:
1. **Accurate citations** to specific policy sections and pages
2. **Coherent reasoning** that follows medical and policy logic
3. **Calibrated confidence** that reflects evidence quality
4. **Correct status determination** (met/missing/uncertain)

GEPA can optimize all four metrics simultaneously using Pareto optimization, ensuring balanced improvements across all dimensions.

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   GEPA Optimization Loop                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Generate Prompt Candidates (Evolutionary Algorithm)      │
│     └─> Use reflection LLM to propose variations            │
│                                                               │
│  2. Evaluate Candidates on Minibatch                         │
│     └─> Run ReActController with candidate prompt            │
│     └─> Collect results and reasoning traces                 │
│                                                               │
│  3. Calculate Multi-Objective Metrics                        │
│     ├─> Citation Accuracy (40% weight)                       │
│     ├─> Reasoning Coherence (30% weight)                     │
│     ├─> Confidence Calibration (20% weight)                  │
│     └─> Status Correctness (10% weight)                      │
│                                                               │
│  4. Generate Textual Feedback                                │
│     └─> Analyze failure patterns                             │
│     └─> Identify improvement opportunities                   │
│                                                               │
│  5. Pareto Selection                                         │
│     └─> Select best candidates across all metrics            │
│                                                               │
│  6. Reflect and Mutate                                       │
│     └─> Use reflection LLM to propose improvements           │
│     └─> Generate next generation of candidates               │
│                                                               │
│  Repeat until target score reached or max iterations         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Component Architecture

```
src/reasoning_service/services/
├── prompt_optimizer.py          # Main orchestrator
│   ├── PromptOptimizer          # GEPA integration
│   ├── ReActControllerAdapter   # DSPy adapter
│   └── OptimizationConfig       # Configuration
│
├── prompt_evaluator.py          # Evaluation logic
│   ├── PolicyEvaluator          # Metrics calculator
│   ├── CitationAccuracyMetric   # Citation validation
│   ├── ReasoningCoherenceMetric # Trace quality
│   ├── ConfidenceCalibration    # Confidence analysis
│   └── StatusCorrectnessMetric  # Decision validation
│
└── prompt_registry.py           # Version management
    ├── PromptRegistry           # Storage
    ├── PromptVersion            # Versioning
    └── PromptComparator         # A/B testing
```

## Implementation Components

### 1. Main Orchestrator (`prompt_optimizer.py`)

```python
"""GEPA-based prompt optimization for ReActController."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import dspy

from reasoning_service.models.schema import CaseBundle, CriterionResult
from reasoning_service.services.react_controller import ReActController
from reasoning_service.services.llm_client import LLMClient
from reasoning_service.config import settings


@dataclass
class OptimizationConfig:
    """Configuration for GEPA optimization."""
    
    auto_mode: str = "medium"  # light, medium, heavy
    max_metric_calls: int = 150
    reflection_minibatch_size: int = 3
    candidate_selection_strategy: str = "pareto"  # pareto, current_best
    track_stats: bool = True
    skip_perfect_score: bool = True
    
    # Evaluation metric weights
    citation_accuracy_weight: float = 0.4
    reasoning_coherence_weight: float = 0.3
    confidence_calibration_weight: float = 0.2
    status_correctness_weight: float = 0.1
    
    # Target thresholds
    target_aggregate_score: float = 0.8
    min_citation_accuracy: float = 0.85
    min_reasoning_coherence: float = 0.75
    min_confidence_calibration: float = 0.70
    min_status_correctness: float = 0.90
    
    # Reflection model
    reflection_model: str = "gpt-4o"
    reflection_temperature: float = 1.0
    reflection_max_tokens: int = 32000
    
    # Task model (the model being optimized)
    task_model: str = "gpt-4o-mini"
    
    # Output paths
    output_dir: Path = field(default_factory=lambda: Path("optimization_results"))
    save_intermediate: bool = True


@dataclass
class EvaluationResult:
    """Result of evaluating a prompt candidate."""
    
    candidate_id: str
    prompt_text: str
    aggregate_score: float
    citation_accuracy: float
    reasoning_coherence: float
    confidence_calibration: float
    status_correctness: float
    feedback: str
    case_results: List[CriterionResult]
    evaluation_time_ms: int


class ReActControllerAdapter:
    """Adapter to integrate ReActController with GEPA."""
    
    def __init__(
        self,
        retrieval_service: Any,
        test_cases: List[Dict[str, Any]],
        config: OptimizationConfig,
    ):
        """Initialize adapter.
        
        Args:
            retrieval_service: RetrievalService instance
            test_cases: List of test cases with case_bundle and policy_doc_id
            config: Optimization configuration
        """
        self.retrieval_service = retrieval_service
        self.test_cases = test_cases
        self.config = config
        self._cache: Dict[str, List[CriterionResult]] = {}
    
    def get_components_to_update(self, candidate: Dict[str, Any]) -> List[str]:
        """Return components that GEPA should evolve.
        
        Args:
            candidate: Current candidate dictionary
            
        Returns:
            List of component names to optimize
        """
        return ["system_prompt"]
    
    async def evaluate_candidate(
        self,
        candidate: Dict[str, Any],
        minibatch: List[Dict[str, Any]],
    ) -> EvaluationResult:
        """Evaluate a prompt candidate on a minibatch.
        
        Args:
            candidate: Candidate containing system_prompt
            minibatch: Subset of test cases to evaluate
            
        Returns:
            EvaluationResult with scores and feedback
        """
        start_time = time.time()
        
        # Extract system prompt
        system_prompt = candidate.get("system_prompt", "")
        candidate_id = hashlib.sha256(system_prompt.encode()).hexdigest()[:8]
        
        # Check cache
        cache_key = f"{candidate_id}_{len(minibatch)}"
        if cache_key in self._cache:
            cached_results = self._cache[cache_key]
            return self._calculate_metrics(
                candidate_id, system_prompt, cached_results,
                int((time.time() - start_time) * 1000)
            )
        
        # Initialize controller with candidate prompt
        llm_client = LLMClient(model=self.config.task_model)
        controller = ReActController(
            llm_client=llm_client,
            retrieval_service=self.retrieval_service,
            max_iterations=10,
            verbose=False,
        )
        
        # Override system prompt (would need to add this capability)
        controller._system_prompt = system_prompt
        
        # Evaluate minibatch
        results = []
        for case in minibatch:
            try:
                case_bundle = self._parse_case_bundle(case)
                policy_doc_id = case.get("policy_doc_id", case.get("policy", {}).get("doc_id"))
                
                criterion_results = await controller.evaluate_case(
                    case_bundle=case_bundle,
                    policy_document_id=policy_doc_id,
                )
                
                results.extend(criterion_results)
                
            except Exception as e:
                # Record error but continue evaluation
                print(f"Error evaluating case: {e}")
                continue
        
        # Cache results
        self._cache[cache_key] = results
        
        # Calculate metrics
        evaluation_time = int((time.time() - start_time) * 1000)
        return self._calculate_metrics(candidate_id, system_prompt, results, evaluation_time)
    
    def _parse_case_bundle(self, case: Dict[str, Any]) -> CaseBundle:
        """Parse case dictionary to CaseBundle."""
        if isinstance(case.get("case_bundle"), CaseBundle):
            return case["case_bundle"]
        
        # Parse from JSON structure
        case_data = case.get("case_bundle", case)
        return CaseBundle(
            case_id=case_data.get("case_id", "unknown"),
            policy_id=case_data.get("policy_id", "unknown"),
            fields=case_data.get("fields", []),
            metadata=case_data.get("metadata", {}),
        )
    
    def _calculate_metrics(
        self,
        candidate_id: str,
        prompt_text: str,
        results: List[CriterionResult],
        evaluation_time_ms: int,
    ) -> EvaluationResult:
        """Calculate evaluation metrics from results.
        
        Args:
            candidate_id: Unique identifier for candidate
            prompt_text: The prompt being evaluated
            results: List of criterion results
            evaluation_time_ms: Time taken for evaluation
            
        Returns:
            EvaluationResult with all metrics
        """
        if not results:
            return EvaluationResult(
                candidate_id=candidate_id,
                prompt_text=prompt_text,
                aggregate_score=0.0,
                citation_accuracy=0.0,
                reasoning_coherence=0.0,
                confidence_calibration=0.0,
                status_correctness=0.0,
                feedback="No results to evaluate",
                case_results=[],
                evaluation_time_ms=evaluation_time_ms,
            )
        
        # 1. Citation Accuracy (40%)
        citation_accuracy = sum(
            1 for r in results
            if r.citation.doc != "N/A" and r.citation.section != "N/A" and r.citation.pages
        ) / len(results)
        
        # 2. Reasoning Coherence (30%)
        reasoning_scores = []
        for result in results:
            if result.reasoning_trace:
                # Quality heuristics:
                # - Longer traces = more thorough (up to 5 steps)
                # - Diverse actions = better reasoning
                # - Non-empty observations = meaningful steps
                trace_length_score = min(len(result.reasoning_trace) / 5.0, 1.0)
                
                actions = set(step.action for step in result.reasoning_trace)
                action_diversity_score = min(len(actions) / 4.0, 1.0)  # 4 tools max
                
                non_empty_obs = sum(
                    1 for step in result.reasoning_trace
                    if step.observation and len(step.observation) > 20
                )
                observation_quality = non_empty_obs / len(result.reasoning_trace)
                
                coherence = (
                    trace_length_score * 0.4 +
                    action_diversity_score * 0.3 +
                    observation_quality * 0.3
                )
                reasoning_scores.append(coherence)
            else:
                reasoning_scores.append(0.0)
        
        reasoning_coherence = sum(reasoning_scores) / len(reasoning_scores)
        
        # 3. Confidence Calibration (20%)
        # Well-calibrated: high confidence → met, low confidence → uncertain
        calibrated_count = 0
        for result in results:
            if result.status.value == "met" and result.confidence > 0.75:
                calibrated_count += 1
            elif result.status.value == "missing" and 0.6 < result.confidence < 0.9:
                calibrated_count += 1
            elif result.status.value == "uncertain" and result.confidence < 0.65:
                calibrated_count += 1
        
        confidence_calibration = calibrated_count / len(results)
        
        # 4. Status Correctness (10%)
        # This requires ground truth labels - use heuristics for now
        # Assumption: cases with high confidence and citations are likely correct
        status_correctness = sum(
            1 for r in results
            if (r.status.value != "uncertain" and r.confidence > 0.7 and r.citation.doc != "N/A") or
               (r.status.value == "uncertain" and r.confidence < 0.65)
        ) / len(results)
        
        # Aggregate score
        aggregate_score = (
            citation_accuracy * self.config.citation_accuracy_weight +
            reasoning_coherence * self.config.reasoning_coherence_weight +
            confidence_calibration * self.config.confidence_calibration_weight +
            status_correctness * self.config.status_correctness_weight
        )
        
        # Generate feedback
        feedback = self._generate_feedback(
            citation_accuracy, reasoning_coherence,
            confidence_calibration, status_correctness
        )
        
        return EvaluationResult(
            candidate_id=candidate_id,
            prompt_text=prompt_text,
            aggregate_score=aggregate_score,
            citation_accuracy=citation_accuracy,
            reasoning_coherence=reasoning_coherence,
            confidence_calibration=confidence_calibration,
            status_correctness=status_correctness,
            feedback=feedback,
            case_results=results,
            evaluation_time_ms=evaluation_time_ms,
        )
    
    def _generate_feedback(
        self,
        citation_acc: float,
        reasoning_coh: float,
        confidence_cal: float,
        status_corr: float,
    ) -> str:
        """Generate detailed textual feedback for GEPA reflection.
        
        Args:
            citation_acc: Citation accuracy score
            reasoning_coh: Reasoning coherence score
            confidence_cal: Confidence calibration score
            status_corr: Status correctness score
            
        Returns:
            Textual feedback describing strengths and weaknesses
        """
        feedback_parts = []
        
        # Citation accuracy feedback
        if citation_acc < self.config.min_citation_accuracy:
            feedback_parts.append(
                f"CITATION_ACCURACY ({citation_acc:.2%}) is below target ({self.config.min_citation_accuracy:.2%}). "
                f"The prompt should more explicitly guide the agent to cite specific policy sections and page numbers. "
                f"Consider adding examples or stronger language about citation requirements."
            )
        else:
            feedback_parts.append(
                f"Citation accuracy is strong ({citation_acc:.2%}). Good policy section identification."
            )
        
        # Reasoning coherence feedback
        if reasoning_coh < self.config.min_reasoning_coherence:
            feedback_parts.append(
                f"REASONING_COHERENCE ({reasoning_coh:.2%}) needs improvement. "
                f"Reasoning traces are too brief or lack diverse tool usage. "
                f"Emphasize step-by-step analysis, encourage using multiple tools (pi_search → facts_get → finish), "
                f"and require thorough evidence evaluation before making decisions."
            )
        else:
            feedback_parts.append(
                f"Reasoning coherence is good ({reasoning_coh:.2%}). Traces show thorough analysis."
            )
        
        # Confidence calibration feedback
        if confidence_cal < self.config.min_confidence_calibration:
            feedback_parts.append(
                f"CONFIDENCE_CALIBRATION ({confidence_cal:.2%}) is off. "
                f"Confidence scores don't align with decision certainty. "
                f"Add clear guidance on confidence assessment: "
                f"High confidence (>0.75) requires clear policy match AND solid case evidence. "
                f"Low confidence (<0.65) should trigger UNCERTAIN status. "
                f"Mid-range confidence (0.65-0.75) acceptable for met/missing with caveats."
            )
        else:
            feedback_parts.append(
                f"Confidence calibration is appropriate ({confidence_cal:.2%}). Well-aligned with decision quality."
            )
        
        # Status correctness feedback
        if status_corr < self.config.min_status_correctness:
            feedback_parts.append(
                f"STATUS_CORRECTNESS ({status_corr:.2%}) could be better. "
                f"Decisions may not match actual policy requirements or evidence quality. "
                f"Strengthen instructions about when to return met vs missing vs uncertain. "
                f"Emphasize abstaining (uncertain) when evidence is insufficient."
            )
        else:
            feedback_parts.append(
                f"Status decisions are accurate ({status_corr:.2%}). Good alignment with requirements."
            )
        
        return " ".join(feedback_parts)
    
    def make_reflective_dataset(
        self,
        candidate: Dict[str, Any],
        eval_result: EvaluationResult,
        components_to_update: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Build reflective dataset for GEPA's reflection process.
        
        Args:
            candidate: Current candidate
            eval_result: Evaluation result with scores and feedback
            components_to_update: Components being optimized
            
        Returns:
            Dictionary mapping component names to example lists
        """
        examples = []
        
        # Create examples from low-quality results for reflection
        for result in eval_result.case_results:
            # Focus on cases that need improvement
            if result.confidence < 0.7 or result.status.value == "uncertain":
                examples.append({
                    "criterion_id": result.criterion_id,
                    "status": result.status.value,
                    "confidence": result.confidence,
                    "citation_quality": "good" if result.citation.doc != "N/A" else "poor",
                    "reasoning_steps": len(result.reasoning_trace),
                    "feedback": f"Confidence {result.confidence:.2f}, citation {'present' if result.citation.doc != 'N/A' else 'missing'}",
                })
        
        return {
            "system_prompt": examples
        }


class PromptOptimizer:
    """Main GEPA optimization orchestrator."""
    
    def __init__(
        self,
        retrieval_service: Any,
        config: Optional[OptimizationConfig] = None,
    ):
        """Initialize optimizer.
        
        Args:
            retrieval_service: RetrievalService instance
            config: Optimization configuration
        """
        self.retrieval_service = retrieval_service
        self.config = config or OptimizationConfig()
        
        # Ensure output directory exists
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def optimize_prompt(
        self,
        seed_prompt: str,
        trainset: List[Dict[str, Any]],
        valset: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Run GEPA optimization process.
        
        Args:
            seed_prompt: Initial system prompt
            trainset: Training cases for optimization
            valset: Validation cases for final evaluation
            
        Returns:
            Dictionary with best_candidate, metrics, and optimization history
        """
        print(f"Starting GEPA optimization with {len(trainset)} training cases")
        print(f"Target aggregate score: {self.config.target_aggregate_score:.2%}")
        
        # Initialize GEPA
        reflection_lm = dspy.LM(
            model=self.config.reflection_model,
            temperature=self.config.reflection_temperature,
            max_tokens=self.config.reflection_max_tokens,
        )
        
        gepa = dspy.GEPA(
            metric=self._create_feedback_metric(),
            auto=self.config.auto_mode,
            max_metric_calls=self.config.max_metric_calls,
            reflection_minibatch_size=self.config.reflection_minibatch_size,
            reflection_lm=reflection_lm,
            candidate_selection_strategy=self.config.candidate_selection_strategy,
            track_stats=self.config.track_stats,
            skip_perfect_score=self.config.skip_perfect_score,
        )
        
        # Initialize adapter
        adapter = ReActControllerAdapter(
            retrieval_service=self.retrieval_service,
            test_cases=trainset,
            config=self.config,
        )
        
        # Prepare seed candidate
        seed_candidate = {"system_prompt": seed_prompt}
        
        # Run optimization
        print("Running GEPA optimization loop...")
        result = await self._run_optimization(
            gepa, adapter, seed_candidate, trainset, valset
        )
        
        # Save results
        self._save_results(result)
        
        return result
    
    def _create_feedback_metric(self):
        """Create metric function that returns scores and feedback.
        
        Returns:
            Metric function for GEPA
        """
        def metric_with_feedback(example, prediction, trace=None):
            # Extract score and feedback from prediction
            if hasattr(prediction, "aggregate_score"):
                score = prediction.aggregate_score
            else:
                score = 0.5
            
            if hasattr(prediction, "feedback"):
                feedback = prediction.feedback
            else:
                feedback = "No feedback available"
            
            return dspy.Prediction(score=score, feedback=feedback)
        
        return metric_with_feedback
    
    async def _run_optimization(
        self,
        gepa: dspy.GEPA,
        adapter: ReActControllerAdapter,
        seed_candidate: Dict[str, Any],
        trainset: List[Dict[str, Any]],
        valset: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute GEPA optimization.
        
        Args:
            gepa: GEPA optimizer instance
            adapter: ReActController adapter
            seed_candidate: Initial candidate
            trainset: Training cases
            valset: Validation cases
            
        Returns:
            Optimization result dictionary
        """
        try:
            # Convert to GEPA format if needed
            trainset_formatted = [
                {"inputs": case, "outputs": None} for case in trainset
            ]
            valset_formatted = [
                {"inputs": case, "outputs": None} for case in valset
            ]
            
            # Run GEPA compilation/optimization
            result = gepa.compile(
                student=seed_candidate,
                trainset=trainset_formatted,
                valset=valset_formatted,
            )
            
            # Evaluate best candidate on validation set
            best_prompt = result.get("system_prompt", seed_candidate["system_prompt"])
            val_result = await adapter.evaluate_candidate(
                {"system_prompt": best_prompt},
                valset[:10],  # Use subset for validation
            )
            
            return {
                "best_candidate": {"system_prompt": best_prompt},
                "train_score": result.get("train_score", 0.0),
                "val_score": val_result.aggregate_score,
                "val_metrics": {
                    "citation_accuracy": val_result.citation_accuracy,
                    "reasoning_coherence": val_result.reasoning_coherence,
                    "confidence_calibration": val_result.confidence_calibration,
                    "status_correctness": val_result.status_correctness,
                },
                "optimization_stats": result.get("stats", {}),
            }
            
        except Exception as e:
            print(f"GEPA optimization failed: {e}")
            return {
                "best_candidate": seed_candidate,
                "error": str(e),
                "train_score": 0.0,
                "val_score": 0.0,
            }
    
    def _save_results(self, result: Dict[str, Any]) -> None:
        """Save optimization results to disk.
        
        Args:
            result: Optimization result dictionary
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = self.config.output_dir / f"optimization_{timestamp}.json"
        
        # Save main results
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        
        # Save best prompt separately
        prompt_path = self.config.output_dir / f"prompt_{timestamp}.txt"
        with open(prompt_path, "w") as f:
            f.write(result["best_candidate"]["system_prompt"])
        
        print(f"Results saved to {output_path}")
        print(f"Best prompt saved to {prompt_path}")
```

## Configuration

Add the following to `src/reasoning_service/config.py`:

```python
# GEPA Optimization Configuration
GEPA_ENABLED: bool = Field(default=False, description="Enable GEPA prompt optimization")
GEPA_AUTO_MODE: str = Field(default="medium", description="GEPA auto mode: light, medium, heavy")
GEPA_MAX_ITERATIONS: int = Field(default=150, description="Maximum GEPA metric calls")
GEPA_TARGET_SCORE: float = Field(default=0.8, description="Target aggregate score")
GEPA_REFLECTION_MODEL: str = Field(default="gpt-4o", description="Model for reflection")
GEPA_TASK_MODEL: str = Field(default="gpt-4o-mini", description="Model being optimized")

# Optimization metric weights
GEPA_CITATION_WEIGHT: float = Field(default=0.4, description="Citation accuracy weight")
GEPA_REASONING_WEIGHT: float = Field(default=0.3, description="Reasoning coherence weight")
GEPA_CONFIDENCE_WEIGHT: float = Field(default=0.2, description="Confidence calibration weight")
GEPA_STATUS_WEIGHT: float = Field(default=0.1, description="Status correctness weight")
```

## Usage Examples

### Basic Usage

```python
# scripts/optimize_react_prompt.py
"""Script to run GEPA optimization on ReActController prompt."""

import asyncio
from pathlib import Path

from reasoning_service.services.prompt_optimizer import PromptOptimizer, OptimizationConfig
from reasoning_service.services.retrieval import RetrievalService
from reasoning_service.prompts.react_system_prompt import REACT_SYSTEM_PROMPT
from policy_ingest.pageindex_client import PageIndexClient


async def main():
    """Run GEPA optimization."""
    
    # Initialize services
    pageindex_client = PageIndexClient()
    retrieval_service = RetrievalService(pageindex_client=pageindex_client)
    
    # Load test cases
    test_cases = load_test_cases()
    trainset = test_cases[:50]  # Use 50 for training
    valset = test_cases[50:70]  # Use 20 for validation
    
    # Configure optimization
    config = OptimizationConfig(
        auto_mode="medium",
        max_metric_calls=150,
        target_aggregate_score=0.8,
        reflection_model="gpt-4o",
        task_model="gpt-4o-mini",
        output_dir=Path("optimization_results"),
    )
    
    # Create optimizer
    optimizer = PromptOptimizer(
        retrieval_service=retrieval_service,
        config=config,
    )
    
    # Run optimization
    result = await optimizer.optimize_prompt(
        seed_prompt=REACT_SYSTEM_PROMPT,
        trainset=trainset,
        valset=valset,
    )
    
    # Display results
    print("\n" + "="*80)
    print("OPTIMIZATION COMPLETE")
    print("="*80)
    print(f"Training Score: {result['train_score']:.2%}")
    print(f"Validation Score: {result['val_score']:.2%}")
    print("\nValidation Metrics:")
    for metric, score in result['val_metrics'].items():
        print(f"  {metric}: {score:.2%}")
    
    print(f"\nBest prompt saved to: {config.output_dir}")
    
    return result


def load_test_cases():
    """Load test cases from fixtures."""
    import json
    from pathlib import Path
    
    fixture_dir = Path("tests/data/cases")
    test_cases = []
    
    for case_file in fixture_dir.glob("*.json"):
        with open(case_file) as f:
            case_data = json.load(f)
            test_cases.append(case_data)
    
    return test_cases


if __name__ == "__main__":
    asyncio.run(main())
```

### Automated Retraining Trigger

```python
# src/reasoning_service/services/quality_monitor.py
"""Monitor quality metrics and trigger GEPA optimization when needed."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

from reasoning_service.services.prompt_optimizer import PromptOptimizer, OptimizationConfig
from reasoning_service.models.policy import ReasoningOutput
from reasoning_service.config import get_db


class QualityMonitor:
    """Monitor ReActController quality and trigger optimization."""
    
    def __init__(
        self,
        retrieval_service,
        check_interval_hours: int = 24,
        quality_threshold: float = 0.75,
    ):
        self.retrieval_service = retrieval_service
        self.check_interval_hours = check_interval_hours
        self.quality_threshold = quality_threshold
        self.optimizer = PromptOptimizer(retrieval_service=retrieval_service)
    
    async def monitor_and_optimize(self):
        """Monitor quality metrics and trigger optimization if needed."""
        
        while True:
            # Wait for check interval
            await asyncio.sleep(self.check_interval_hours * 3600)
            
            # Calculate recent quality metrics
            metrics = await self._calculate_recent_metrics()
            
            # Check if optimization needed
            if metrics["aggregate_score"] < self.quality_threshold:
                print(f"Quality degradation detected: {metrics['aggregate_score']:.2%}")
                print("Triggering GEPA optimization...")
                
                # Run optimization
                await self._run_optimization(metrics)
    
    async def _calculate_recent_metrics(self) -> Dict[str, float]:
        """Calculate quality metrics from recent decisions."""
        
        async with get_db() as db:
            # Get decisions from last 7 days
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            
            query = select(ReasoningOutput).where(
                ReasoningOutput.created_at >= cutoff_date
            ).limit(100)
            
            result = await db.execute(query)
            decisions = result.scalars().all()
        
        if not decisions:
            return {"aggregate_score": 1.0}  # No data, assume OK
        
        # Calculate metrics
        citation_accuracy = sum(
            1 for d in decisions
            if d.citation_doc and d.citation_doc != "N/A"
        ) / len(decisions)
        
        # Additional metric calculations...
        
        aggregate_score = citation_accuracy * 0.4  # Simplified
        
        return {
            "aggregate_score": aggregate_score,
            "citation_accuracy": citation_accuracy,
            "sample_size": len(decisions),
        }
    
    async def _run_optimization(self, current_metrics: Dict[str, float]):
        """Run optimization with current prompt as seed."""
        from reasoning_service.prompts.react_system_prompt import REACT_SYSTEM_PROMPT
        
        # Load test cases
        test_cases = self._load_test_cases()
        
        # Run optimization
        result = await self.optimizer.optimize_prompt(
            seed_prompt=REACT_SYSTEM_PROMPT,
            trainset=test_cases[:50],
            valset=test_cases[50:70],
        )
        
        # Log results and notify
        print(f"Optimization complete. New score: {result['val_score']:.2%}")
        
        # Would trigger approval workflow here
        await self._request_approval(result)
    
    def _load_test_cases(self) -> List[Dict]:
        """Load test cases for optimization."""
        # Implementation
        pass
    
    async def _request_approval(self, result: Dict):
        """Request manual approval for optimized prompt."""
        # Implementation - could send notification, create PR, etc.
        pass
```

## Integration Points

### 1. Prompt Registry Integration

```python
# src/reasoning_service/services/prompt_registry.py
"""Manage prompt versions and A/B testing."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import json
from pathlib import Path


@dataclass
class PromptVersion:
    """A versioned prompt."""
    
    version_id: str
    prompt_text: str
    created_at: datetime
    metrics: Dict[str, float]
    status: str  # draft, approved, active, retired
    parent_version: Optional[str] = None
    optimization_run_id: Optional[str] = None


class PromptRegistry:
    """Registry for managing prompt versions."""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._versions: Dict[str, PromptVersion] = {}
        self._load_versions()
    
    def register_prompt(
        self,
        prompt_text: str,
        metrics: Dict[str, float],
        parent_version: Optional[str] = None,
        optimization_run_id: Optional[str] = None,
    ) -> str:
        """Register a new prompt version."""
        
        version_id = f"v{len(self._versions) + 1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        version = PromptVersion(
            version_id=version_id,
            prompt_text=prompt_text,
            created_at=datetime.now(),
            metrics=metrics,
            status="draft",
            parent_version=parent_version,
            optimization_run_id=optimization_run_id,
        )
        
        self._versions[version_id] = version
        self._save_version(version)
        
        return version_id
    
    def approve_prompt(self, version_id: str):
        """Approve a prompt for production use."""
        if version_id in self._versions:
            self._versions[version_id].status = "approved"
            self._save_version(self._versions[version_id])
    
    def activate_prompt(self, version_id: str):
        """Activate a prompt (mark as current production prompt)."""
        # Retire current active prompts
        for version in self._versions.values():
            if version.status == "active":
                version.status = "retired"
                self._save_version(version)
        
        # Activate new prompt
        if version_id in self._versions:
            self._versions[version_id].status = "active"
            self._save_version(self._versions[version_id])
    
    def get_active_prompt(self) -> Optional[PromptVersion]:
        """Get the currently active prompt."""
        for version in self._versions.values():
            if version.status == "active":
                return version
        return None
    
    def _load_versions(self):
        """Load versions from disk."""
        for version_file in self.storage_path.glob("*.json"):
            with open(version_file) as f:
                data = json.load(f)
                version = PromptVersion(
                    version_id=data["version_id"],
                    prompt_text=data["prompt_text"],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    metrics=data["metrics"],
                    status=data["status"],
                    parent_version=data.get("parent_version"),
                    optimization_run_id=data.get("optimization_run_id"),
                )
                self._versions[version.version_id] = version
    
    def _save_version(self, version: PromptVersion):
        """Save version to disk."""
        version_file = self.storage_path / f"{version.version_id}.json"
        with open(version_file, "w") as f:
            json.dump({
                "version_id": version.version_id,
                "prompt_text": version.prompt_text,
                "created_at": version.created_at.isoformat(),
                "metrics": version.metrics,
                "status": version.status,
                "parent_version": version.parent_version,
                "optimization_run_id": version.optimization_run_id,
            }, f, indent=2)
```

### 2. CLI Integration

```bash
# Add to pyproject.toml [tool.poetry.scripts] or equivalent
optimize-prompt = "scripts.optimize_react_prompt:main"
```

```python
# Usage
poetry run optimize-prompt --trainset tests/data/cases/ --max-iterations 150
```

## Monitoring and Evaluation

### Prometheus Metrics

```python
# Add to src/reasoning_service/observability/react_metrics.py

from prometheus_client import Counter, Histogram, Gauge

# GEPA optimization metrics
gepa_optimizations_total = Counter(
    "gepa_optimizations_total",
    "Total number of GEPA optimization runs",
    ["status"]  # success, failure
)

gepa_optimization_duration_seconds = Histogram(
    "gepa_optimization_duration_seconds",
    "Time taken for GEPA optimization",
    buckets=[60, 300, 600, 1800, 3600]  # 1min to 1hour
)

gepa_prompt_score = Gauge(
    "gepa_prompt_score",
    "Current active prompt score",
    ["metric_type"]  # aggregate, citation_accuracy, reasoning_coherence, etc.
)

gepa_evaluations_per_run = Histogram(
    "gepa_evaluations_per_run",
    "Number of candidate evaluations per optimization run",
    buckets=[10, 50, 100, 150, 200]
)
```

### Dashboard Queries

```promql
# Optimization success rate
rate(gepa_optimizations_total{status="success"}[7d]) /
rate(gepa_optimizations_total[7d])

# Average optimization time
rate(gepa_optimization_duration_seconds_sum[7d]) /
rate(gepa_optimization_duration_seconds_count[7d])

# Prompt quality trend
gepa_prompt_score{metric_type="aggregate"}
```

## Troubleshooting

### Common Issues

1. **GEPA fails to improve scores**
   - Check evaluation metric alignment with actual quality
   - Increase `max_metric_calls` for more exploration
   - Try different `reflection_model` (gpt-4o vs gpt-5)
   - Review feedback generation - ensure it's specific and actionable

2. **Optimization runs out of memory**
   - Reduce `reflection_minibatch_size`
   - Use smaller trainset/valset
   - Clear cache between runs

3. **Optimized prompt performs worse**
   - Overfitting to training set
   - Increase valset size
   - Add more diverse test cases
   - Review Pareto frontier for balanced candidates

### Debug Mode

```python
config = OptimizationConfig(
    track_stats=True,
    save_intermediate=True,
    # ... other settings
)

# This will save:
# - optimization_results/intermediate_candidates/
# - optimization_results/evaluation_traces/
# - optimization_results/reflection_logs/
```

## Next Steps

1. **Implement additional tools** (see section on Medical Knowledge Tools)
2. **Add multi-agent evaluation** for complex cases
3. **Integrate with MLflow** for prompt registry
4. **Set up automated retraining pipeline**
5. **Build approval workflow** for optimized prompts

## References

- [GEPA Paper](https://arxiv.org/abs/2507.19457)
- [DSPy Documentation](https://dspy.ai/api/optimizers/GEPA/overview/)
- [GEPA GitHub](https://github.com/gepa-ai/gepa)
- [DSPy GEPA Tutorials](https://dspy.ai/tutorials/gepa_ai_program/)

