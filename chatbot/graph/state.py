import operator
from langgraph.graph import MessagesState
from typing import List, Optional, Annotated, TypedDict, Union
from enum import Enum

class Intent(Enum):
    """
    Production-Grade Intent Schema.
    """
    PRODUCT_QUERY = "product_query"
    INFO_REQUEST = "info_request"   
    NEEDS_CLARITY = "needs_clarity" 
    HESITANT = "hesitant"
    PURCHASE_INTENT = "purchase_intent"
    OTHER = "other"

class LeadStatus(TypedDict):
    """
    Strict Lead Tracker (Deterministic).
    """
    attempts: int
    has_email: bool
    last_asked_turn: int

class VehicleContext(TypedDict, total=False):
    year: Optional[Union[int, str]]
    make: Optional[str]
    model: Optional[str]
    vehicle_type: Optional[str]

class SalesContext(TypedDict, total=False):
    budget_max: Optional[float]
    size: Optional[str]
    bolt_pattern: Optional[str]
    style: Optional[str]
    brand: Optional[str]

class GraphState(MessagesState):
    """
    Master Production State for Sebastian (Production 7 Hardened).
    """
    session_id: str # Ties explicitly to AgentSession model
    sales_stage: str # Matches AgentSession.Stage
    
    # Context Data
    vehicle_context: VehicleContext # Ties to AgentSession.vehicle_data
    sales_context: SalesContext # Consolidates identified_budget, identified_style
    identified_budget: Optional[float] # Legacy tie to AgentSession.identified_budget
    identified_style: dict # Legacy tie to AgentSession.identified_style

    # 1. Classification & Intelligence
    intent: Union[Intent, str]
    intent_confidence: Optional[float]
    sentiment: Optional[str]
    advisor_history: List[str] # Chain of steps completed
    
    # 2. Domain & Integrity Guards (NEW)
    domain: str # "wheels" | "out_of_scope"
    product_type: str # "wheels" | "tires" | "lift_kits" | "other"
    muzzle_response: bool # Signal to Synthesizer to use Nuclear Refusal
    iron_domain_violation: bool # Deterministic Keyword Shield Flag
    detected_violation_category: Optional[str] # e.g., "Food", "Tires"
    
    # 3. Entity Resolution
    resolved_entity_type: str # "SKU" | "BRAND" | "GENERIC" | "NONE"
    resolved_product: Optional[dict] # {name, sku, price, specs}
    
    # 4. History & Loop Protection
    last_action: str # "info" | "recommend" | "discovery" | "fallback" | "refusal"
    last_user_query: str # Normalized version for loop detection
    repeat_count: int
    
    # 5. Extraction Metadata
    extracted_entities: Annotated[dict, operator.ior]
    newly_extracted_entities: Optional[dict] # Transient per-turn entities
    missing_fields: List[str]
    
    # 6. Recommendation Context
    recommended_products: List[str]
    recommended_products_metadata: List[dict]
    
    # 7. Lead Capture
    lead_status: LeadStatus
    customer_name: Optional[str]
    customer_email: Optional[str]
    has_email: bool # Hard Anti-Nag Guard
    
    # 8. Structural Flow (Internal Payloads)
    raw_response_data: Optional[dict] 
    
    # 9. Control
    iteration_count: int = 0
    is_exhausted: bool = False
    sanitized_input: Optional[str] = None
    pii_found: bool = False
    
    # 10. Persona State
    is_greeting: bool = False
