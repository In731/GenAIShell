import json
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from config.settings import settings
from utils.logging import logger

class LightweightVectorStore:
    """A lightweight, high-performance semantic vector database written in pure Python/NumPy.
    
    Persists documents, embeddings, and metadata into a local JSON store and performs
    vector search using optimized NumPy cosine similarity calculations.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or settings.vector_db_path
        self.documents: List[Dict[str, Any]] = []
        self.embeddings: List[List[float]] = []
        self.load()

    def load(self) -> None:
        """Loads vector database records from local storage path if it exists."""
        if not self.storage_path.exists():
            logger.debug(f"Vector store file not found at {self.storage_path}. Initializing empty store.")
            self.documents = []
            self.embeddings = []
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.documents = data.get("documents", [])
                self.embeddings = data.get("embeddings", [])
                logger.debug(f"Loaded {len(self.documents)} records from vector store.")
        except Exception as e:
            logger.error(f"Error loading vector store from {self.storage_path}: {e}")
            self.documents = []
            self.embeddings = []

    def save(self) -> None:
        """Saves current memory index of documents and embeddings to disk."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({
                    "documents": self.documents,
                    "embeddings": self.embeddings
                }, f, ensure_ascii=False, indent=2)
            logger.debug(f"Saved {len(self.documents)} records to vector store.")
        except Exception as e:
            logger.error(f"Error saving vector store: {e}")

    def add_document(self, text: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        """Adds a new document along with its corresponding embedding vector and metadata to the index."""
        if not embedding or not isinstance(embedding, list):
            raise ValueError("Embedding must be a list of floats.")
        
        self.documents.append({
            "text": text,
            "metadata": metadata or {}
        })
        self.embeddings.append(embedding)
        self.save()

    def query(self, query_embedding: List[float], top_k: int = 3) -> List[Tuple[Dict[str, Any], float]]:
        """Executes a semantic similarity search using vectorized cosine similarity computation.
        
        Returns:
            List of Tuples containing (document_dict, similarity_score) sorted in descending order.
        """
        if not self.embeddings or not query_embedding:
            return []

        # Convert lists to NumPy arrays for high-performance matrix math
        vectors = np.array(self.embeddings, dtype=np.float32)
        q_vec = np.array(query_embedding, dtype=np.float32)

        # Compute dot products of query against database vectors
        dot_products = np.dot(vectors, q_vec)

        # Compute magnitude norms
        norms_db = np.linalg.norm(vectors, axis=1)
        norm_q = np.linalg.norm(q_vec)

        # Avoid zero division
        norms_db = np.where(norms_db == 0, 1e-10, norms_db)
        norm_q = 1e-10 if norm_q == 0 else norm_q

        # Calculate Cosine Similarities: dot(A, B) / (||A|| * ||B||)
        similarities = dot_products / (norms_db * norm_q)

        # Retrieve top k indexes sorting descending
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            results.append((self.documents[idx], score))

        return results

    def clear(self) -> None:
        """Purges the database index and truncates storage file."""
        self.documents = []
        self.embeddings = []
        if self.storage_path.exists():
            try:
                os.remove(self.storage_path)
            except Exception as e:
                logger.error(f"Failed to remove vector store file: {e}")
        logger.info("Vector database cleared successfully.")
