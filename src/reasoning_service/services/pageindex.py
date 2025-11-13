"""Client for PageIndex API integration."""

import httpx
from typing import Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from reasoning_service.config import settings


class PageIndexClient:
    """Client for interacting with PageIndex API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """Initialize PageIndex client.
        
        Args:
            api_key: PageIndex API key (defaults to settings)
            base_url: Base URL for PageIndex API (defaults to settings)
            timeout: Request timeout in seconds (defaults to settings)
        """
        self.api_key = api_key or settings.pageindex_api_key
        self.base_url = base_url or settings.pageindex_base_url
        self.timeout = timeout or settings.pageindex_timeout
        
        if not self.api_key:
            raise ValueError("PageIndex API key is required")
        
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout
        )
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def submit_document(self, pdf_path: str) -> str:
        """Submit a PDF document for processing using PageIndex.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Document ID for subsequent operations
        """
        with open(pdf_path, "rb") as file:
            files = {"file": file}
            response = await self.client.post("/doc/", files=files)
            response.raise_for_status()
            result = response.json()
            return result["doc_id"]
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_processing_status(self, document_id: str, result_type: str = "tree") -> dict[str, Any]:
        """Get processing status and results for a document.

        Args:
            document_id: PageIndex document identifier
            result_type: Type of result ("tree" or "ocr")

        Returns:
            Processing status and results when complete
        """
        params = {"type": result_type}
        response = await self.client.get(f"/doc/{document_id}/", params=params)
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_tree(self, document_id: str) -> dict[str, Any]:
        """Generate hierarchical tree structure from document.

        Args:
            document_id: PageIndex document identifier

        Returns:
            Tree structure with nodes, summaries, and page ranges
        """
        return await self.get_processing_status(document_id, "tree")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def submit_retrieval(self, document_id: str, query: str, thinking: bool = False) -> str:
        """Submit a retrieval query.

        Args:
            document_id: PageIndex document identifier
            query: Search query
            thinking: Whether to use thinking mode

        Returns:
            Retrieval task ID
        """
        payload = {
            "doc_id": document_id,
            "query": query,
            "thinking": thinking
        }
        response = await self.client.post("/retrieval/", json=payload)
        response.raise_for_status()
        result = response.json()
        return result["retrieval_id"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_retrieval_status(self, retrieval_id: str) -> dict[str, Any]:
        """Get retrieval status and results.

        Args:
            retrieval_id: Retrieval task ID

        Returns:
            Retrieval status and results when complete
        """
        response = await self.client.get(f"/retrieval/{retrieval_id}/")
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def llm_tree_search(
        self,
        document_id: str,
        query: str,
        top_k: int = 3
    ) -> dict[str, Any]:
        """Perform LLM-based tree search.

        Args:
            document_id: PageIndex document identifier
            query: Search query
            top_k: Number of top nodes to return

        Returns:
            Search results with node IDs, trajectory, pages, and relevant paragraphs
        """
        retrieval_id = await self.submit_retrieval(document_id, query)
        # In a real implementation, we'd poll for completion
        # For demo, assume immediate completion
        result = await self.get_retrieval_status(retrieval_id)

        # Transform to expected format
        retrieved_nodes = result.get("retrieved_nodes", [])
        node_ids = [node["node_id"] for node in retrieved_nodes]
        pages = []
        relevant_paragraphs = []
        for node in retrieved_nodes:
            for content in node.get("relevant_contents", []):
                pages.append(content["page_index"])
                relevant_paragraphs.append(content["relevant_content"])

        return {
            "node_ids": node_ids,
            "trajectory": node_ids,  # Simplified
            "pages": list(set(pages)),  # Unique pages
            "relevant_paragraphs": relevant_paragraphs,
            "method": "pageindex-llm"
        }
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def hybrid_tree_search(
        self,
        document_id: str,
        query: str,
        top_k: int = 3
    ) -> dict[str, Any]:
        """Perform hybrid tree search (LLM + value function).
        
        Args:
            document_id: PageIndex document identifier
            query: Search query
            top_k: Number of top nodes to return
            
        Returns:
            Search results with node IDs, trajectory, pages, and relevant paragraphs
        """
        # TODO: Implement based on PageIndex API docs (Hybrid search)
        # https://docs.pageindex.ai/tree-search/basic
        raise NotImplementedError("Hybrid tree search endpoint to be implemented")
    
    async def get_node_content(self, document_id: str, node_id: str) -> dict[str, Any]:
        """Retrieve full content for a specific node.
        
        Args:
            document_id: PageIndex document identifier
            node_id: Node identifier from tree
            
        Returns:
            Node content with text and metadata
        """
        # TODO: Implement based on PageIndex API docs
        raise NotImplementedError("Node content retrieval to be implemented")
