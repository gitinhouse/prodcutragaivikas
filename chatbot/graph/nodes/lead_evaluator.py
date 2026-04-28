import logging
from chatbot.graph.state import GraphState, Intent

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.lead_evaluator")

async def lead_evaluator_node(state: GraphState):
    """
    THE NBA ENGINE V8: Deterministic Strategic Authority.
    Decides the 'Next Best Action' based on Phase, State Gaps, and Business Goals.
    """
    # 0. INGRESS & STATE VALIDATION
    phase = state.get("phase", "VEHICLE_COLLECTION")
    intent = state.get("intent", "product_search")
    signal_type = state.get("signal_type", "EXPLICIT_INTENT")
    raw_data = state.get("raw_response_data", {})
    action_type = raw_data.get("action", "discovery")
    
    view_count = state.get("view_count", 0)
    loop_count = state.get("loop_count", 0)
    last_action = state.get("last_action", "")
    
    debug_info = {
        "phase": phase,
        "intent": intent,
        "signal": signal_type,
        "reason": "Standard Phase Progression"
    }

    # 1. PRIORITY LEVEL 1: CRITICAL SIGNAL OVERRIDES
    if signal_type == "RESET":
        debug_info["reason"] = "User requested hard reset."
        return {"cta_intent": "greeting", "raw_response_data": {"action": "reset"}, "debug_info": debug_info}

    # 2. PRIORITY LEVEL 2: CONVERSION LOCKDOWN (Soft Lockdown)
    if phase == "PURCHASE":
        # Allow questions/clarifications but redirect back to the deal
        if intent in ["product_detail", "info_request", "brand_inquiry"]:
            debug_info["reason"] = "Soft lockdown: Answer question then redirect to checkout."
            raw_data["cta_intent"] = "answer_and_close"
            return {"cta_intent": "answer_and_close", "raw_response_data": raw_data, "debug_info": debug_info}
        
        debug_info["reason"] = "High intent detected. Lockdown to closing actions."
        cta = "confirm_order_on_file" if state.get("has_email") else "ask_lead_info"
        return {"cta_intent": cta, "raw_response_data": raw_data, "debug_info": debug_info}

    # 3. PRIORITY LEVEL 3: LOOP DETECTION & FATIGUE
    # Semantic Loop Break: If user keeps saying "show more" or "anything else"
    if loop_count >= 2 and intent != "product_detail":
        debug_info["reason"] = "Fatigue detected. Breaking loop with Top Picks."
        return {"cta_intent": "break_loop_with_guidance", "raw_response_data": raw_data, "debug_info": debug_info}

    # 4. PRIORITY LEVEL 4: PHASE-BASED NBA
    cta_intent = "ask_vehicle"

    if phase == "VEHICLE_COLLECTION":
        cta_intent = "ask_vehicle"
        debug_info["reason"] = "Phase: Missing vehicle data."

    elif phase == "READY_FOR_SEARCH":
        # If we have vehicle but haven't shown results
        cta_intent = "show_options"
        debug_info["reason"] = "Phase: Vehicle complete, moving to search."

    elif phase == "BROWSING":
        # Intelligent Browser Nudges
        if view_count > 3:
            cta_intent = "recommend_top_pick"
            debug_info["reason"] = "Browse fatigue: Suggesting top match."
        elif signal_type == "ACKNOWLEDGEMENT" and last_action == "recommendation":
             cta_intent = "suggest_comparison"
             debug_info["reason"] = "User acknowledged results. Offering comparison."
        else:
            cta_intent = "show_options"
            debug_info["reason"] = "Standard browsing."

    # 5. SAFETY FALLBACK (The Net)
    if not cta_intent or (phase == "VEHICLE_COLLECTION" and action_type == "recommend"):
        logger.warning("NBA Engine: Inconsistent state detected. Triggering safe fallback.")
        cta_intent = "safe_fallback"
        debug_info["reason"] = "Safety Fallback triggered."

    # 6. RE-ENGAGEMENT HOOK
    if last_action == "recovery" and phase != "VEHICLE_COLLECTION":
        raw_data["apply_reengagement"] = True

    raw_data["cta_intent"] = cta_intent
    logger.info(f"NBA Engine Final Choice: '{cta_intent}' | Reason: {debug_info['reason']}")

    return {
        "cta_intent": cta_intent,
        "raw_response_data": raw_data,
        "debug_info": debug_info
    }
