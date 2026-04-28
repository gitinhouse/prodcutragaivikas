from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class VehicleAttributes(BaseModel):
    """Extracted vehicle information."""
    vehicle_year: Optional[int] = Field(None, description="The year of the vehicle (e.g. 2015)")
    vehicle_make: Optional[str] = Field(None, description="The manufacturer of the vehicle (e.g. Audi, Toyota)")
    vehicle_model: Optional[str] = Field(None, description="The specific model of the vehicle (e.g. A4, Tacoma)")
    wheel_brand: Optional[str] = Field(None, description="The specific wheel manufacturer (e.g. Fuel, BBS, Vossen)")
    size: Optional[str] = Field(None, description="The desired wheel size/diameter")
    style: Optional[str] = Field(None, description="The desired style (e.g. rugged, sporty, luxury)")
    finish: Optional[str] = Field(None, description="The desired wheel finish (e.g. matte black, chrome)")
    budget_max: Optional[float] = Field(None, description="The maximum price or budget for the wheels")

class IdentitySchema(BaseModel):
    """Extracted lead information."""
    name: Optional[str] = Field(None, description="The user's first name")
    email: Optional[str] = Field(None, description="The user's email address")
    phone: Optional[str] = Field(None, description="The user's phone number")

class ProductAttributes(BaseModel):
    """Deep product attributes for catalog ingestion."""
    vehicle_type: List[str] = Field(default_factory=list, description="Types of vehicles supported (e.g. SUV, Truck, Sedan)")
    usage: List[str] = Field(default_factory=list, description="Intended usage (e.g. Off-road, Track, Street)")
    style: List[str] = Field(default_factory=list, description="Aesthetic style (e.g. Rugged, Luxury, Sport)")
    terrain: List[str] = Field(default_factory=list, description="Compatible terrain (e.g. Mud, Sand, Pavement)")
    durability: str = Field(default="Standard", description="Durability rating")

class ProductAIExtraction(BaseModel):
    """Structured data extracted from product descriptions during catalog import."""
    attributes: ProductAttributes = Field(default_factory=ProductAttributes)
    features: List[str] = Field(default_factory=list, description="Key technical features of the product")
    ai_summary: str = Field(description="A clean, one-sentence marketing summary")

class ControllerSchema(BaseModel):
    """The structured output for intent classification and entity extraction."""
    intent: str = Field(description="The primary intent: fitment_lookup, fitment_check, recommendation, product_search, show_more_options, product_detail, brand_inquiry, purchase_intent, greeting, info_request, out_of_scope")
    category: str = Field(default="wheels", description="The product category: wheels, tires, or other")
    confidence: float = Field(default=1.0, description="Confidence score from 0.0 to 1.0")
    domain: str = Field(default="in_scope", description="Whether the request is 'in_scope' or 'hard_out'")
    is_contextual: bool = Field(default=False, description="True if the message refers to previous items in the conversation")
    context_ref: Optional[str] = Field(None, description="The specific reference in context: price, availability, finish, size, specs")
    selected_product: Optional[str] = Field(None, description="The exact name of a product the user wants to buy or get details for")
    missing_fields: List[str] = Field(default_factory=list, description="List of required fields missing from the user's query (e.g. vehicle_make)")
    attributes: VehicleAttributes = Field(default_factory=VehicleAttributes)
