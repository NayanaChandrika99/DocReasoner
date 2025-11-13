import pytest

from retrieval.service import RetrievalConfig, RetrievalResult, RetrievalService
from retrieval.fts5_fallback import FTS5Fallback


class FakePageIndexClient:
    def __init__(self, llm_payload, hybrid_payload=None, node_payloads=None):
        self.llm_payload = llm_payload
        self.hybrid_payload = hybrid_payload or llm_payload
        self.node_payloads = node_payloads or {}
        self.calls = {"llm": 0, "hybrid": 0, "node": 0}
        self.available = True

    def llm_tree_search(self, doc_id, query, thinking=True):
        self.calls["llm"] += 1
        return self.llm_payload

    def hybrid_tree_search(self, doc_id, query, top_k=3):
        self.calls["hybrid"] += 1
        return self.hybrid_payload

    def get_node_content(self, doc_id, node_id):
        self.calls["node"] += 1
        return self.node_payloads[node_id]


LLM_PAYLOAD = {
    "nodes": [
        {
            "node_id": "n1",
            "title": "Section A",
            "page_index": 1,
            "prefix_summary": "summary a",
            "relevant_contents": [{"page_index": 1, "relevant_content": "short text"}],
            "score": 0.9,
        },
        {
            "node_id": "n2",
            "title": "Section B",
            "page_index": 2,
            "prefix_summary": "summary b",
            "relevant_contents": [{"page_index": 2, "relevant_content": "another short text"}],
            "score": 0.7,
        },
    ],
    "search_trajectory": ["n1", "n2"],
}

HYBRID_PAYLOAD = {
    "nodes": [
        {
            "node_id": "n3",
            "title": "Hybrid Section",
            "page_index": 3,
            "prefix_summary": "summary hybrid",
            "relevant_contents": [{"page_index": 3, "relevant_content": "hybrid span"}],
            "score": 0.95,
        }
    ],
    "search_trajectory": ["n3"],
}


def test_retrieval_llm_mode():
    client = FakePageIndexClient(LLM_PAYLOAD)
    config = RetrievalConfig(hybrid_threshold=10.0, node_span_token_threshold=1000)
    service = RetrievalService(client=client, config=config)

    result = service.search("query", "doc123")

    assert result.retrieval_method == "pageindex-llm"
    assert client.calls["llm"] == 1
    assert client.calls["hybrid"] == 0
    assert result.spans and result.spans[0].text == "short text"


def test_retrieval_triggers_hybrid(monkeypatch):
    client = FakePageIndexClient(LLM_PAYLOAD, hybrid_payload=HYBRID_PAYLOAD)
    config = RetrievalConfig(hybrid_threshold=0.01, node_span_token_threshold=1000)
    service = RetrievalService(client=client, config=config)

    # Force ambiguity to exceed threshold regardless of payload contents
    monkeypatch.setattr(service, "_calculate_ambiguity", lambda payload: 0.5)

    result = service.search("query", "doc123")

    assert result.retrieval_method == "pageindex-hybrid"
    assert client.calls["hybrid"] == 1
    assert result.spans and result.spans[0].text == "hybrid span"


def test_retrieval_triggers_bm25():
    long_payload = {
        "nodes": [
            {
                "node_id": "n1",
                "title": "Long Section",
                "page_index": 1,
                "prefix_summary": "summary",
                "relevant_contents": [
                    {
                        "page_index": 1,
                        "relevant_content": " ".join(["match"] * 100),
                    }
                ],
                "score": 0.8,
            }
        ],
        "search_trajectory": ["n1"],
    }
    node_payloads = {"n1": {"text": "match token\n\nirrelevant paragraph"}}
    client = FakePageIndexClient(long_payload, node_payloads=node_payloads)
    config = RetrievalConfig(hybrid_threshold=10.0, node_span_token_threshold=10)
    service = RetrievalService(client=client, config=config, fts5_fallback=FTS5Fallback())

    result = service.search("match", "doc123")

    assert result.retrieval_method == "bm25-fallback"
    assert client.calls["node"] >= 1
    assert result.spans and "match token" in result.spans[0].text
