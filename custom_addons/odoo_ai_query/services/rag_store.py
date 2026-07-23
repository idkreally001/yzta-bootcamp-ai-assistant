import json
import logging
import math
import os
import threading

import requests

_logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent"
)
EMBEDDING_DIM = 768
FAQ_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "faq.json")

_lock = threading.Lock()
_index = None  # list of {id, title, content, embedding} once built


def _embed(text, api_key):
    resp = requests.post(
        EMBEDDING_URL,
        params={"key": api_key},
        json={
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBEDDING_DIM,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


def _cosine_sim(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _build_index(api_key):
    with open(FAQ_PATH, encoding="utf-8") as f:
        docs = json.load(f)

    indexed = []
    for doc in docs:
        text = f"{doc['title']}\n{doc['content']}"
        try:
            embedding = _embed(text, api_key)
        except Exception:
            _logger.exception("Failed to embed FAQ doc %s, skipping", doc["id"])
            continue
        indexed.append({**doc, "embedding": embedding})
    _logger.info("RAG index built: %d/%d FAQ docs embedded", len(indexed), len(docs))
    return indexed


def get_index(api_key):
    """Lazily build and cache the FAQ embedding index (module-level, process-lifetime)."""
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = _build_index(api_key)
    return _index


def search_docs(query, api_key, top_k=3, min_score=0.5):
    """Return the top_k most relevant FAQ docs for `query`, above min_score similarity."""
    index = get_index(api_key)
    if not index:
        return []

    query_embedding = _embed(query, api_key)
    scored = [
        (doc, _cosine_sim(query_embedding, doc["embedding"]))
        for doc in index
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [
        {"id": doc["id"], "title": doc["title"], "content": doc["content"], "score": score}
        for doc, score in scored[:top_k]
        if score >= min_score
    ]
