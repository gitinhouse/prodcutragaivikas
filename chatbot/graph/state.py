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
    active_filters: Dict[str, Any] # size, finish, style (Persists during session)
    wheel_size: Optional[str]
    budget: Optional[float]
    style: Optional[str]
    
    # --- SYSTEM CONTROL (The Engine) ---
    phase: str # VEHICLE_COLLECTION, READY_FOR_SEARCH, BROWSING, PURCHASE
    intent: str 
    signal_type: str # ACKNOWLEDGEMENT, CORRECTION, EXPLICIT_INTENT, RESET
    domain: str # in_scope, soft_out, hard_out
    sales_stage: str # discovery, fitment, recommendation, closing
    action_type: str # recommend, discovery, info, hard_block
    cta_intent: str # tactical play
    debug_info: Dict[str, Any] # explainability layer
    
    # --- UX & FLOW CONTROL ---
    view_count: int
    loop_count: int
    is_follow_up: bool
    pivot_count: int
    muzzle_response: bool
    is_greeting: bool
    
    # --- MEMORY & RESULTS ---
    raw_response_data: Dict[str, Any] # Products, reasons, flags
    recommended_products: List[str] # Names of shown products
    shown_products: List[str] # Persistence list to avoid repeats
    rejected_products: List[str] # Products user specifically disliked
    has_valid_results: bool # True if recommender found matches
    resolved_product: Optional[str] # Currently discussed product
    customer_name: Optional[str] # Captured lead name
    customer_email: Optional[str] # Captured lead email
    has_email: bool # True once email is captured
    final_response: str
    last_final_response: Optional[str]
    metrics: Dict[str, Any] # time, tokens, model_info
