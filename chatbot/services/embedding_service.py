import logging
import asyncio
from typing import List
from django.conf import settings
from asgiref.sync import sync_to_async, async_to_sync
from config.llm_config import get_embeddings

logger = logging.getLogger(__name__)

class ServiceError(Exception):
    pass

class EmbeddingProviderError(ServiceError):
    pass

class EmbeddingService:
    """
    Handles generation of embeddings via LangChain LLM providers.
    Highly optimized for performance: Singleton Clients + Batch Processing.
    Hardened for Async/Sync Dual Compatibility.
    """

    @staticmethod
    def generate_embedding(text: str) -> List[float]:
        """
        Generates a vector embedding for the given text using a shared singleton client.
        """
        try:
            embeddings = get_embeddings()
            return embeddings.embed_query(text)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            raise EmbeddingProviderError(f"Embedding generation failed: {str(e)}")

    @classmethod
    async def update_product_embedding(cls, product):
        """
        Sequential update for a single product. 
        Async-Safe.
        """
        combined_text = product.embedding_text
        
        if not combined_text:
            # Generic fallback for WheelProduct
            brand = getattr(product, 'brand_desc', 'Unknown')
            name = getattr(product, 'product_name', 'Unknown')
            desc = getattr(product, 'product_desc', '')
            combined_text = f"{brand} {name} {desc}"
            logger.warning(f"Embedding text missing for {name}. Falling back to raw text.")

        vector = cls.generate_embedding(combined_text)
        
        def _save():
            product.embedding = vector
            product.save(update_fields=['embedding'])
            
        await sync_to_async(_save)()
        logger.info(f"Updated embedding for: {getattr(product, 'product_name', 'Item')}")

    @classmethod
    def batch_update_products_sync(cls, products: List):
        return async_to_sync(cls.batch_update_products_async)(products)

    @classmethod
    async def batch_update_products_async(cls, products: List):
        if not products:
            return

        embeddings_client = get_embeddings()
        batch_size = 100
        
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            texts_to_embed = []
            for p in batch:
                combined_text = p.embedding_text
                if not combined_text:
                    brand = getattr(p, 'brand_desc', 'Unknown')
                    name = getattr(p, 'product_name', 'Unknown')
                    desc = getattr(p, 'product_desc', '')
                    combined_text = f"{brand} {name} {desc}"
                texts_to_embed.append(combined_text)
            
            try:
                vectors = await sync_to_async(embeddings_client.embed_documents)(texts_to_embed)
                
                def _batch_save():
                    for idx, p in enumerate(batch):
                        p.embedding = vectors[idx]
                        p.save(update_fields=['embedding'])
                
                await sync_to_async(_batch_save)()
                logger.info(f"Batch Processing Success: {len(batch)} items embedded.")
            except Exception as e:
                logger.error(f"Batch embedding failed: {str(e)}")
