from typing import List, Dict, Any, Optional
from config.settings import settings
from utils.logging import logger
from storage.memory import MemoryManager
from storage.vector_store import LightweightVectorStore

class GeminiOrchestrator:
    """Manages semantic embedding creation using local sentence-transformers."""

    def __init__(self):
        self.memory = MemoryManager()
        self.vector_store = LightweightVectorStore()
        self._embedding_model = None

    def _get_model(self):
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading local sentence-transformers model (this may take a moment on first run)...")
                self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            except ImportError:
                logger.error("sentence-transformers not installed. Embeddings will fail.")
                return None
        return self._embedding_model

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generates a semantic embedding vector using local model."""
        model = self._get_model()
        if not model:
            return self._fallback_embedding(text)
            
        try:
            embedding = model.encode(text)
            # all-MiniLM-L6-v2 returns 384 dimensions. Duplicate it to 768 to match original schema!
            emb_list = embedding.tolist()
            return emb_list + emb_list
        except Exception as e:
            logger.error(f"Error generating embedding from local model: {e}", exc_info=True)
            return self._fallback_embedding(text)

    def _fallback_embedding(self, text: str) -> List[float]:
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        fallback = [float(b) / 255.0 for b in h] * 24
        return fallback[:768]

    def add_to_rag_store(self, text: str, category: str = "General") -> None:
        """Helper to generate an embedding for text and save it to the semantic Vector Store."""
        embedding = self.get_embedding(text)
        if embedding:
            self.vector_store.add_document(
                text=text,
                embedding=embedding,
                metadata={"category": category}
            )
            logger.info(f"Successfully added document to local RAG under category '{category}'")

    def search_rag_store(self, query: str, top_k: int = 3) -> str:
        """Helper to query local semantic documents using Gemini embeddings."""
        query_embedding = self.get_embedding(query)
        if not query_embedding:
            return "Failed to fetch query embedding."
            
        matches = self.vector_store.query(query_embedding, top_k=top_k)
        if not matches:
            return "No matching documentation matches found."

        results = []
        for doc, score in matches:
            cat = doc.get("metadata", {}).get("category", "General")
            results.append(f"- [Score: {score:.2f}] [{cat}] {doc.get('text')}")
            
        return "\n".join(results)
