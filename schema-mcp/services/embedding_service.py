"""Embedding service for semantic search using sentence-transformers.

This service provides:
1. Lazy-loaded sentence transformer model
2. Document embedding with JSON file caching
3. Cosine similarity calculation

Note: This service requires the 'sentence-transformers' optional dependency.
Install with: pip install schema-mcp[semantic]
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import numpy as np

# Lazy import to avoid loading model at module import time
SentenceTransformer = None


def _get_sentence_transformer():
    """Lazy import of SentenceTransformer."""
    global SentenceTransformer
    if SentenceTransformer is None:
        from sentence_transformers import SentenceTransformer as ST

        SentenceTransformer = ST
    return SentenceTransformer


class EmbeddingService:
    """Service for generating and caching document embeddings.

    Uses all-MiniLM-L6-v2 model (384 dimensions, ~80MB).
    Caches embeddings in .embeddings_cache.json to avoid re-computation.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    CACHE_FILE = ".embeddings_cache.json"
    CACHE_VERSION = "1.0"

    def __init__(self, schemas_dir: str):
        """Initialize the embedding service.

        Args:
            schemas_dir: Path to the schemas directory
        """
        self.schemas_dir = schemas_dir
        self._model = None
        self._cache_path = Path(schemas_dir) / self.CACHE_FILE

    def get_model(self):
        """Get the sentence transformer model (lazy loaded).

        Returns:
            SentenceTransformer model instance
        """
        if self._model is None:
            ST = _get_sentence_transformer()
            self._model = ST(self.MODEL_NAME)
        return self._model

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string.

        Args:
            text: Text to embed

        Returns:
            Numpy array of shape (384,) containing the embedding
        """
        model = self.get_model()
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding

    def _compute_content_hash(self, content: str) -> str:
        """Compute MD5 hash of content for cache invalidation.

        Args:
            content: Text content to hash

        Returns:
            Hex digest of MD5 hash
        """
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _load_cache(self) -> Optional[dict[str, Any]]:
        """Load embeddings cache from disk.

        Returns:
            Cache dictionary or None if cache doesn't exist
        """
        if not self._cache_path.exists():
            return None

        try:
            with open(self._cache_path, encoding="utf-8") as f:
                cache = json.load(f)

            # Check cache version
            if cache.get("version") != self.CACHE_VERSION:
                return None

            return cache
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, embeddings: dict[str, Any]) -> None:
        """Save embeddings cache to disk.

        Args:
            embeddings: Dictionary mapping schema names to embedding data
        """
        cache = {
            "version": self.CACHE_VERSION,
            "model": self.MODEL_NAME,
            "embeddings": embeddings,
        }
        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)

    def embed_documents(self, force_rebuild: bool = False) -> dict[str, Any]:
        """Embed all schema documents and cache results.

        Args:
            force_rebuild: If True, ignore cache and rebuild all embeddings

        Returns:
            Dictionary mapping schema names to embedding data:
            {
                "SCHEMA_NAME.md": {
                    "embedding": [...],  # List of floats
                    "content_hash": "abc123..."
                }
            }
        """
        schemas_path = Path(self.schemas_dir)
        result = {}

        # Load existing cache
        cache = None if force_rebuild else self._load_cache()
        cached_embeddings = cache.get("embeddings", {}) if cache else {}

        # Process each schema file
        for schema_file in schemas_path.glob("*.md"):
            if schema_file.name == "SCHEMA_INDEX.md":
                continue

            try:
                content = schema_file.read_text(encoding="utf-8")
                content_hash = self._compute_content_hash(content)

                # Check if cached embedding is still valid
                cached = cached_embeddings.get(schema_file.name)
                if cached and cached.get("content_hash") == content_hash:
                    # Reuse cached embedding
                    result[schema_file.name] = cached
                else:
                    # Compute new embedding
                    embedding = self.embed_text(content)
                    result[schema_file.name] = {
                        "embedding": embedding.tolist(),
                        "content_hash": content_hash,
                    }
            except (OSError, UnicodeDecodeError):
                # Skip files that can't be read
                continue

        # Save updated cache
        self._save_cache(result)
        return result

    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (between -1 and 1)
        """
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def search_semantic(
        self,
        query: str,
        top_k: int = 20,
    ) -> list[tuple[str, float]]:
        """Search schemas using semantic similarity.

        Args:
            query: Search query
            top_k: Number of top results to return

        Returns:
            List of (schema_name, similarity_score) tuples, sorted by score descending
        """
        # Embed the query
        query_embedding = self.embed_text(query)

        # Get all document embeddings
        doc_embeddings = self.embed_documents(force_rebuild=False)

        # Compute similarities
        similarities = []
        for schema_name, data in doc_embeddings.items():
            doc_embedding = np.array(data["embedding"])
            similarity = self.cosine_similarity(query_embedding, doc_embedding)
            similarities.append((schema_name, similarity))

        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]
