import logging
from chatbot.graph.state import GraphState
from chatbot.helpers.prompts import DISCOVERY_PROMPT, STATIC_MESSAGES

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.clarify")

async def clarify_node(state: GraphState):
    """
    Expert Discovery Node.
    Hardened for pure Stage-Driven Extraction (No eager product dumping).
    """
    is_greeting = state.get("is_greeting", False)
    entities = state.get("extracted_entities", {})
    vehicle_context = state.get("vehicle_context", {})
    
    logger.info(f"Clarify: Initiating Pure Discovery (Greeting={is_greeting})...")
    
    # 1. CONSTRUCT PAYLOAD FOR GREETINGS
    if is_greeting:
        logger.info("Clarify: Setting action to 'greeting' for natural persona response.")
        return {
            "raw_response_data": {
                "action": "greeting",
                "message": STATIC_MESSAGES["greeting"]
            }
        }

    # 2. STRICT FALLBACK & EXTRACTION
    has_vehicle = bool(vehicle_context.get("make") and vehicle_context.get("model")) or bool(vehicle_context.get("vehicle_type")) or bool(entities.get("vehicle_type"))
    has_budget = bool(entities.get("budget_max"))
    has_style = bool(entities.get("style")) or bool(entities.get("usage"))
    
    missing_fields = []
    if not has_vehicle:
        missing_fields.append("vehicle")
    elif not has_budget:
        missing_fields.append("budget")
    elif not has_style:
        missing_fields.append("style")
        
    logger.info(f"Clarify: Setting action to 'discovery'. Missing sequential fields: {missing_fields}")
    
    return {
        "raw_response_data": {
            "action": "discovery",
            "instruction": DISCOVERY_PROMPT,
            "missing_fields": missing_fields
        }
    }
