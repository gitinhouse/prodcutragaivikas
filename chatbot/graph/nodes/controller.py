import re
import json
import logging
from typing import List, Optional
from chatbot.graph.state import GraphState
from chatbot.helpers.state_manager import StateManager
from chatbot.helpers.constants import DomainTypes
from chatbot.helpers.prompts import CLASSIFIER_PROMPT
from config.llm_config import get_llm

logger = logging.getLogger("chatbot.nodes.controller")

def _match_product(query: str, shown_products: List[str]) -> Optional[str]:
    """Resilient product matching from conversation history."""
    if not query or not shown_products:
        return None
        
    query_low = query.lower()
    
    # 1. Exact Match (Sanitized)
    for p in shown_products:
        if p.lower() in query_low:
            return p
            
    # 2. Key Term Match (e.g. 'Bbs Model-21' matches if user says 'Bbs 21')
    # Extract brand + numbers/model identifiers
    query_tokens = set(re.findall(r'\w+', query_low))
    for p in shown_products:
        p_low = p.lower()
        p_tokens = set(re.findall(r'\w+', p_low))
        # If major identifiers overlap (brand and model number)
        if len(query_tokens.intersection(p_tokens)) >= 2:
            return p
            
    return None

def _route(intent, state, result, updated_state, user_query):
    phase = updated_state.get("phase", "VEHICLE_COLLECTION")
    shown_products = updated_state.get("shown_products", [])
    resolved_product = updated_state.get("resolved_product")
    has_lead = bool(state.get("customer_email") or state.get("has_email"))
    
    llm_selected = result.get("selected_product")
    context_ref = result.get("context_ref")
    is_contextual = result.get("is_contextual", False)
    signal_type = result.get("signal_type", "EXPLICIT_INTENT")

    base = {
        "intent": intent,
        "is_contextual": is_contextual,
        "context_ref": context_ref,
        "action_type": "info", 
        "cta_intent": "clarify",
        "phase": phase
    }

    if intent == "greeting":
        return {**base, "action_type": "info", "cta_intent": "greeting"}
        
    if signal_type == "ACKNOWLEDGEMENT" or intent == "thank_you":
        return {**base, "action_type": "info", "cta_intent": "continue_flow"}

    if intent == "out_of_scope":
        return {**base, "action_type": "info", "cta_intent": "recovery"}

    if signal_type == "RESET":
        return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

    if intent == "purchase_intent":
        if not shown_products:
            return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}
        
        # TRANSITION: Final Order Confirmation (Loop Breaker)
        last_cta = state.get("cta_intent")
        if last_cta == "confirm_order_on_file":
            return {**base, "action_type": "info", "cta_intent": "close"}

        matched = _match_product(user_query, shown_products)
        if matched:
            target_cta = "ask_lead_info" if not has_lead else "confirm_order_on_file"
            return {**base, "action_type": "recommend", "cta_intent": target_cta,
                    "context_payload": {"selected_product": matched},
                    "resolved_product": matched}
        if phase in ["BROWSING", "PURCHASE"]:
            return {**base, "action_type": "recommend", "cta_intent": "show_options"}
        return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

    if intent in ["product_search", "fitment_lookup", "recommendation", "show_more_options"]:
        if phase in ["BROWSING", "PURCHASE", "READY_FOR_SEARCH"]:
            return {**base, "action_type": "recommend", "cta_intent": "show_options"}
        else:
            return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

    if intent == "product_detail" or (intent == "info_request" and is_contextual):
        about = resolved_product or (shown_products[0] if shown_products else None)
        if not about and not llm_selected:
            return {**base, "action_type": "info", "cta_intent": "clarify_product"}
        return {**base, "action_type": "info", "cta_intent": "product_detail",
                "context_payload": {"about_product": about}}

    if phase != "VEHICLE_COLLECTION":
        return {**base, "action_type": "recommend", "cta_intent": "show_options"}
    return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

