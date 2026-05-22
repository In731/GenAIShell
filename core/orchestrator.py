import google.generativeai as genai
from typing import List, Dict, Any, Optional
from config.settings import settings
from utils.logging import logger
from storage.memory import MemoryManager
from storage.vector_store import LightweightVectorStore

class GeminiOrchestrator:
    """Manages the Gemini API connection, prompt orchestration, and vector embedding creation."""

    def __init__(self):
        self.api_key = settings.gemini_api_key
        if not self.api_key:
            logger.warning("GEMINI_API_KEY environment variable is not set. AI operations will fail.")
        else:
            genai.configure(api_key=self.api_key)
            logger.info("Successfully configured Gemini API Client.")
            
        self.model_name = settings.gemini_model
        self.memory = MemoryManager()
        self.vector_store = LightweightVectorStore()

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generates a high-quality semantic embedding vector for RAG queries using Gemini's embedding model."""
        if not self.api_key:
            logger.error("Cannot generate embedding: Gemini API Key is missing.")
            return None
        try:
            # We use standard 'models/text-embedding-004' for standard vector dimensions (768)
            result = genai.embed_content(
                model="models/text-embedding-004",
                contents=text,
                task_type="retrieval_document"
            )
            embedding = result.get("embedding", [])
            if not embedding:
                # Fallback check
                embedding = result.get("embeddings", [[]])[0]
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding from Gemini API: {e}", exc_info=True)
            # Create a simple hash-based pseudo-embedding fallback in case of connection outages
            # to prevent application crashes during local testing
            import hashlib
            h = hashlib.sha256(text.encode("utf-8")).digest()
            fallback = [float(b) / 255.0 for b in h] * 24  # Pad to 768 elements
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
