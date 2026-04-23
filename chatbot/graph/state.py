from typing import List, Optional, TypedDict, Dict, Any
from enum import Enum
from langgraph.graph import MessagesState

class Intent(Enum):
    PRODUCT_QUERY = "product_query"
    INFO_REQUEST = "info_request"
    PURCHASE_INTENT = "purchase_intent"
    HESITANT = "hesitant"
    NEEDS_CLARITY = "needs_clarity"
    GREETING = "greeting"
    ORDER_STATUS = "order_status"
    OUT_OF_SCOPE = "out_of_scope"
    FOLLOW_UP = "follow_up"

class GraphState(MessagesState):
    # --- CORE QUERY DATA ---
    last_user_query: str
    sanitized_input: str
    
    # --- VEHICLE AUTHORITY ---
    vehicle_context: Dict[str, Any] # year, make, model, type
    vehicle_locked: bool # True once make/model are valid
    
    # --- SHOPPING CONTEXT (The pillars) ---
    extracted_entities: Dict[str, Any] # brand, size, style, budget_max, vehicle_type
    wheel_size: Optional[str]
    budget: Optional[float]
    style: Optional[str]
    
    # --- SYSTEM CONTROL ---
    intent: str # Using string for easier JSON handling
    domain: str # in_scope, soft_out, hard_out
    sales_stage: str # discovery, guided_discovery, partial_recommend, recommend, closing
    action_type: str # The physical node to route to: recommend, discovery, info, hard_block
    cta_intent: str # The tactical play
    confidence_score: float # LLM confidence (0.0 - 1.0)
    category: str # Normalized product category: wheels, tires, other
    is_contextual: bool # True if user is referencing something from prior context
    context_ref: Optional[str] # What specifically user is asking about: price, availability, etc.
    context_payload: Dict[str, Any] # Structured context for downstream nodes
    
    # --- UX & FLOW CONTROL ---
    is_follow_up: bool
    pivot_count: int
    muzzle_response: bool
    is_greeting: bool
    
    # --- MEMORY & RESULTS ---
    raw_response_data: Dict[str, Any] # Products, reasons, flags
    recommended_products: List[str] # Names of shown products
    shown_products: List[str] # Persistence list to avoid repeats
    has_valid_results: bool # True if recommender found matches
    resolved_product: Optional[str] # Currently discussed product
    customer_email: Optional[str] # Captured lead email
    has_email: bool # True once email is captured
    final_response: str
    metrics: Dict[str, Any] # time, tokens, model_info