async def controller_node(state: GraphState):
    user_query = state.get("sanitized_input", state.get("last_user_query", "")).lower()
    full_history = state.get("messages", [])
    sales_stage = state.get("sales_stage", "discovery")

    # 1. LLM CLASSIFICATION
    from chatbot.graph.schemas import ControllerSchema
    llm = get_llm()
    try:
        structured_llm = llm.with_structured_output(ControllerSchema)
        raw_result = await structured_llm.ainvoke([
            {"role": "system", "content": CLASSIFIER_PROMPT},
            *(full_history[-6:])
        ])
        result = raw_result.model_dump()
    except Exception as e:
        logger.error(f"Controller: Structured Output failed: {e}")
        result = {"intent": "product_search", "category": "wheels", "attributes": {}, "signal_type": "EXPLICIT_INTENT", "confidence": 1.0}

    # 2. DETERMINISTIC OVERRIDES
    confirm_patterns = r"(?i)^(yes|correct|yep|yeah|that's it|exactly|confirm|yes it is|it is correct)$"
    is_short_confirm = bool(re.search(confirm_patterns, user_query.strip()))
    is_thanks = bool(re.search(r"\b(thank|thanks|thx|ty|grateful)\b", user_query))
    is_contact_info = bool(re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_query)) or (len(user_query.split()) <= 4 and bool(re.search(r"\b(my name is|i am|it's)\b", user_query)))
    
    if is_thanks:
        result["intent"] = "thank_you"
        result["signal_type"] = "ACKNOWLEDGEMENT"
    elif is_contact_info and sales_stage == "closing":
        result["intent"] = "info_request"
        result["is_contextual"] = True
    # 2.2 NUCLEAR BRAND PIVOT
    # If user mentions a DIFFERENT brand than current, trigger a surgical reset
    current_make = (state.get("vehicle_context") or {}).get("make", "").lower()
    new_make_match = re.search(r"\b(audi|bmw|honda|mercedes|tesla|toyota|jeep|ford|chevy|dodge|ram|civic|camry|accord|f150)\b", user_query)
    
    if new_make_match:
        found_brand = new_make_match.group(1).lower()
        # Map models to brands for pivot detection
        brand_map = {"civic": "honda", "camry": "toyota", "accord": "honda", "f150": "ford"}
        resolved_new_brand = brand_map.get(found_brand, found_brand)
        
        if current_make and resolved_new_brand != current_make and resolved_new_brand not in ["f150"]:
             logger.info(f"Controller: Nuclear Pivot detected. {current_make} -> {resolved_new_brand}. Resetting context.")
             result["signal_type"] = "RESET"
             result["intent"] = "product_search"

    elif bool(re.search(r"\b(20\d{2}|audi|bmw|civic|honda|mercedes|tesla|toyota|jeep|ford|chevy|dodge|ram|maruti|suzuki|tata|mahindra)\b", user_query)) or bool(re.search(r"\$\d+|under \d+|budget", user_query)):
        if result.get("intent") not in ["purchase_intent", "product_detail", "needs_clarity"]:
            result["intent"] = "product_search"
            
    # 2.5 SMART CONFIRMATION (Prevent 'Ok' Trap)
    last_cta = state.get("cta_intent", "")
    last_action = state.get("last_action", "")
    
    # 2.6 FILTER RESET & TECHNICAL PIVOT
    # Detect 'all', 'any', 'different' to clear sticky filters
    wants_all = bool(re.search(r"\b(all|any|every|different|all colors|show me everything)\b", user_query))
    if wants_all:
        result["reset_filters"] = True
        logger.info("Controller: 'All' signal detected. Resetting persistent filters.")

    # Detect explicit bolt pattern in query (e.g. 5x120)
    has_pattern = bool(re.search(r"\d+x\d+\.?\d*", user_query))
    if has_pattern and result["intent"] == "product_search":
        result["intent"] = "fitment_check"
        result["signal_type"] = "EXPLICIT_INTENT"

    is_offering_more = last_cta in ["show_options", "clarify_product"] or last_action in ["no_fitment_found", "out_of_stock"]

    if is_short_confirm:
        if state.get("resolved_product") and not is_offering_more:
            result["intent"] = "purchase_intent"
        else:
            result["intent"] = "show_more_options" if is_offering_more else "info_request"
            result["is_contextual"] = True
    
    # 3. CONTEXTUAL OVERRIDES
    matched_context_product = _match_product(user_query, state.get("shown_products", []))
    if matched_context_product:
        result["intent"] = "product_detail"
        result["selected_product"] = matched_context_product
        result["is_contextual"] = True
    elif bool(re.search(r"\b(same email|on file|already gave|you have it|wait|hold on|stop)\b", user_query)) and state.get("has_email"):
        result["intent"] = "purchase_intent"
        result["is_contextual"] = True

    # 3.5 REJECTED PRODUCTS
    rejected_products = state.get("rejected_products", [])
    reject_patterns = r"(?i)\b(don't like|not the|remove|ugly|different|hate|no|don't want)\b"
    if re.search(reject_patterns, user_query):
        matched_reject = _match_product(user_query, state.get("shown_products", []))
        if matched_reject and matched_reject not in rejected_products:
            rejected_products.append(matched_reject)

    # 3.6 DOMAIN LOCK
    if result.get("category") == "tires" and not bool(re.search(r"\b(wheel|rim)\b", user_query)):
        return {**state, "action_type": "hard_block", "cta_intent": "redirect_to_domain"}

    # 4. EXECUTE
    state_updates = await StateManager.process_state(state, result, user_query)
    state_updates["rejected_products"] = rejected_products
    
    temp_state = {**state, **state_updates}
    routing = _route(result["intent"], state, result, temp_state, user_query)

    return {**state_updates, **routing}
