import json
import logging
import re
from langchain_core.messages import AIMessage
from chatbot.graph.state import GraphState
from chatbot.helpers.constants import SAFE_GREETINGS
from chatbot.helpers.prompts import SYNTHESIZER_PROMPT, ACTION_VOICE_CONTRACTS, STATIC_MESSAGES
from config.llm_config import get_llm

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.synthesizer")

async def synthesizer_node(state: GraphState):
    """
    SUPER-NODE 7: The Master Voice & Bookkeeper.
    """
    domain = state.get("domain", "wheels")
    muzzle = state.get("muzzle_response", False)
    
    logger.info(f"Synthesizer: Vocalizing turn (Muzzle={muzzle}, Domain={domain})...")

    # 1. Authority Refusal Path
    if muzzle or domain == "out_of_scope":
        refusal_content = (
            "I specialize exclusively in premium automotive wheels and rims. "
            "I'm afraid I cannot assist with that request, but I would be happy "
            "to help you find the perfect set of wheels for your vehicle—what are you driving?"
        )
        logger.warning("Synthesizer Refusal Path Triggered: Input out of domain.")
        return {
            "messages": [AIMessage(content=refusal_content)],
            "last_action": "refusal"
        }

    # 2. Vocal Synthesis Path
    raw_data = state.get("raw_response_data", {})
    action_type = raw_data.get("action", "fallback")
    has_results = bool(raw_data.get("products"))
    
    logger.info(f"Synthesizer Action Mode: {action_type} | Results Found: {has_results}")

    # --- 3. ZERO-RESULT POLISH ---
    # If we are in 'recommend' mode but have 0 products, 
    # we elevate the prompt to explain fitment difficulty rather than just asking questions.
    enhanced_metadata = {
        "intent": str(state.get("intent")),
        "action_type": action_type,
        "action_output": raw_data,
        "has_results": has_results,
        "lead_allowed": raw_data.get("allow_lead_capture", False),
        "resolved_product": state.get("resolved_product"),
        "conversation_state": {
            "user_stage": state.get("user_stage"),
            "iteration": state.get("iteration_count", 0),
            "fitment_context": state.get("extracted_entities", {})
        }
    }

    vocal_contract = ACTION_VOICE_CONTRACTS.get(action_type, SYNTHESIZER_PROMPT)
    
    # --- 4. ACTION-SPECIFIC VOICE OVERRIDES (STATE-DRIVEN SHIELD) ---
    is_greeting = state.get("is_greeting", False)
    last_user_msg = state.get("messages", [])[-1].content.lower() if state.get("messages") else ""
    is_objection = any(k in last_user_msg for k in ["not those", "wrong", "different", "more", "other"])

    # MASTER BYPASS SWITCH: Force static greeting if query is a pure greeting word (Reliability 100)
    clean_last_msg = re.sub(r'[^a-zA-Z]', '', last_user_msg).strip()
    if clean_last_msg in SAFE_GREETINGS and len(clean_last_msg.split()) <= 2:
        logger.info(f"Synthesizer [MASTER BYPASS]: Forcing static greeting for '{clean_last_msg}'")
        is_greeting = True

    # ⚡ ZERO-LATENCY GREETING BYPASS (MASTER OVERRIDE)
    if is_greeting or action_type == "greeting":
        logger.info("Synthesizer: Pure Greeting detected. Bypassing LLM for zero-latency response.")
        return {
            "messages": [AIMessage(content=raw_data.get("message", STATIC_MESSAGES.get("greeting")))],
            "last_action": "greeting"
        }

    if action_type == "discovery" and has_results:
        logger.info("Setting 'Value-First Discovery' persona (Priority 1).")
        vocal_contract = "ROLE: Style Gallery Advisor. TASK: Enthusiastically showcase these popular examples first. THEN, explain that to guarantee fitment, we'll eventually need the bolt pattern or vehicle info. Make it feel like 'I want to make sure these fit you' rather than 'I need info'."

    elif is_objection and action_type == "recommend":
        logger.info("Setting 'Objection Pivot' persona.")
        vocal_contract = "ROLE: Style Specialist. TASK: Acknowledge that the previous options didn't fit. Pivot gracefully to the new rugged/specific options found. Use 'I hear you' or 'Let's adjust'."

    elif action_type == "recommend" and not has_results:
        logger.info("Injecting Fitment Advisory tone for zero-result recommendation.")
        vocal_contract += "\nNOTE: No products found for these specs. Explain that this fitment is specific and offer to help find alternatives or check wider inventory."

    # --- 5. THE MASTER CLOSER (SALES PRIORITY) ---
    # If the user is trying to buy, we SHUT DOWN the technical consultant and trigger the Closer.
    from chatbot.graph.state import Intent
    intent_val = state.get("intent")
    intent_str = str(intent_val.value if hasattr(intent_val, "value") else intent_val).lower()

    hesitation_signals = ["budget", "price", "too much", "expensive", "costly", "afford", "cheaper"]
    status_signals = ["where is", "track", "status", "check my", "order status", "receive", "received", "haven't got", "did not get"]
    meta_signals = ["updated", "current", "latest", "data", "database", "inventory list", "what brands", "what do you have"]
    pivot_category = state.get("detected_violation_category")
    was_leaded = state.get("lead_status", {}).get("attempts", 0) > 0
    is_affirming = any(k in last_user_msg.lower() for k in ["yes", "ok", "sure", "correct", "perfect", "thanks", "thank you"])

    has_hesitation = any(k in last_user_msg.lower() for k in hesitation_signals) or intent_str == "hesitant"
    has_status_request = any(k in last_user_msg.lower() for k in status_signals)
    has_meta_request = any(k in last_user_msg.lower() for k in meta_signals)
    
    advisor_step = state.get("advisor_step", "discovery_usage")

    if (intent_str == "purchase_intent" or "buy" in last_user_msg) and not has_hesitation and not has_status_request and not pivot_category and not has_meta_request:
        logger.info("Synthesizer [SALES LOCK]: Activating Master Closer Persona.")
        product_name = state.get("resolved_product")
        customer_name = state.get("customer_name")
        customer_email = state.get("customer_email")

        if customer_email:
            name_vocal = f" {customer_name}," if customer_name else ""
            vocal_contract = f"ROLE: Master Sales Closer. TASK: Rule 3 Compliance: Enthusiastically confirm details for {customer_email}.{name_vocal} Explain you are generating the quote for the {product_name or 'wheels'} now. Status: Final Step."
        else:
            vocal_contract = f"ROLE: Master Sales Closer. TASK: Rule 3 Compliance: Enthusiastically confirm we can get those {product_name or 'wheels'} ordered. ASK for customer's Name and Email for the quote. Focus 100% on lead capture for this specific set."
            
    elif has_meta_request:
        logger.info("Synthesizer [META-DATA]: Confirming Expert Knowledge.")
        vocal_contract = "ROLE: Expert Database Specialist. VOICE: Confident, technical, authoritative. TASK: Enthusiastically confirm that your wheel database is fully current and includes the latest releases from premium brands. DO NOT show any specific wheel models yet. Instead, state that to provide an accurate technical fitment from your data, you just need to know if they are outfitting a Truck, SUV, or Jeep today."

    elif has_status_request:
        logger.info("Synthesizer [STATUS REDIRECT]: Activating Order Support Persona.")
        vocal_contract = "ROLE: Professional AI Advisor. VOICE: Soft, helpful, and empathetic. TASK: Identify as Sebastian, the AI Design Advisor. Explain that while you help with selection and technical builds, you don't have access to the shipping or customer database. REDIRECT the user to email 'order@example.com' with their order number. Assure them our logistics team will provide a detailed update on their shipment immediately."
    
    elif pivot_category:
        logger.info(f"Synthesizer [SOFT PIVOT]: Activating Pivot for {pivot_category}.")
        vocal_contract = f"ROLE: Premium Design Advisor. TASK: DO NOT DENY availability for {pivot_category}. Acknowledge their interest in the {pivot_category} first. THEN state that while we currently specialize in locating the perfect premium wheels for the build, you can certainly help them find the exact offsets and wide-stance fitment to ensure those {pivot_category} fit perfectly once the rims are selected. ASK what they are driving to start the wheel check."
    elif was_leaded and ("thank" in last_user_msg.lower() or is_affirming):
        logger.info("Synthesizer [LEAD LOCK]: Providing Concierge Closure.")
        vocal_contract = "ROLE: Senior Concierge Advisor. VOICE: Professional, warm, expert. TASK: Provide a polite, final professional closing. Acknowledge their thanks. Confirm you are busy finalizing the technical quote for their specific build and will email it shortly. Do NOT offer more wheels or ask more questions. Just offer a helpful 'I'm on it!' closure."
    elif has_hesitation:
        logger.info("Synthesizer [EMPATHY MODE]: Activating Rule 4 (Objections) Persona.")
        vocal_contract = "ROLE: Empathetic Advisor. TASK: Rule 4 Compliance: Acknowledge budget concern. Provide a side-by-side comparison (Pros/Cons) of the current selection vs. a value alternative. Offer empathy, no pressure."
    else:
        # Standard step-by-step guidance injection
        vocal_contract += f"\nRule 5 guidance: Current Build Stage: {advisor_step}. Help the user feel confident moving to the next step."

    llm = get_llm()
    
    full_content = ""
    async for chunk in llm.astream([
        {"role": "system", "content": SYNTHESIZER_PROMPT}, 
        {"role": "system", "content": f"SUB-CONTRACT: {vocal_contract}"},
        *state["messages"][-6:], 
        {"role": "user", "content": f"FINAL_DATA_PAYLOAD: {json.dumps(enhanced_metadata)}"}
    ]):
        full_content += chunk.content

    # 3. Bookkeeping
    logger.info(f"Turn Complete: Generated {len(full_content.split())} words for user.")
    
    lead_status = state.get("lead_status", {"attempts": 0, "has_email": False, "last_asked_turn": 0}).copy()
    if state.get("customer_email"):
        lead_status["has_email"] = True
    
    if raw_data.get("allow_lead_capture") and action_type != "info":
        lead_status["attempts"] += 1
        lead_status["last_asked_turn"] = state.get("iteration_count", 0)
        logger.info("Sales Logic Update: Incrementing lead capture attempts.")

    return {
        "messages": [AIMessage(content=full_content)],
        "last_action": action_type,
        "lead_status": lead_status,
        "has_email": lead_status["has_email"]
    }
