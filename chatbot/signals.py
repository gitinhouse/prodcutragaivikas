import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from threading import Thread
from chatbot.models import Product

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Product)
def trigger_product_embedding(sender, instance, created, **kwargs):
    """
    Automatically triggers the EmbeddingService when a product is saved.
    Uses a thread to avoid blocking the main database transaction.
    """
    from chatbot.services.embedding_service import EmbeddingService
    
    # Check if we need to update
    if created or not instance.embedding:
        logger.info(f"Triggering background embedding for: {instance.name}")
        # Run in a separate thread for simplicity in this stage
        Thread(target=EmbeddingService.update_product_embedding, args=(instance,)).start()
