import logging
from chatbot.graph.state import GraphState

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.clarify")

async def clarify_node(state: GraphState):
    """
    Expert Discovery Node.
    Hardened for Progressive Discovery (Ask one thing at a time).
    """
    entities = state.get("extracted_entities", {})
    vehicle_context = state.get("vehicle_context", {})
    cta_intent = state.get("cta_intent", "ask_preference")
    
    logger.info(f"Clarify: Initiating Progressive Discovery (Strategy={cta_intent})...")
    
    # 1. ANALYZE PILLARS
    has_make_model = bool(vehicle_context.get("make") and vehicle_context.get("model"))
    has_style = bool(entities.get("style")) or bool(entities.get("usage"))
    has_budget = bool(entities.get("budget_max"))
    
    # 2. PROGRESSIVE SELECTION (Ask ONE thing to maintain conversion speed)
    # Priority: Vehicle -> Style -> Budget
    missing_fields = []
    if not has_make_model:
        missing_fields = ["vehicle (Year, Make, Model)"]
    elif not has_style:
        missing_fields = ["preferred style or usage"]
    elif not has_budget:
        missing_fields = ["budget range"]
    else:
        # If everything is known but we are here, clarify the "Pillar of Importance"
        missing_fields = ["which factor is most important (price, style, or performance)"]
        
    logger.info(f"Clarify: Progressive field identified: {missing_fields}")
    
    return {
        "raw_response_data": {
            "action": "discovery",
            "cta_intent": cta_intent,
            "missing_fields": missing_fields
        }
    }
