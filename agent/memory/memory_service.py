"""
Long-Term Semantic Memory Service for Jarvis:
Powered by Qdrant (Local on-disk storage or client) for user preferences,
frequently accessed projects, and contextual fact recall.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, List, Optional
import uuid
import numpy as np

log = logging.getLogger("memory_service")


@dataclass
class MemoryItem:
    """Semantic long-term memory entry."""
    id: str
    text: str
    category: str = "general"  # "preference" | "project" | "fact" | "history"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "category": self.category,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "score": round(self.score, 4),
        }


class MemoryService:
    """Abstract Base Class for Memory Services."""

    def store(self, text: str, category: str = "general", metadata: dict[str, Any] | None = None) -> str:
        raise NotImplementedError

    def search(self, query: str, limit: int = 5, category: str | None = None) -> list[MemoryItem]:
        raise NotImplementedError

    def list_all(self, category: str | None = None) -> list[MemoryItem]:
        raise NotImplementedError


class QdrantMemoryProvider(MemoryService):
    """
    Qdrant-backed Vector Memory Service.
    Uses local on-disk storage directory (./data/qdrant) or connected Qdrant server.
    """

    _instance: QdrantMemoryProvider | None = None

    @classmethod
    def get_instance(cls) -> QdrantMemoryProvider:
        if cls._instance is None:
            cls._instance = QdrantMemoryProvider()
        return cls._instance

    def __init__(
        self,
        collection_name: str = "jarvis_memory",
        storage_path: str | Path | None = None,
        vector_size: int = 128,
    ):
        self.collection_name = collection_name
        self.vector_size = vector_size

        if storage_path is None:
            storage_path = os.environ.get("QDRANT_STORAGE_PATH", "./data/qdrant")
        self.storage_path = Path(storage_path).resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._client: Any = None
        self._fallback_store: list[MemoryItem] = []
        self._init_qdrant()

    def _init_qdrant(self) -> None:
        """Initialize Qdrant client."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            server_url = os.environ.get("QDRANT_URL", "").strip()
            if server_url:
                log.info("[MEMORY] Connecting to Qdrant server at %s...", server_url)
                self._client = QdrantClient(url=server_url)
            else:
                log.info("[MEMORY] Initializing local on-disk Qdrant storage at %s...", self.storage_path)
                self._client = QdrantClient(path=str(self.storage_path))

            # Ensure collection exists
            if not self._client.collection_exists(self.collection_name):
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                )
                log.info("[MEMORY] Created Qdrant collection '%s'.", self.collection_name)
        except Exception as e:
            log.warning("[MEMORY] Could not initialize Qdrant client (%s). Using fallback memory.", e)
            self._client = None

    def close(self) -> None:
        """Close client connection to release locks."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _generate_vector(self, text: str) -> list[float]:
        """
        Generate lightweight deterministic semantic vector (dim=128)
        based on token hashing and character n-grams.
        """
        vec = np.zeros(self.vector_size, dtype=np.float32)
        words = text.lower().split()
        for w in words:
            # Word level hash
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % self.vector_size
            vec[idx] += 1.0
            # Character bigram level hash
            for i in range(len(w) - 1):
                bg = w[i:i+2]
                bg_h = int(hashlib.sha256(bg.encode("utf-8")).hexdigest()[:8], 16)
                vec[bg_h % self.vector_size] += 0.5

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def store(self, text: str, category: str = "general", metadata: dict[str, Any] | None = None) -> str:
        """Store a memory item."""
        clean_text = text.strip()
        if not clean_text:
            return ""

        raw_id = f"{clean_text}|{category}|{time.time()}"
        point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))
        meta = metadata or {}
        payload = {
            "id": point_uuid,
            "text": clean_text,
            "category": category,
            "timestamp": datetime.now().isoformat(),
            "metadata": meta,
        }

        if self._client is not None:
            try:
                from qdrant_client.models import PointStruct
                vector = self._generate_vector(clean_text)
                self._client.upsert(
                    collection_name=self.collection_name,
                    points=[PointStruct(id=point_uuid, vector=vector, payload=payload)],
                )
                log.info("[MEMORY] Stored memory '%s' (category=%s, id=%s)", clean_text[:40], category, point_uuid)
                return point_uuid
            except Exception as e:
                log.warning("[MEMORY] Failed to store in Qdrant (%s), saving to fallback.", e)

        # Fallback local in-memory storage
        self._fallback_store.append(MemoryItem(id=point_uuid, text=clean_text, category=category, metadata=meta))
        return point_uuid

    def search(self, query: str, limit: int = 5, category: str | None = None) -> list[MemoryItem]:
        """Search relevant memories using vector similarity."""
        clean_query = query.strip()
        if not clean_query:
            return []

        if self._client is not None:
            try:
                query_vector = self._generate_vector(clean_query)
                # Use query_points in newer qdrant_client
                res = self._client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=limit,
                )
                points = getattr(res, "points", res)
                items: list[MemoryItem] = []
                for pt in points:
                    p = pt.payload or {}
                    if category and p.get("category") != category:
                        continue
                    items.append(MemoryItem(
                        id=str(p.get("id", pt.id)),
                        text=p.get("text", ""),
                        category=p.get("category", "general"),
                        timestamp=p.get("timestamp", ""),
                        metadata=p.get("metadata", {}),
                        score=float(pt.score) if hasattr(pt, "score") else 1.0,
                    ))
                log.info("[MEMORY] Found %d matching memories for '%s'", len(items), clean_query)
                return items
            except Exception as e:
                log.warning("[MEMORY] Qdrant search error: %s", e)

        # Fallback search
        q_words = set(clean_query.lower().split())
        scored: list[tuple[float, MemoryItem]] = []
        for it in self._fallback_store:
            if category and it.category != category:
                continue
            it_words = set(it.text.lower().split())
            overlap = len(q_words.intersection(it_words))
            if overlap > 0:
                score = overlap / max(len(q_words), 1)
                scored.append((score, it))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def list_all(self, category: str | None = None) -> list[MemoryItem]:
        """Retrieve all stored memories."""
        if self._client is not None:
            try:
                scroll_res = self._client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    with_payload=True,
                )
                points = scroll_res[0]
                items: list[MemoryItem] = []
                for pt in points:
                    p = pt.payload or {}
                    if category and p.get("category") != category:
                        continue
                    items.append(MemoryItem(
                        id=str(p.get("id", pt.id)),
                        text=p.get("text", ""),
                        category=p.get("category", "general"),
                        timestamp=p.get("timestamp", ""),
                        metadata=p.get("metadata", {}),
                    ))
                return items
            except Exception as e:
                log.warning("[MEMORY] Qdrant list error: %s", e)

        if category:
            return [it for it in self._fallback_store if it.category == category]
        return list(self._fallback_store)


def get_memory_service() -> QdrantMemoryProvider:
    return QdrantMemoryProvider.get_instance()
