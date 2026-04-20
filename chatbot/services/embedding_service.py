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
        Used by Django Signals for manual/Admin saves.
        Async-Safe.
        """
        # We now source text solely from the new embedding_text field
        combined_text = product.embedding_text
        
        if not combined_text:
            brand_name = product.brand.name if product.brand else "Unknown"
            cat_name = product.category.name if product.category else "General"
            combined_text = f"{product.name} {brand_name} {cat_name} {product.description}"
            logger.warning(f"Embedding text missing for {product.name}. Falling back to raw text.")

        vector = cls.generate_embedding(combined_text)
        
        def _save():
            product.embedding = vector
            product.save(update_fields=['embedding'])
            
        await sync_to_async(_save)()
        logger.info(f"Updated ENRICHED embedding for Product: {product.name}")

    @classmethod
    def batch_update_products_sync(cls, products: List):
        """
        Synchronous wrapper for batch processing.
        To be used by legacy synchronous views and services (like UploadService).
        """
        # We use async_to_sync to reuse the high-speed batch logic
        return async_to_sync(cls.batch_update_products_async)(products)

    @classmethod
    async def batch_update_products_async(cls, products: List):
        """
        High-Speed Batch Processing for Product Catalog Ingestion.
        Processes products in groups of 100 to stay within token limits.
        Async-Safe.
        """
        if not products:
            return

        embeddings_client = get_embeddings()
        batch_size = 100
        
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            
            # 1. Prepare Golden Strings
            texts_to_embed = []
            for p in batch:
                # We now source text solely from the new embedding_text field
                combined_text = p.embedding_text
                
                if not combined_text:
                    brand_name = p.brand.name if p.brand else "Unknown"
                    cat_name = p.category.name if p.category else "General"
                    combined_text = f"{p.name} {brand_name} {cat_name} {p.description}"
                
                texts_to_embed.append(combined_text)
            
            # 2. Batch Embed (Directly calls AI once per 100 items)
            try:
                # embed_documents is typically a blocking network call in LangChain
                # but we wrap it in sync_to_async to be clean
                vectors = await sync_to_async(embeddings_client.embed_documents)(texts_to_embed)
                
                # 3. Save vectors back to models
                def _batch_save():
                    for idx, p in enumerate(batch):
                        p.embedding = vectors[idx]
                        p.save(update_fields=['embedding'])
                
                await sync_to_async(_batch_save)()
                logger.info(f"Batch Processing Success: {len(batch)} products embedded.")
            except Exception as e:
                logger.error(f"Batch embedding failed for a chunk: {str(e)}")
