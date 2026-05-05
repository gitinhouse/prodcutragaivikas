import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from threading import Thread
from chatbot.models import WheelProduct

logger = logging.getLogger(__name__)

@receiver(post_save, sender=WheelProduct)
def trigger_product_embedding(sender, instance, created, **kwargs):
    """
    Automatically triggers the EmbeddingService when a product is saved.
    Uses a thread to avoid blocking the main database transaction.
    """
    from chatbot.services.embedding_service import EmbeddingService
    from asgiref.sync import async_to_sync
    
    # Check if we need to update
    if created or instance.embedding is None:
        logger.info(f"Triggering background embedding for: {instance.product_name}")
        # Run using a thread-safe async bridge
        Thread(target=async_to_sync(EmbeddingService.update_product_embedding), args=(instance,)).start()
