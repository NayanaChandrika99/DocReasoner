"""Configuration management for the reasoning service."""

from typing import Literal, AsyncGenerator, Dict
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Application
    app_name: str = "reasoning-service"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # Database
    database_url: str = Field(
        default="postgresql://localhost:5432/reasoning_service",
        description="PostgreSQL connection string",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Redis Cache
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl: int = 3600  # 1 hour

    # PageIndex API
    pageindex_api_key: str = Field(default="", description="PageIndex API key")
    pageindex_base_url: str = "https://api.pageindex.ai"
    pageindex_timeout: int = 30

    # TreeStore gRPC
    treestore_host: str = Field(
        default="localhost", description="TreeStore gRPC server host"
    )
    treestore_port: int = Field(
        default=50051, description="TreeStore gRPC server port"
    )
    treestore_timeout: int = Field(
        default=30, description="TreeStore gRPC timeout in seconds"
    )
    treestore_max_retries: int = Field(
        default=3, description="Max retries for TreeStore gRPC calls"
    )
    treestore_retry_delay: float = Field(
        default=1.0, description="Delay between retries in seconds"
    )
    treestore_enable_compression: bool = Field(
        default=True, description="Enable gRPC compression"
    )
    treestore_use_stub: bool = Field(
        default=False, description="Use in-memory stub instead of gRPC client (for development)"
    )

    # Retrieval Settings
    llm_tree_search_enabled: bool = True
    hybrid_tree_search_threshold: float = 0.15  # Switch to hybrid if ambiguity > 15%
    node_span_token_threshold: int = 2000  # Trigger BM25+reranker if node spans exceed this
    bm25_shortlist_size: int = 20
    reranker_top_k: int = 5
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"

    # ReAct Controller
    controller_model: str = Field(
        default="mistral-7b-instruct", description="LLM for ReAct controller (3B-7B class)"
    )
    controller_temperature: float = 0.1
    controller_max_iterations: int = 10
    react_use_llm_controller: bool = False
    react_shadow_mode: bool = False
    react_fallback_enabled: bool = True
    react_ab_test_ratio: float = 0.0
    prompt_ab_test_ratio: float = 0.0
    controller_tool_timeout_seconds: float = 12.0
    controller_tool_timeout_overrides: Dict[str, float] = Field(default_factory=dict)
    controller_tool_retry_limit: int = 1
    retrieval_backend: Literal["pageindex", "treestore"] = "pageindex"
    tool_rate_limit_per_minute: Dict[str, int] = Field(
        default_factory=lambda: {
            "pubmed_search": 30,
            "pi_search": 120,
        }
    )

    # Evidence Retrieval
    pubmed_enabled: bool = False
    pubmed_api_key: str = ""
    pubmed_max_results: int = 3
    pubmed_timeout_seconds: float = 15.0
    pubmed_cache_ttl_seconds: int = 86400

    # LLM Provider Settings
    llm_provider: str = Field(
        default="openai", description="LLM provider: openai, anthropic, or vllm"
    )
    llm_model: str = Field(
        default="gpt-4o-mini", description="Model name for LLM provider"
    )
    llm_api_key: str = Field(
        default="", description="LLM API key (from environment)"
    )
    llm_base_url: str = Field(
        default="", description="Base URL for vLLM or custom OpenAI-compatible endpoints"
    )

    # Safety & Calibration
    temperature_scaling_enabled: bool = True
    self_consistency_enabled: bool = True
    self_consistency_k: int = 3  # Number of samples
    self_consistency_threshold: float = 0.7  # Trigger if confidence < 0.7
    conformal_alpha: float = 0.1  # Significance level for conformal prediction
    high_impact_confidence_threshold: float = 0.85

    # Performance
    max_concurrent_requests: int = 100
    request_timeout: int = 30  # seconds
    target_p50_latency: float = 5.0  # seconds
    target_p95_latency: float = 15.0  # seconds

    # Observability
    metrics_enabled: bool = True
    tracing_enabled: bool = True
    tracing_sample_rate: float = 0.1

    # GEPA / Prompt Optimization
    gepa_enabled: bool = False
    gepa_auto_mode: Literal["light", "medium", "heavy"] = "medium"
    gepa_max_iterations: int = 150
    gepa_target_score: float = 0.8
    gepa_reflection_model: str = "gpt-4o"
    gepa_task_model: str = "gpt-4o-mini"
    gepa_dataset_path: str = "tests/data/cases"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """Ensure LLM provider is valid."""
        valid_providers = {"openai", "anthropic", "vllm"}
        v_lower = v.lower()
        if v_lower not in valid_providers:
            raise ValueError(f"llm_provider must be one of {valid_providers}")
        return v_lower

    @field_validator("react_ab_test_ratio")
    @classmethod
    def validate_ab_ratio(cls, v: float) -> float:
        """Ensure A/B ratio is between 0 and 1."""
        if v < 0.0 or v > 1.0:
            raise ValueError("react_ab_test_ratio must be between 0.0 and 1.0")
        return v


# Global settings instance
settings = Settings()

# Database engine and session factory
_engine = None
_async_session_factory = None


def get_async_engine():
    """Get or create async database engine."""
    global _engine
    if _engine is None:
        # Convert postgresql:// to postgresql+asyncpg://
        db_url = settings.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        _engine = create_async_engine(
            db_url,
            echo=settings.environment == "development",
            pool_pre_ping=True,
        )
    return _engine


def get_async_session_factory():
    """Get or create async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting database sessions in FastAPI routes.

    Yields:
        AsyncSession for database operations
    """
    async_session = get_async_session_factory()
    async with async_session() as session:
        yield session
