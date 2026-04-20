from chatbot.graph.state import GraphState, Intent

async def route_to_action(state: GraphState):
    """
    DETERMINISTIC ROUTER (Production 7 Standard).
    100% Async-Native for event-loop efficiency.
    Maps intent and domain signals to the 3 Action Expert branches.
    """
    intent = state.get("intent")
    domain = state.get("domain", "wheels")
    
    # 1. THE IRON DOMAIN SHUNT
    # If out of scope or muzzle is active, force to discovery (domain-aware-refusal)
    if domain == "out_of_scope" or state.get("muzzle_response"):
        return "discovery_node"

    # 2. THE SPECIFICATION OVERRIDE (Break Discovery Loop)
    # If we have a diameter or bolt pattern, we show products, even if they are asking info.
    entities = state.get("extracted_entities", {})
    if entities.get("size") or entities.get("bolt_pattern"):
        return "recommender_node"

    # 3. INTENT-BASED MAPPING (Robust String-Aware Checks)
    intent_str = str(intent.value if hasattr(intent, "value") else intent).lower()

    if intent_str == "product_query":
        return "recommender_node"
        
    if intent_str in ["info_request", "hesitant", "purchase_intent"]:
        return "info_node"
        
    if intent_str == "needs_clarity":
        return "discovery_node"
        
    # Default Safety Net (Converge to Discovery)
    return "discovery_node"
