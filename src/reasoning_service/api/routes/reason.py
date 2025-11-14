"""Reasoning endpoints for authorization review and QA."""

import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reasoning_service.models.schema import (
    AuthReviewRequest,
    AuthReviewResponse,
    QARequest,
    QAResponse,
)
from reasoning_service.models.policy import PolicyVersion, ReasoningOutput
from reasoning_service.config import get_db, settings
from policy_ingest.pageindex_client import PageIndexClient
from reasoning_service.services import RetrievalService, ReActController, SafetyService
from reasoning_service.services.treestore_client import TreeStoreClient

router = APIRouter()


async def load_calibration_scores(
    policy_id: str, version_id: str, db: AsyncSession, limit: int = 100
) -> list[float]:
    """
    Load historical confidence scores for conformal prediction calibration.

    Args:
        policy_id: Policy identifier
        version_id: Policy version
        db: Database session
        limit: Maximum number of historical decisions to retrieve

    Returns:
        List of c_joint confidence scores from previous decisions
    """
    query = (
        select(ReasoningOutput.c_joint)
        .where(ReasoningOutput.policy_id == policy_id)
        .where(ReasoningOutput.version_id == version_id)
        .order_by(ReasoningOutput.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    scores = [row[0] for row in result.all()]
    return scores


# Dependency injection
async def get_retrieval_service() -> RetrievalService:
    """Get retrieval service instance."""
    pageindex = PageIndexClient()
    treestore = TreeStoreClient()
    service = RetrievalService(
        pageindex_client=pageindex,
        treestore_client=treestore,
        backend=settings.retrieval_backend,
    )
    try:
        yield service
    finally:
        await service.close()


async def get_controller(
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> ReActController:
    """Get ReAct controller instance."""
    return ReActController(retrieval_service=retrieval_service)


async def get_safety_service() -> SafetyService:
    """Get safety service instance."""
    return SafetyService()


async def get_policy_document_id(
    policy_id: str, version_id: Optional[str] = None, db: AsyncSession = Depends(get_db)
) -> str:
    """
    Lookup PageIndex document ID for a policy version from database.

    Args:
        policy_id: Policy identifier (e.g., LCD-L34220)
        version_id: Optional version label (uses most recent if not specified)
        db: Database session

    Returns:
        PageIndex document ID

    Raises:
        HTTPException: If policy not found
    """
    query = select(PolicyVersion).where(PolicyVersion.policy_id == policy_id)

    if version_id:
        query = query.where(PolicyVersion.version_id == version_id)
    else:
        # Get most recent version
        query = query.order_by(PolicyVersion.ingested_at.desc())

    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=404,
            detail=f"Policy {policy_id} (version: {version_id or 'latest'}) not found in database",
        )

    return policy.pageindex_doc_id, policy.version_id


@router.post("/auth-review", response_model=AuthReviewResponse)
async def auth_review(
    request: AuthReviewRequest,
    controller: ReActController = Depends(get_controller),
    safety: SafetyService = Depends(get_safety_service),
    db: AsyncSession = Depends(get_db),
) -> AuthReviewResponse:
    """Evaluate case for authorization approval.

    This endpoint:
    1. Uses PageIndex for hierarchical policy retrieval
    2. Applies ReAct loop for reasoning and evidence linking
    3. Enforces safety mechanisms (calibration, self-consistency, conformal)
    4. Returns structured decisions with citations and confidence scores

    Args:
        request: Authorization review request with case bundle
        controller: ReAct controller (injected)
        safety: Safety service (injected)

    Returns:
        Authorization review response with criterion results

    Raises:
        HTTPException: If processing fails
    """
    start_time = time.time()
    policy_id = "LCD-L34220"  # Default
    actual_version = "v1.0"  # Default

    try:
        # Get policy document ID from database
        policy_id = getattr(request.case_bundle, "policy_id", "LCD-L34220")
        version_id = getattr(request.case_bundle, "version_id", None)

        policy_document_id, actual_version = await get_policy_document_id(
            policy_id=policy_id, version_id=version_id, db=db
        )

        # Evaluate case using ReAct controller
        results = await controller.evaluate_case(
            case_bundle=request.case_bundle, policy_document_id=policy_document_id
        )

        # Apply safety mechanisms to each result
        processed_results = []
        for result in results:
            # Apply self-consistency if requested and needed
            if request.self_consistency:
                result = await safety.apply_self_consistency(
                    criterion_result=result,
                    evaluate_fn=None,  # Callback for re-evaluation
                )

            # Apply conformal prediction with historical calibration data
            calibration_scores = await load_calibration_scores(
                policy_id=policy_id, version_id=actual_version, db=db, limit=100
            )
            result = safety.apply_conformal_prediction(result, calibration_scores)

            processed_results.append(result)

        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        return AuthReviewResponse(
            case_id=request.case_bundle.case_id,
            results=processed_results,
            policy_version_used=actual_version,
            controller_version="v0.1.0",
            prompt_id="prompt-v1",
            processing_time_ms=processing_time_ms,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        # Business logic errors (e.g., validation failures)
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except TimeoutError as e:
        # PageIndex or controller timeouts
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except Exception as e:
        # Catch-all for unexpected errors
        import traceback

        error_id = f"err_{int(time.time() * 1000)}"
        print(f"Error ID {error_id}: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error (ID: {error_id})")


@router.post("/qa", response_model=QAResponse)
async def document_qa(
    request: QARequest,
) -> QAResponse:
    """Perform document-level quality assurance.

    Checks for:
    - Contradictions between fields
    - Missing required attachments
    - Date inconsistencies
    - Other quality issues

    Args:
        request: QA request with case bundle

    Returns:
        QA response with detected issues

    Raises:
        HTTPException: If QA check fails
    """
    try:
        # TODO: Implement QA logic
        # 1. Check for contradictions using LLM
        # 2. Validate attachment requirements
        # 3. Check date consistency
        # 4. Flag anomalies

        return QAResponse(case_id=request.case_bundle.case_id, issues=[], clean=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QA check failed: {str(e)}")
