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
    is_wheel_brand = models.BooleanField(default=False, db_index=True, help_text="Flags this brand as a known wheel manufacturer")

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
        # Enriched with finish and bolt_pattern for better keyword matching
        self.searchable_text = f"{self.name} {self.brand.name} {self.category.name} {self.finish or ''} {self.bolt_pattern or ''} {self.ai_summary}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.brand.name} - {self.name} (${self.price})"

class Fitment(models.Model):
    """
    Relational Fitment Mapping.
    Allows exact vehicle matching (Year, Make, Model) to specific Products.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='fitments')
    
    make = models.CharField(max_length=100, db_index=True)
    model = models.CharField(max_length=100, db_index=True)
    year_from = models.IntegerField(db_index=True)
    year_to = models.IntegerField(db_index=True)
    
    # Optional constraints mapped from vendor
    bolt_pattern = models.CharField(max_length=50, blank=True, null=True)
    center_bore = models.FloatField(blank=True, null=True)
    offset_min = models.FloatField(blank=True, null=True)
    offset_max = models.FloatField(blank=True, null=True)

    class Meta:
        verbose_name = "Fitment"
        verbose_name_plural = "Fitments"
        indexes = [
            models.Index(fields=['make', 'model']),
        ]

    def __str__(self):
        return f"{self.make} {self.model} ({self.year_from}-{self.year_to}) -> {self.product.name}"

class VehicleTypeLimit(models.Model):
    """
    Physical constraints (max diameter/width) by vehicle type (e.g. sedan, suv).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle_type = models.CharField(max_length=50, unique=True, db_index=True, help_text="e.g. sedan, suv, truck")
    max_diameter = models.FloatField(help_text="Maximum allowed wheel diameter in inches")
    max_width = models.FloatField(help_text="Maximum allowed wheel width in inches")
    
    class Meta:
        verbose_name = "Vehicle Type Limit"
        verbose_name_plural = "Vehicle Type Limits"

    def __str__(self):
        return f"{self.vehicle_type} (Max D: {self.max_diameter}, Max W: {self.max_width})"

class BoltPatternRule(models.Model):
    """
    Bolt Pattern mappings for Make and optionally Model.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    make = models.CharField(max_length=100, db_index=True, help_text="Vehicle Make (e.g. ford, honda)")
    model = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="Optional Vehicle Model (e.g. f-150)")
    patterns = models.JSONField(help_text="List of valid bolt patterns e.g. [\"5x114.3\", \"6x135\"]")

    class Meta:
        verbose_name = "Bolt Pattern Rule"
        verbose_name_plural = "Bolt Pattern Rules"
        constraints = [
            models.UniqueConstraint(fields=['make', 'model'], name='unique_make_model_rule')
        ]

    def __str__(self):
        if self.model:
            return f"{self.make} {self.model} -> {self.patterns}"
        return f"{self.make} (Default) -> {self.patterns}"

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

class AgentSession(models.Model):
    """
    Persistent memory for the Agentic Sales Advisor.
    Tracks user progression through the sales stages and holds their specific constraints.
    """
    class Stage(models.TextChoices):
        DISCOVERY = 'discovery', 'Discovery'
        FITMENT_VALIDATION = 'fitment_validation', 'Fitment Validation'
        READY_TO_RECOMMEND = 'ready_to_recommend', 'Ready to Recommend'
        CLOSING = 'closing', 'Closing'

    session_id = models.CharField(max_length=255, unique=True, primary_key=True)
    sales_stage = models.CharField(
        max_length=50,
        choices=Stage.choices,
        default=Stage.DISCOVERY,
        db_index=True
    )

    # Context Data
    vehicle_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores parsed Year, Make, Model, and specific DB-matched Type"
    )
    identified_budget = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    identified_style = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores style preferences (e.g., finish, usage, off-road vs street)"
    )

    # Lead Tracking
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Session {self.session_id} - {self.sales_stage}"

