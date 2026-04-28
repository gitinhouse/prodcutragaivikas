import re
import logging
from chatbot.graph.state import GraphState

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.validator")

async def validator_node(state: GraphState):
    """
    THE STATE VALIDATION LAYER V8.
    Ensures state integrity and performs high-speed identity extraction.
    """
    # 0. HARD STATE VALIDATION (Safety Net)
    if state is None:
        logger.error("Validator: State is NONE. Emergency recovery.")
        return {"phase": "VEHICLE_COLLECTION", "view_count": 0, "loop_count": 0}

    # Initialize Missing Fields (Default State)
    init_updates = {}
    if "phase" not in state: init_updates["phase"] = "VEHICLE_COLLECTION"
    if "view_count" not in state: init_updates["view_count"] = 0
    if "loop_count" not in state: init_updates["loop_count"] = 0
    if "active_filters" not in state: init_updates["active_filters"] = {}
    if "shown_products" not in state: init_updates["shown_products"] = []
    if "rejected_products" not in state: init_updates["rejected_products"] = []
    if "vehicle_context" not in state: init_updates["vehicle_context"] = {}

    # 1. INGRESS SYNCHRONIZATION
    messages = state.get("messages", [])
    raw_query = messages[-1].content if messages else ""
    user_query = raw_query.strip()
    
    current_name = state.get("customer_name")
    current_email = state.get("customer_email")

    # 2. SMART IDENTITY EXTRACTION (Structured)
    from chatbot.graph.schemas import IdentitySchema
    from config.llm_config import get_llm
    
    new_name = current_name
    new_email = current_email
    
    # Regex fallback for email (extremely fast)
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_query)
    if email_match:
        new_email = email_match.group(0)

    # LLM extraction for name and missing email
    if not (new_name and new_email) and len(user_query.split()) > 1:
        try:
            llm = get_llm()
            structured_llm = llm.with_structured_output(IdentitySchema)
            res = await structured_llm.ainvoke(f"Extract name and email from this message: {user_query}")
            if res.name: new_name = res.name
            if res.email: new_email = res.email
        except Exception as e:
            logger.warning(f"Validator: Identity extraction failed: {e}")

    logger.info(f"Validator: Ingress Verified. Name='{new_name}' Email='{new_email}'")
    
    return {
        **init_updates,
        "last_user_query": raw_query,
        "sanitized_input": user_query.lower(),
        "customer_name": new_name,
        "customer_email": new_email,
        "has_email": bool(new_email)
    }
