import logging
from typing import List, Tuple
from app.config import get_settings

logger = logging.getLogger(__name__)

class SemanticMemoryEngine:
    _model = None

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            settings = get_settings()
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading semantic model {settings.memory_semantic_model}...")
                # Load model on CPU
                cls._model = SentenceTransformer(settings.memory_semantic_model, device="cpu")
            except Exception as e:
                logger.error(f"Failed to load sentence-transformers: {e}")
                raise e
        return cls._model

    @classmethod
    def get_embeddings(cls, texts: List[str]) -> List[List[float]]:
        """Returns embeddings for a list of texts."""
        if not texts:
            return []
        
        try:
            model = cls._get_model()
            # Normalize embeddings for cosine similarity via dot product
            embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return []

    @classmethod
    def compute_similarity(cls, query: str, candidates: List[str]) -> List[float]:
        """
        Computes cosine similarity between query and candidates.
        Returns a list of float scores between -1.0 and 1.0.
        """
        if not query or not candidates:
            return []

        try:
            model = cls._get_model()
            query_emb = model.encode([query], normalize_embeddings=True, show_progress_bar=False)
            docs_emb = model.encode(candidates, normalize_embeddings=True, show_progress_bar=False)
            
            # Since normalized, dot product is cosine similarity
            import numpy as np
            scores = np.dot(docs_emb, query_emb.T).flatten()
            return scores.tolist()
        except Exception as e:
            logger.error(f"Similarity computation failed: {e}")
            return []

semantic_engine = SemanticMemoryEngine()
