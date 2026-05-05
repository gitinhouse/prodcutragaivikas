import uuid
from django.db import models
from django.contrib.postgres.indexes import GinIndex
from pgvector.django import VectorField, HnswIndex

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
    product = models.ForeignKey('WheelProduct', on_delete=models.PROTECT, related_name='orders')
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


class VehicleYear(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    year = models.IntegerField(unique=True, db_index=True)

    class Meta:
        verbose_name = "Vehicle Year"
        verbose_name_plural = "Vehicle Years"

    def __str__(self):
        return str(self.year)

class VehicleMake(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    make_fitment_id = models.CharField(max_length=100, db_index=True)
    years = models.IntegerField(db_index=True)
    make_fitment_value = models.CharField(max_length=255, db_index=True)

    class Meta:
        verbose_name = "Vehicle Make"
        verbose_name_plural = "Vehicle Makes"

    def __str__(self):
        return f"{self.make_fitment_value} ({self.years})"

class VehicleModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    make_fitment_id = models.CharField(max_length=100, db_index=True)
    year = models.IntegerField(db_index=True)
    model_fitment_id = models.CharField(max_length=100, db_index=True)
    model_fitment_value = models.CharField(max_length=255, db_index=True)

    class Meta:
        verbose_name = "Vehicle Model"
        verbose_name_plural = "Vehicle Models"

    def __str__(self):
        return f"{self.model_fitment_value} ({self.year})"

class WheelProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    product_name = models.CharField(max_length=255, db_index=True)
    product_desc = models.TextField(blank=True, null=True)
    brand_desc = models.CharField(max_length=100, db_index=True)
    style = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    fancy_finish_desc = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    
    diameter = models.FloatField(null=True, blank=True, db_index=True)
    width = models.FloatField(null=True, blank=True, db_index=True)
    bolt_pattern_metric = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    bolt_pattern_standard = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    wheel_offset = models.CharField(max_length=50, blank=True, null=True)
    backspacing = models.FloatField(null=True, blank=True)
    centerbore = models.FloatField(null=True, blank=True)
    
    image_url1 = models.URLField(max_length=1000, blank=True, null=True)
    category_name = models.CharField(max_length=100, blank=True, null=True)
    size_desc = models.CharField(max_length=255, blank=True, null=True)
    quantity = models.IntegerField(default=0)
    map_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Vector Search
    embedding_text = models.TextField(blank=True, help_text="The 'Golden String' used for high-quality Vector generation")
    embedding = VectorField(dimensions=1536, null=True, blank=True)

    class Meta:
        verbose_name = "Wheel Product"
        verbose_name_plural = "Wheel Products"
        indexes = [
            HnswIndex(
                name="wheel_prod_embedding_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"]
            ),
        ]

    def __str__(self):
        return f"{self.brand_desc} - {self.product_name} ({self.sku})"
