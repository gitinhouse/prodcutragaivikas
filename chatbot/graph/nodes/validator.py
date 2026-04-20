import logging
import re
from chatbot.graph.state import GraphState
from chatbot.helpers.constants import DENIAL_MASTER_LIST, VIOLATION_MAP

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.validator")

async def validator_node(state: GraphState):
    """
    DOMAIN SHIELD: Hardness Check.
    Hardened for Ingress Synchronization: Pulls latest message into state.
    """
    # 0. INGRESS SYNCHRONIZATION (CRITICAL)
    # Pull the latest HumanMessage content into the deterministic 'last_user_query' field.
    messages = state.get("messages", [])
    raw_query = messages[-1].content if messages else ""
    user_query = raw_query.lower().strip()
    
    prev_domain = state.get("domain", "wheels")
    
    logger.info(f"Validator: Auditing query for domain integrity ('{user_query}'). Previous Domain: {prev_domain}")
    
    # Update state for downstream nodes
    state_update = {
        "last_user_query": raw_query
    }

    # 1. HARD DENIAL (Explicit Violations)
    # This always triggers regardless of memory.
    for category, keywords in VIOLATION_MAP.items():
        if any(f" {k} " in f" {user_query} " for k in keywords):
            logger.warning(f"DOMAIN VIOLATION DETECTED: Category={category}")
            return {
                **state_update,
                "domain": "out_of_scope",
                "iron_domain_violation": True,
                "detected_violation_category": category,
                "muzzle_response": True
            }

    # 2. SOFT DOMAIN CHECK (Sales Resilience)
    # If the domain is already established as 'wheels', we allow generic affirmations/requests.
    is_affirming = any(k in user_query for k in ["yes", "please", "show", "give", "tell", "more", "look", "recommendation"])
    
    if prev_domain == "wheels":
        if is_affirming or len(user_query.split()) < 3:
            logger.info("Validator [Domain Lock]: Allowing established sales context to continue.")
            return {
                **state_update,
                "domain": "wheels",
                "iron_domain_violation": False,
                "muzzle_response": False
            }

    # 3. INITIAL DOMAIN VALIDATION (Strict Mode)
    # If this is a new session or out-of-scope intent, we are strict.
    if state.get("domain") == "out_of_scope":
        logger.warning("Validator: Strict Match Failed. Triggering Nuclear Refusal.")
        return {**state_update, "muzzle_response": True, "iron_domain_violation": True}

    return {**state_update, "iron_domain_violation": False, "muzzle_response": False}
