"""Tool definitions for ReAct controller."""

from typing import Dict, Any, List


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Get OpenAI function calling tool schemas.

    Returns:
        List of tool definitions in OpenAI function calling format.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "pi_search",
                "description": (
                    "Search the policy document using PageIndex LLM Tree Search. "
                    "Use this to find relevant policy sections and requirements. "
                    "Returns: node_ids, page_refs, relevant_paragraphs, search_trajectory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query describing what policy information you need (e.g., 'What are the age requirements for lumbar MRI?')",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of nodes to retrieve (default: 3)",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "facts_get",
                "description": (
                    "Retrieve a specific field value from the case bundle. "
                    "Use this to get patient information extracted by VLM. "
                    "Returns: field value with confidence score and document location."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "field_name": {
                            "type": "string",
                            "description": "Name of the field to retrieve (e.g., 'patient_age', 'diagnosis_code', 'physical_therapy_duration')",
                        },
                    },
                    "required": ["field_name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "spans_tighten",
                "description": (
                    "Use BM25 ranking to narrow down spans within a selected policy node. "
                    "Only use this when policy spans are too long (>800 tokens) or contain noise. "
                    "Returns: ranked list of most relevant paragraphs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "Node ID from pi_search result to tighten",
                        },
                        "query": {
                            "type": "string",
                            "description": "Specific requirement you're looking for within the node",
                        },
                    },
                    "required": ["node_id", "query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "policy_xref",
                "description": (
                    "Cross-reference related policy sections for a given criterion. "
                    "Use when a criterion is ambiguous or references 'see also'. "
                    "Returns: related nodes and citations."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "criterion_id": {
                            "type": "string",
                            "description": "Criterion identifier from metadata (e.g., 'lumbar-mri-pt')",
                        },
                    },
                    "required": ["criterion_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "temporal_lookup",
                "description": (
                    "Lookup policy version as of a specific date and provide diffs. "
                    "Use when the case has a service date or version constraints. "
                    "Returns: version metadata and changed node IDs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "policy_id": {
                            "type": "string",
                            "description": "Policy identifier (e.g., 'LCD-L34220')",
                        },
                        "as_of_date": {
                            "type": "string",
                            "description": "Date in YYYY-MM-DD format to resolve effective version",
                        },
                    },
                    "required": ["policy_id", "as_of_date"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "confidence_score",
                "description": (
                    "Aggregate confidence across criterion results. "
                    "Use before finishing to compute final decision confidence. "
                    "Returns: overall score and per-criterion breakdown."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "criteria_results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "status": {"type": "string", "enum": ["met", "missing", "uncertain"]},
                                    "confidence": {"type": "number"},
                                },
                                "required": ["id", "status"],
                                "additionalProperties": True,
                            },
                            "description": "List of per-criterion interim outcomes to aggregate",
                        },
                    },
                    "required": ["criteria_results"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "contradiction_detector",
                "description": (
                    "Detect conflicting evidence across findings. "
                    "Use when signals disagree or sources conflict. "
                    "Returns: conflicts per criterion and resolution hints."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "findings": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "criterion_id": {"type": "string"},
                                    "evidence": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "node_id": {"type": "string"},
                                                "snippet": {"type": "string"},
                                                "stance": {"type": "string", "enum": ["support", "oppose", "neutral"]},
                                            },
                                            "required": ["stance"],
                                            "additionalProperties": True,
                                        },
                                    },
                                },
                                "required": ["criterion_id", "evidence"],
                                "additionalProperties": False,
                            },
                            "description": "Evidence sets with stances per criterion",
                        },
                    },
                    "required": ["findings"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "pubmed_search",
                "description": (
                    "Search PubMed for clinical evidence relevant to the condition and treatment. "
                    "Use sparingly for borderline cases or when policy instructs to consult evidence. "
                    "Returns: studies and a brief summary."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "condition": {
                            "type": "string",
                            "description": "Condition or diagnosis (e.g., 'low back pain')",
                        },
                        "treatment": {
                            "type": "string",
                            "description": "Treatment or procedure (e.g., 'lumbar MRI')",
                        },
                    },
                    "required": ["condition", "treatment"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "code_validator",
                "description": (
                    "Validate and normalize ICD-10 and CPT codes. "
                    "Use to ensure codes conform to expected formats and suggest corrections. "
                    "Returns: validity flag, normalized codes, and suggestions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "icd10": {
                            "type": ["string", "null"],
                            "description": "ICD-10-CM diagnosis code (optional)",
                        },
                        "cpt": {
                            "type": ["string", "null"],
                            "description": "CPT procedure code (optional)",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": (
                    "Submit your final decision after analyzing policy and case facts. "
                    "You MUST call this when you have enough information to make a determination. "
                    "Status values: 'met' (requirement satisfied), 'missing' (requirement not met), 'uncertain' (insufficient info)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["met", "missing", "uncertain"],
                            "description": "Final decision status",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Clear explanation of your reasoning (2-3 sentences)",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Your confidence in this decision (0.0-1.0). Use <0.65 for uncertain cases.",
                        },
                        "policy_section": {
                            "type": "string",
                            "description": "Section path from policy tree (e.g., 'Section 2.1.3')",
                        },
                        "policy_pages": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Page numbers where requirement is stated",
                        },
                        "evidence_doc_id": {
                            "type": ["string", "null"],
                            "description": "Document ID where evidence was found (if applicable)",
                        },
                        "evidence_page": {
                            "type": ["integer", "null"],
                            "description": "Page number of evidence (if applicable)",
                        },
                    },
                    "required": ["status", "rationale", "confidence", "policy_section", "policy_pages"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
    ]

