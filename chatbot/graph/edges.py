from chatbot.graph.state import GraphState, Intent

async def route_to_action(state: GraphState):
    """
    DETERMINISTIC ROUTER (Production 8 - Stage Driven).
    100% Async-Native for event-loop efficiency.
    Maps state and context to the Expert branches.
    """
    intent = state.get("intent")
    domain = state.get("domain", "wheels")
    stage = state.get("sales_stage", "discovery")
    
    vehicle_context = state.get("vehicle_context", {})
    sales_context = state.get("sales_context", {})
    entities = state.get("extracted_entities", {})
    
    # 1. THE IRON DOMAIN SHUNT
    # If out of scope or muzzle is active, force to discovery (domain-aware-refusal)
    if domain == "out_of_scope" or state.get("muzzle_response"):
        return "discovery_node"

    # 2. STRONG CONTEXT & SOFT GATE
    has_vehicle = bool(vehicle_context.get("make") and vehicle_context.get("model")) or bool(vehicle_context.get("vehicle_type")) or bool(entities.get("vehicle_type"))
    has_strong_context = bool(
        sales_context.get("budget_max") or 
        sales_context.get("size") or 
        sales_context.get("bolt_pattern") or 
        sales_context.get("style") or
        entities.get("size") or
        entities.get("bolt_pattern") or
        entities.get("style")
    )

    intent_str = str(intent.value if hasattr(intent, "value") else intent).lower()

    # 3. STATE-BASED DECISION
    if stage == "closing":
        return "info_node" # Post-closing behavior, e.g. order tracking

    if intent_str in ["product_query", "purchase_intent"]:
        # SOFT GATE: Allow product query if vehicle is known OR strong context is present
        if has_vehicle or has_strong_context:
            return "recommender_node"
        else:
            return "discovery_node"

    if intent_str in ["info_request", "hesitant"]:
        return "info_node"
        
    if intent_str == "needs_clarity":
        return "discovery_node"
        
    # Default Safety Net (Converge to Discovery)
    return "discovery_node"
