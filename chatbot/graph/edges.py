import logging
from chatbot.graph.state import GraphState, Intent
from chatbot.helpers.constants import DomainTypes

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.graph.edges")

async def route_to_action(state: GraphState):
    """
    DETERMINISTIC ROUTER (Production 8 - Stage Driven).
    100% Async-Native for event-loop efficiency.
    Maps state and context to the Expert branches.
    """
    action_type = state.get("action_type", "discovery")
    domain = state.get("domain", "wheels")
    
    # 1. THE IRON DOMAIN SHUNT
    if domain == DomainTypes.HARD_OUT:
        return "discovery_node" # Synthesizer will handle the hard_block persona

    # 2. DETERMINISTIC ACTION MAPPING
    # action_type mapping to physical node keys
    mapping = {
        "recommend": "recommender_node",
        "info": "info_node",
        "discovery": "discovery_node",
        "hesitant": "info_node", # Info node handles hesitations with technical/value value-add
        "pivot": "discovery_node", # Discovery node handles pivots back to wheels
        "hard_block": "discovery_node" # Blocks routed through discovery for synthesis
    }

    target = mapping.get(action_type, "discovery_node")
    logger.info(f"Router [HARDENED]: Routing action '{action_type}' -> '{target}'")
    return target
