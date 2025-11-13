# Additional Tools for ReActController

This document outlines additional tools that can be integrated into the ReActController to enhance medical policy verification capabilities.

## Table of Contents

1. [Medical Knowledge Tools](#medical-knowledge-tools)
2. [Policy Analysis Tools](#policy-analysis-tools)
3. [Evidence Synthesis Tools](#evidence-synthesis-tools)
4. [Multi-Agent Collaboration](#multi-agent-collaboration)
5. [Implementation Patterns](#implementation-patterns)

## Medical Knowledge Tools

### 1. PubMed Literature Search

Search medical literature for evidence-based guidelines and clinical research.

```python
# src/reasoning_service/services/medical_tools.py

from typing import Dict, List, Any
import requests


class PubMedSearchTool:
    """Search PubMed for medical literature."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Search PubMed and return relevant articles.
        
        Args:
            query: Search terms (e.g., "lumbar MRI indication lower back pain")
            max_results: Maximum number of results to return
            
        Returns:
            Dictionary with articles list
        """
        # Search for PMIDs
        search_url = f"{self.base_url}/esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        }
        
        response = requests.get(search_url, params=search_params)
        pmids = response.json().get("esearchresult", {}).get("idlist", [])
        
        if not pmids:
            return {
                "success": True,
                "articles": [],
                "message": "No articles found"
            }
        
        # Fetch article details
        fetch_url = f"{self.base_url}/esummary.fcgi"
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        }
        
        response = requests.get(fetch_url, params=fetch_params)
        results = response.json().get("result", {})
        
        articles = []
        for pmid in pmids:
            if pmid in results:
                article = results[pmid]
                articles.append({
                    "pmid": pmid,
                    "title": article.get("title", ""),
                    "authors": article.get("authors", []),
                    "source": article.get("source", ""),
                    "pubdate": article.get("pubdate", ""),
                    "doi": article.get("elocationid", ""),
                })
        
        return {
            "success": True,
            "articles": articles,
            "count": len(articles)
        }


def get_pubmed_tool_definition() -> Dict[str, Any]:
    """Get PubMed tool definition for ReAct controller."""
    return {
        "type": "function",
        "function": {
            "name": "pubmed_search",
            "description": (
                "Search PubMed medical literature database for evidence-based "
                "guidelines, clinical studies, and research supporting medical decisions. "
                "Use this to validate clinical appropriateness of procedures."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Medical search query (e.g., 'lumbar MRI indication chronic low back pain')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of articles to retrieve (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
```

### 2. ICD-10 Code Lookup

Validate and expand diagnosis codes with descriptions and hierarchy.

```python
class ICD10LookupTool:
    """Lookup ICD-10 diagnosis codes."""
    
    def __init__(self, icd10_database_path: str):
        self.database = self._load_database(icd10_database_path)
    
    def lookup(
        self, 
        code: str, 
        include_children: bool = False
    ) -> Dict[str, Any]:
        """Lookup ICD-10 code details.
        
        Args:
            code: ICD-10 code (e.g., "M54.5")
            include_children: Include child codes in hierarchy
            
        Returns:
            Dictionary with code details
        """
        code = code.upper().strip()
        
        if code not in self.database:
            return {
                "success": False,
                "message": f"ICD-10 code {code} not found",
                "code": code
            }
        
        code_info = self.database[code]
        result = {
            "success": True,
            "code": code,
            "description": code_info["description"],
            "category": code_info["category"],
            "is_billable": code_info["billable"],
            "parent_code": code_info.get("parent"),
        }
        
        if include_children:
            children = [
                c for c in self.database
                if self.database[c].get("parent") == code
            ]
            result["child_codes"] = children
        
        return result
    
    def _load_database(self, path: str) -> Dict[str, Dict]:
        """Load ICD-10 database from file."""
        # Implementation would load from JSON/CSV file
        # For now, return a sample database
        return {
            "M54.5": {
                "description": "Low back pain",
                "category": "Dorsalgia",
                "billable": True,
                "parent": "M54"
            },
            "M51.16": {
                "description": "Intervertebral disc disorders with radiculopathy, lumbar region",
                "category": "Intervertebral disc disorders",
                "billable": True,
                "parent": "M51.1"
            },
            # Additional codes...
        }


def get_icd10_tool_definition() -> Dict[str, Any]:
    """Get ICD-10 lookup tool definition."""
    return {
        "type": "function",
        "function": {
            "name": "icd10_lookup",
            "description": (
                "Look up ICD-10 diagnosis code details including description, "
                "category, and billability. Use this to validate diagnosis codes "
                "and understand their clinical meaning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "ICD-10 code to lookup (e.g., 'M54.5', 'M51.16')",
                    },
                    "include_children": {
                        "type": "boolean",
                        "description": "Include child codes in hierarchy (default: false)",
                        "default": False,
                    },
                },
                "required": ["code"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
```

### 3. Drug Interaction Checker

Check for medication interactions and contraindications.

```python
class DrugInteractionTool:
    """Check drug interactions."""
    
    def check_interactions(
        self,
        medications: List[str],
        patient_conditions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Check for drug interactions and contraindications.
        
        Args:
            medications: List of medication names
            patient_conditions: Optional list of patient conditions
            
        Returns:
            Dictionary with interactions and warnings
        """
        # This would integrate with a drug interaction database
        # For demonstration, using simplified logic
        
        interactions = []
        contraindications = []
        
        # Example interaction checking logic
        if "warfarin" in [m.lower() for m in medications]:
            for med in medications:
                if med.lower() in ["aspirin", "ibuprofen", "naproxen"]:
                    interactions.append({
                        "severity": "major",
                        "drugs": ["warfarin", med],
                        "description": "Increased bleeding risk when combined with NSAIDs",
                        "recommendation": "Consider alternative pain management or increase monitoring"
                    })
        
        if patient_conditions:
            # Check contraindications
            if "kidney disease" in [c.lower() for c in patient_conditions]:
                for med in medications:
                    if med.lower() in ["ibuprofen", "naproxen"]:
                        contraindications.append({
                            "drug": med,
                            "condition": "kidney disease",
                            "severity": "major",
                            "description": "NSAIDs can worsen kidney function"
                        })
        
        return {
            "success": True,
            "interactions": interactions,
            "contraindications": contraindications,
            "requires_review": len(interactions) > 0 or len(contraindications) > 0
        }


def get_drug_interaction_tool_definition() -> Dict[str, Any]:
    """Get drug interaction tool definition."""
    return {
        "type": "function",
        "function": {
            "name": "check_drug_interactions",
            "description": (
                "Check for drug interactions and contraindications based on "
                "medication list and patient conditions. Use this to evaluate "
                "medication safety."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "medications": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of medication names",
                    },
                    "patient_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of patient conditions/diagnoses",
                    },
                },
                "required": ["medications"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
```

## Policy Analysis Tools

### 1. Cross-Reference Checker

Find related requirements across policy sections.

```python
class PolicyCrossReferenceTool:
    """Check cross-references in policy documents."""
    
    def __init__(self, retrieval_service):
        self.retrieval_service = retrieval_service
    
    async def find_related_sections(
        self,
        policy_doc_id: str,
        current_section: str,
        requirement_type: str
    ) -> Dict[str, Any]:
        """Find related policy sections.
        
        Args:
            policy_doc_id: PageIndex document ID
            current_section: Current section path
            requirement_type: Type of requirement (e.g., "age", "duration", "diagnosis")
            
        Returns:
            Dictionary with related sections
        """
        # Search for related sections
        query = f"{requirement_type} requirements related to {current_section}"
        
        result = await self.retrieval_service.retrieve(
            document_id=policy_doc_id,
            query=query,
            top_k=5
        )
        
        related_sections = []
        for node in result.node_refs:
            if node.title != current_section:  # Exclude current section
                related_sections.append({
                    "section_path": node.title,
                    "pages": node.pages,
                    "relevance": result.confidence,
                    "summary": node.summary
                })
        
        return {
            "success": True,
            "current_section": current_section,
            "related_sections": related_sections,
            "count": len(related_sections)
        }


def get_cross_reference_tool_definition() -> Dict[str, Any]:
    """Get cross-reference tool definition."""
    return {
        "type": "function",
        "function": {
            "name": "policy_cross_reference",
            "description": (
                "Find related requirements across multiple policy sections. "
                "Use this to discover additional requirements or exceptions "
                "mentioned in other parts of the policy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "current_section": {
                        "type": "string",
                        "description": "Current policy section path",
                    },
                    "requirement_type": {
                        "type": "string",
                        "description": "Type of requirement to search for (e.g., 'age', 'duration', 'diagnosis')",
                    },
                },
                "required": ["current_section", "requirement_type"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
```

### 2. Temporal Policy Analysis

Check policy effective dates and version history.

```python
class TemporalPolicyTool:
    """Analyze policy temporal constraints."""
    
    def check_policy_version(
        self,
        policy_id: str,
        service_date: str,
        db_session
    ) -> Dict[str, Any]:
        """Check which policy version was effective on service date.
        
        Args:
            policy_id: Policy identifier
            service_date: Date of service (ISO format)
            db_session: Database session
            
        Returns:
            Dictionary with applicable policy version
        """
        from datetime import datetime
        from sqlalchemy import select
        from reasoning_service.models.policy import PolicyVersion
        
        service_dt = datetime.fromisoformat(service_date)
        
        # Query for policy version effective on service date
        query = (
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy_id)
            .where(PolicyVersion.effective_date <= service_dt)
            .order_by(PolicyVersion.effective_date.desc())
        )
        
        result = db_session.execute(query)
        policy_version = result.scalar_one_or_none()
        
        if not policy_version:
            return {
                "success": False,
                "message": f"No policy version found effective on {service_date}",
                "policy_id": policy_id,
                "service_date": service_date
            }
        
        return {
            "success": True,
            "policy_id": policy_id,
            "version_id": policy_version.version_id,
            "effective_date": policy_version.effective_date.isoformat(),
            "pageindex_doc_id": policy_version.pageindex_doc_id,
            "grandfathered": service_dt < policy_version.effective_date
        }


def get_temporal_analysis_tool_definition() -> Dict[str, Any]:
    """Get temporal analysis tool definition."""
    return {
        "type": "function",
        "function": {
            "name": "policy_temporal_check",
            "description": (
                "Check which policy version was effective on a specific date. "
                "Use this to ensure you're applying the correct policy version "
                "for the service date."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "policy_id": {
                        "type": "string",
                        "description": "Policy identifier (e.g., 'LCD-L34220')",
                    },
                    "service_date": {
                        "type": "string",
                        "description": "Date of service in ISO format (YYYY-MM-DD)",
                    },
                },
                "required": ["policy_id", "service_date"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
```

## Evidence Synthesis Tools

### 1. Confidence Aggregator

Combine evidence from multiple sources using Bayesian updating.

```python
class ConfidenceAggregatorTool:
    """Aggregate confidence scores from multiple sources."""
    
    def aggregate(
        self,
        evidence_sources: List[Dict[str, Any]],
        aggregation_method: str = "bayesian"
    ) -> Dict[str, Any]:
        """Aggregate confidence scores.
        
        Args:
            evidence_sources: List of evidence with confidence scores
            aggregation_method: Method to use (bayesian, weighted_average, min, max)
            
        Returns:
            Dictionary with aggregated confidence
        """
        if not evidence_sources:
            return {
                "success": False,
                "message": "No evidence sources provided"
            }
        
        confidences = [e.get("confidence", 0.0) for e in evidence_sources]
        
        if aggregation_method == "bayesian":
            # Simplified Bayesian updating
            prior = 0.5
            posterior = prior
            for conf in confidences:
                likelihood = conf
                posterior = (likelihood * posterior) / (
                    (likelihood * posterior) + ((1 - likelihood) * (1 - posterior))
                )
            aggregated = posterior
            
        elif aggregation_method == "weighted_average":
            weights = [e.get("weight", 1.0) for e in evidence_sources]
            total_weight = sum(weights)
            aggregated = sum(c * w for c, w in zip(confidences, weights)) / total_weight
            
        elif aggregation_method == "min":
            aggregated = min(confidences)
            
        elif aggregation_method == "max":
            aggregated = max(confidences)
            
        else:
            aggregated = sum(confidences) / len(confidences)
        
        return {
            "success": True,
            "aggregated_confidence": aggregated,
            "method": aggregation_method,
            "source_count": len(evidence_sources),
            "confidence_range": [min(confidences), max(confidences)]
        }


def get_confidence_aggregator_tool_definition() -> Dict[str, Any]:
    """Get confidence aggregator tool definition."""
    return {
        "type": "function",
        "function": {
            "name": "aggregate_confidence",
            "description": (
                "Aggregate confidence scores from multiple evidence sources "
                "using various methods. Use this when you have multiple pieces "
                "of evidence that support or contradict a conclusion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evidence_sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "confidence": {"type": "number"},
                                "weight": {"type": "number"}
                            }
                        },
                        "description": "List of evidence sources with confidence scores",
                    },
                    "aggregation_method": {
                        "type": "string",
                        "enum": ["bayesian", "weighted_average", "min", "max"],
                        "description": "Method to aggregate confidences (default: bayesian)",
                        "default": "bayesian"
                    },
                },
                "required": ["evidence_sources"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
```

### 2. Contradiction Detector

Detect conflicting information in case data.

```python
class ContradictionDetectorTool:
    """Detect contradictions in case facts."""
    
    def detect(self, case_facts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect contradictions in case facts.
        
        Args:
            case_facts: List of extracted facts
            
        Returns:
            Dictionary with detected contradictions
        """
        contradictions = []
        
        # Group facts by field name
        facts_by_field = {}
        for fact in case_facts:
            field = fact.get("field_name")
            if field not in facts_by_field:
                facts_by_field[field] = []
            facts_by_field[field].append(fact)
        
        # Check for multiple different values for same field
        for field, facts in facts_by_field.items():
            if len(facts) > 1:
                values = [f.get("value") for f in facts]
                unique_values = set(str(v) for v in values)
                
                if len(unique_values) > 1:
                    contradictions.append({
                        "field": field,
                        "values": list(unique_values),
                        "sources": [
                            {
                                "value": f.get("value"),
                                "doc_id": f.get("doc_id"),
                                "page": f.get("page"),
                                "confidence": f.get("confidence")
                            }
                            for f in facts
                        ],
                        "severity": "high" if len(unique_values) > 2 else "medium"
                    })
        
        # Check for logical inconsistencies
        # e.g., treatment start date after service date
        for fact in case_facts:
            if fact.get("field_name") == "treatment_start_date":
                start_date = fact.get("value")
                # Additional logic to check against service_date
        
        return {
            "success": True,
            "has_contradictions": len(contradictions) > 0,
            "contradictions": contradictions,
            "count": len(contradictions)
        }


def get_contradiction_detector_tool_definition() -> Dict[str, Any]:
    """Get contradiction detector tool definition."""
    return {
        "type": "function",
        "function": {
            "name": "detect_contradictions",
            "description": (
                "Detect contradictory information in case facts. "
                "Use this when multiple documents provide different values "
                "for the same field or when logical inconsistencies exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_facts": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of extracted case facts to check",
                    },
                },
                "required": ["case_facts"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
```

## Multi-Agent Collaboration

For complex cases requiring multiple perspectives:

```python
# src/reasoning_service/services/multi_agent_controller.py

from enum import Enum
from typing import Dict, List
import asyncio


class AgentRole(Enum):
    CLINICAL_REVIEWER = "clinical_reviewer"
    POLICY_EXPERT = "policy_expert"
    COMPLIANCE_OFFICER = "compliance_officer"
    QUALITY_ASSURANCE = "quality_assurance"


class MultiAgentReActController:
    """Multi-agent extension of ReActController."""
    
    def __init__(
        self,
        llm_client,
        retrieval_service,
        enable_collaboration: bool = True
    ):
        self.llm_client = llm_client
        self.retrieval_service = retrieval_service
        self.enable_collaboration = enable_collaboration
        
        # Initialize specialized agents
        self.agents = {
            AgentRole.CLINICAL_REVIEWER: self._create_agent(
                role=AgentRole.CLINICAL_REVIEWER,
                focus="Clinical appropriateness and medical necessity"
            ),
            AgentRole.POLICY_EXPERT: self._create_agent(
                role=AgentRole.POLICY_EXPERT,
                focus="Policy interpretation and requirements"
            ),
            AgentRole.COMPLIANCE_OFFICER: self._create_agent(
                role=AgentRole.COMPLIANCE_OFFICER,
                focus="Regulatory compliance and documentation"
            ),
        }
    
    def _create_agent(self, role: AgentRole, focus: str):
        """Create specialized agent with role-specific prompt."""
        from reasoning_service.services.react_controller import ReActController
        
        # Customize system prompt for role
        role_prompt = f"""You are a {role.value} specializing in {focus}.
        Your evaluation focuses specifically on {focus} aspects of the case."""
        
        agent = ReActController(
            llm_client=self.llm_client,
            retrieval_service=self.retrieval_service,
        )
        agent._system_prompt = role_prompt
        return agent
    
    async def collaborative_evaluation(
        self,
        case_bundle,
        policy_document_id: str
    ) -> List[CriterionResult]:
        """Run multi-agent collaborative evaluation.
        
        Args:
            case_bundle: Case data
            policy_document_id: Policy document ID
            
        Returns:
            List of criterion results with agent perspectives
        """
        if not self.enable_collaboration:
            # Fall back to single agent
            return await self.agents[AgentRole.POLICY_EXPERT].evaluate_case(
                case_bundle, policy_document_id
            )
        
        # Evaluate with all agents in parallel
        agent_evaluations = await asyncio.gather(*[
            agent.evaluate_case(case_bundle, policy_document_id)
            for agent in self.agents.values()
        ], return_exceptions=True)
        
        # Synthesize results
        return self._synthesize_agent_results(agent_evaluations)
    
    def _synthesize_agent_results(
        self,
        agent_results: List[List[CriterionResult]]
    ) -> List[CriterionResult]:
        """Synthesize results from multiple agents using consensus.
        
        Args:
            agent_results: Results from each agent
            
        Returns:
            Synthesized criterion results
        """
        # Group by criterion_id
        by_criterion = {}
        for results in agent_results:
            if isinstance(results, Exception):
                continue  # Skip failed agents
            for result in results:
                if result.criterion_id not in by_criterion:
                    by_criterion[result.criterion_id] = []
                by_criterion[result.criterion_id].append(result)
        
        # Synthesize each criterion
        synthesized = []
        for criterion_id, results in by_criterion.items():
            # Use majority vote for status
            statuses = [r.status for r in results]
            status = max(set(statuses), key=statuses.count)
            
            # Average confidence
            avg_confidence = sum(r.confidence for r in results) / len(results)
            
            # Combine reasoning traces
            combined_trace = []
            for i, result in enumerate(results):
                combined_trace.append(ReasoningStep(
                    step=i + 1,
                    action=f"agent_{i}_evaluation",
                    observation=f"Agent {i}: {result.status.value} (conf: {result.confidence:.2f})"
                ))
            
            # Use highest quality citation
            best_citation = max(results, key=lambda r: r.confidence).citation
            
            synthesized.append(CriterionResult(
                criterion_id=criterion_id,
                status=status,
                evidence=results[0].evidence,
                citation=best_citation,
                rationale=f"Multi-agent consensus: {len(results)} agents evaluated",
                confidence=avg_confidence,
                confidence_breakdown=results[0].confidence_breakdown,
                search_trajectory=[],
                retrieval_method=results[0].retrieval_method,
                reasoning_trace=combined_trace,
            ))
        
        return synthesized
```

## Implementation Patterns

### Registering New Tools

To add a new tool to the ReActController:

1. **Define the tool function** in appropriate module
2. **Create tool definition** following OpenAI function calling format
3. **Add tool handler** in `ToolExecutor.execute()`
4. **Register in tool list** in `tools.py`

```python
# Example: Adding PubMed search tool

# 1. In src/reasoning_service/services/medical_tools.py
class PubMedSearchTool:
    # ... implementation ...

# 2. In src/reasoning_service/services/tools.py
def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        # Existing tools...
        get_pi_search_definition(),
        get_facts_get_definition(),
        get_spans_tighten_definition(),
        get_finish_definition(),
        
        # New medical tools
        get_pubmed_tool_definition(),
        get_icd10_tool_definition(),
        get_drug_interaction_tool_definition(),
    ]

# 3. In src/reasoning_service/services/tool_handlers.py
class ToolExecutor:
    def __init__(self, ..., pubmed_tool: Optional[PubMedSearchTool] = None):
        # ... existing init ...
        self.pubmed_tool = pubmed_tool or PubMedSearchTool()
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        if tool_name == "pubmed_search":
            result = self.pubmed_tool.search(
                query=arguments["query"],
                max_results=arguments.get("max_results", 5)
            )
            return json.dumps(result)
        # ... existing tool handlers ...
```

### Tool Testing Pattern

```python
# tests/unit/test_medical_tools.py

import pytest
from reasoning_service.services.medical_tools import PubMedSearchTool


@pytest.fixture
def pubmed_tool():
    return PubMedSearchTool()


def test_pubmed_search_success(pubmed_tool):
    """Test successful PubMed search."""
    result = pubmed_tool.search(query="lumbar MRI indication", max_results=3)
    
    assert result["success"] is True
    assert "articles" in result
    assert len(result["articles"]) <= 3
    
    if result["articles"]:
        article = result["articles"][0]
        assert "pmid" in article
        assert "title" in article


def test_pubmed_search_no_results(pubmed_tool):
    """Test PubMed search with no results."""
    result = pubmed_tool.search(query="zzz_nonexistent_query_xyz", max_results=1)
    
    assert result["success"] is True
    assert result["articles"] == []
```

## Next Steps

1. **Implement core tools** (PubMed, ICD-10, cross-reference)
2. **Test integration** with ReActController
3. **Evaluate impact** on decision quality metrics
4. **Optimize with GEPA** to learn when to use each tool
5. **Add multi-agent** for complex cases requiring multiple perspectives

## References

- [ReAct Paper](https://arxiv.org/abs/2210.03629)
- [Tool Use in LangChain](https://python.langchain.com/docs/modules/agents/tools/)
- [CrewAI Multi-Agent Framework](https://github.com/crewAIInc/crewAI)
- [PubMed E-utilities API](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [ICD-10-CM Codes](https://www.cdc.gov/nchs/icd/icd-10-cm.htm)

