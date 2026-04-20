import uuid
from django.db import models
from django.contrib.postgres.indexes import GinIndex
from pgvector.django import VectorField, HnswIndex

class Category(models.Model):
    """
    Normalized Product Categories.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

class Brand(models.Model):
    """
    Normalized Product Brands.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, db_index=True)
    website = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    """
    Advanced AI Product model.
    Supports Structured Specs, AI Attributes, and RAG-optimized Vector search.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Core Metadata
    stock = models.IntegerField(default=0)
    part_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    barcode = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Structured Technical Specs (Regex-driven)
    diameter = models.FloatField(null=True, blank=True, db_index=True)
    width = models.FloatField(null=True, blank=True, db_index=True)
    offset = models.FloatField(null=True, blank=True, db_index=True)
    bolt_pattern = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    finish = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Normalized Relations
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='products')
    
    # AI Search & Feature Logic
    attributes = models.JSONField(default=dict, help_text="Strict keys: vehicle_type, usage, style, terrain, durability")
    features = models.JSONField(default=list, help_text="JSON Array of key product features")
    ai_summary = models.TextField(blank=True, help_text="Clean AI-generated product summary")
    price_category = models.CharField(max_length=20, blank=True, db_index=True)
    
    # RAG Optimization
    embedding_text = models.TextField(blank=True, help_text="The 'Golden String' used for high-quality Vector generation")
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    
    # Legacy Fallback
    searchable_text = models.TextField(blank=True, help_text="Materialized field for fallback keyword search")

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        indexes = [
            HnswIndex(
                name="product_embedding_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"]
            ),
            models.Index(fields=['searchable_text'], name='product_search_idx'),
        ]

    def save(self, *args, **kwargs):
        # Auto-populate searchable_text as a safety fallback
        self.searchable_text = f"{self.name} {self.brand.name} {self.category.name} {self.ai_summary}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.brand.name} - {self.name} (${self.price})"


class Lead(models.Model):
    """
    Customer lead information captured during the chatbot flow.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)

    def __str__(self):
        return f"{self.first_name} ({self.email})"

class Order(models.Model):
    """
    Order tracking linking products and leads.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='orders')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(
        max_length=20, 
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id}"
