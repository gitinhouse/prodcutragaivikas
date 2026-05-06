import json
import logging
import re
from langchain_core.messages import AIMessage
from chatbot.graph.state import GraphState
from chatbot.helpers.constants import SAFE_GREETINGS, STATIC_GREETINGS, DomainTypes, STATIC_MESSAGES
import random
from chatbot.helpers.prompts import SYSTEM_CORE_PROMPT, STRATEGY_TEMPLATES, CONTEXT_BLOCK_TEMPLATE, VARIATION_POOLS
from config.llm_config import get_llm

def get_dynamic_variation(category: str, last_response: str = "") -> str:
    """Selects a random variation from the pool, avoiding direct repetition."""
    pool = VARIATION_POOLS.get(category, [])
    if not pool:
        return "I'm here to help with your build. What's on your mind?"
    
    # Filter out the last response to avoid back-to-back repetition
    valid_options = [v for v in pool if v.strip().lower() not in last_response.strip().lower()]
    return random.choice(valid_options if valid_options else pool)

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.synthesizer")

async def synthesizer_node(state: GraphState):
    """
    THE TRUSTED CLOSER V12: Context-Aware Persona.
    Crafts the expert voice based on Phase, Progress, and Strategic Goals.
    """
    phase = state.get("phase", "VEHICLE_COLLECTION")
    cta_intent = state.get("cta_intent", "ask_vehicle")
    full_history = state.get("messages", [])
    last_resp = state.get("last_final_response", "")
    intent = state.get("intent", "")
    
    # 0.5 DATA EXTRACTION (Order Fixed)
    raw_data = state.get("raw_response_data", {})
    action_type = raw_data.get("action", "discovery")
    last_action = state.get("last_action", "")
    debug_info = state.get("debug_info", {})
    
    # 1. ZERO-LATENCY GREETING & HELP OVERRIDES
    user_query = state.get("sanitized_input", "").lower()
    is_help_query = bool(re.search(r"^(how can you help|what can you do|help me|how it works)$", user_query.strip()))
    
    if cta_intent == "greeting":
        res = get_dynamic_variation("greeting", last_resp)
        return {
            "last_action": "info",
            "final_response": res,
            "last_final_response": res,
            "products": []
        }

    if cta_intent == "help_request" or is_help_query:
        res = get_dynamic_variation("help_request", last_resp)
        return {
            "last_action": "info",
            "final_response": res,
            "last_final_response": res,
            "products": []
        }

    # 2. FORMAT PRODUCT DATA
    products = raw_data.get("products", [])
    product_info = raw_data.get("product_info", {})
    
    # Force high-precision data injection for product details
    data_context = ""
    if product_info:
        data_context = f"""
        [TECHNICAL DATA LOCK - DO NOT ALTER]
        PRODUCT_NAME: {product_info.get('marketing_name')}
        UNIT_PRICE: ${product_info.get('price')}
        CURRENT_INVENTORY: {product_info.get('stock')} units in stock
        UNIQUE_SKU: {product_info.get('sku')}
        WHEEL_SPECS: {product_info.get('diameter')}x{product_info.get('width')}, Bolt Pattern {product_info.get('bolt_pattern')}, Offset {product_info.get('offset')}
        [END DATA LOCK]
        """
    stock_confirmed = raw_data.get("stock_confirmed", False)
    
    formatted_products = ""
    # FORCE SPEC SHEET IF WE HAVE PRODUCT INFO
    if product_info:
        formatted_products = (
            f"WHEEL SPEC SHEET:\n"
            f"- Brand: {product_info.get('brand_name')}\n"
            f"- Model: {product_info.get('name')}\n"
            f"- Price: ${product_info.get('price')}\n"
            f"- Stock: {product_info.get('stock')} in stock\n"
            f"- Specs: {product_info.get('diameter')}x{product_info.get('width')}, {product_info.get('bolt_pattern')}, Offset {product_info.get('offset')}\n"
            f"- SKU: {product_info.get('sku')}\n"
            f"- Details: {product_info.get('ai_summary', 'Premium technical fitment.')}"
        )
    elif products:
        # We no longer list products in the text bubble to avoid redundancy with visual cards.
        # We just provide a summary count for the LLM's context.
        formatted_products = f"SUMMARY: {len(products)} curated matches are being displayed as visual cards."
    else:
        formatted_products = "[INFO] State: " + debug_info.get("reason", "Standard flow")

    # 3. ASSEMBLY & IMPLICIT PROGRESS
    vehicle_context = state.get("vehicle_context", {})
    vehicle_make = vehicle_context.get("make") or "your vehicle"
    vehicle_name = f"{vehicle_context.get('year','')} {vehicle_make} {vehicle_context.get('model','')}".strip()
    
    # Implicit Progress Language
    progress_phrase = random.choice(VARIATION_POOLS["implicit_progress"]).format(vehicle_make=vehicle_make)
    
    strategy_text = STRATEGY_TEMPLATES.get(cta_intent, STRATEGY_TEMPLATES["clarify"])
    
    if cta_intent == "ask_vehicle":
        known_parts = []
        if vehicle_context.get("year"): known_parts.append(str(vehicle_context.get("year")))
        if vehicle_context.get("make"): known_parts.append(vehicle_context.get("make"))
        if vehicle_context.get("model"): known_parts.append(vehicle_context.get("model"))
        
        if known_parts:
            known_str = " ".join(known_parts)
            strategy_text = f"The user provided partial vehicle info: {known_str}. Dynamically acknowledge this (e.g. 'Got it 👍 {known_str} is a great choice') and ask for the missing Year/Make/Model to ensure perfect fitment."
    

    context_block = CONTEXT_BLOCK_TEMPLATE.format(
        strategy_text=strategy_text,
        vehicle_type=vehicle_name,
        vehicle_make=vehicle_make,
        vehicle_model=vehicle_context.get("model") or "the vehicle",
        sales_stage=state.get("sales_stage", "discovery"),
        customer_name=state.get("customer_name") or "valued customer",
        customer_contact=state.get("customer_email") or state.get("has_email") or "Not on file",
        stock_confirmed=str(stock_confirmed),
        total_results=raw_data.get("total_results", 0),
        shown_results=len(products),
        last_response=last_resp,
        relaxation_trace=", ".join(raw_data.get("relaxation_steps", [])) if raw_data.get("relaxation_steps") else "None",
        resolved_product=state.get("resolved_product") or "None",
        target_sku=state.get("target_sku") or "None",
        validation_status=raw_data.get("validation_status", "None"),
        validation_notes=raw_data.get("validation_notes", "None"),
        summary=state.get("summary") or "Conversation just started.",
        product_data=formatted_products
    )
    
    # 4. LLM INVOCATION
    full_system_prompt = f"{SYSTEM_CORE_PROMPT}\n\n{data_context}\n\n{context_block}\nPROGRESS STATUS: {progress_phrase}"
    synth_history = full_history[-4:] if len(full_history) > 4 else full_history
    
    llm = get_llm()
    full_content = ""
    async for chunk in llm.astream([
        {"role": "system", "content": full_system_prompt},
        *synth_history
    ]):
        full_content += chunk.content

    # 5. STRATEGIC OVERRIDES (Hardening)
    final_output = full_content.strip()

    # A. RE-ENGAGEMENT HOOK & BRAND IDENTITY
    is_brand_query = bool(re.search(r"\b(extreme wheels|extreme performance|who are you|represent)\b", user_query.lower()))
    
    if is_brand_query:
        brand_blurb = "I represent Extreme Wheels as your virtual wheel recommendation assistant. We specialize in aftermarket wheels for a wide range of vehicles, making it easy for you to get the right set of wheels and tires. Our online catalog has it all: custom rim and tire packages, factory wheel packages, alloy/forged rims, and accessories. We will beat ALL competitors' prices on any car, truck, or SUV wheels!"
        if brand_blurb.lower() not in final_output.lower():
            final_output = f"{brand_blurb}\n\n{final_output}"

    if raw_data.get("apply_reengagement") and products:
        hook = random.choice(VARIATION_POOLS["reengagement_hook"]).format(vehicle_make=vehicle_make)
        final_output = f"{final_output}\n\n{hook}"
    
    # B. PHANTOM MENTION PROTECTION
    # If the LLM uses 'Check out these setups' or similar but products is empty, strip it.
    if not products:
        phantom_phrases = ["Check out these setups", "here are the options", "take a look at these", "I've pulled some options", "Check out this selection"]
        for phrase in phantom_phrases:
            if phrase.lower() in final_output.lower():
                 # Replace with a more accurate research-phase phrase
                 final_output = re.sub(re.escape(phrase), "I'm researching the perfect matches for your build", final_output, flags=re.IGNORECASE)

    # B. INTENT ENFORCEMENT
    user_query = state.get("sanitized_input", "").lower()
    is_short_ack = len(user_query.split()) <= 2 and bool(re.search(r"^(ok|cool|nice|good|thanks|yep|yeah|fine)$", user_query.strip()))
    
    if intent == "needs_clarity" or action_type == "pattern_mismatch":
        if action_type == "pattern_mismatch":
            final_output = f"I have exceptional options in that bolt pattern, but they won't fit your {vehicle_make} {vehicle_model}. Technical fitment is our priority—should we stick with the verified matches for your car, or are we working on a different vehicle?"
        else:
            # Schema-Locked Cross Question
            final_output = f"I found some great options for your {vehicle_make}, but I want to narrow them down to your perfect style. Do you have a preferred finish like Black or Silver, or a specific wheel size in mind?"
            
    elif is_short_ack and last_action == "recommend" and state.get("view_count", 0) > 0:
        # Prevent 'OK' Trap (Progressive CTA)
        final_output = f"Excellent choice. Since these are verified for your {vehicle_make}, would you like to see the pricing details, or should we look at a different finish?"
        
    elif cta_intent == "ask_style":
        final_output = "What are you looking for today?\n• Style upgrade\n• Off-road wheels\n• Performance\n• Just exploring"
    elif cta_intent == "ask_lead_info":
        final_output = f"Excellent choice. To finalize your technical quote for the {state.get('resolved_product', 'wheels')}, please provide your **Name** and **Email address**. I will send the formal fitment guarantee directly to your inbox."
    elif cta_intent == "safe_fallback":
        final_output = "I want to ensure your build is perfect. Would you like to continue looking at wheel options for your vehicle, or do you have a specific technical question?"
    elif cta_intent == "close":
        final_output = f"Excellent choice. I've generated your formal technical quote for the {state.get('resolved_product')} and sent it to your email. You should receive it shortly. Would you like to explore other wheel finishes for your {vehicle_make}, or is there anything else I can assist you with today?"
    elif cta_intent == "final_thank_you":
        final_output = f"You're very welcome! It was a pleasure helping you perfect the build for your {vehicle_make}. Your formal quote is in your inbox—feel free to reach out if you have any follow-up questions. Enjoy your new setup!"
    elif cta_intent == "break_loop_with_guidance":
        final_output = f"I've shared quite a few styles! To simplify things, I can narrow this down to the top 3 best-selling options for your {vehicle_make} that I know are in stock. Would you like me to do that?"

    
    # 6. UI DUPLICATION PREVENTION
    # Do not re-render the LARGE card grid if we are just purchasing or asking follow-up fitment/info questions
    # about already displayed products.
    is_follow_up = intent in ["fitment_check", "info_request", "product_detail"] and last_action in ["recommend", "recommendation"]
    if intent == "purchase_intent" or cta_intent in ["ask_lead_info", "confirm_order_on_file"] or is_follow_up:
        products = []

    return {
        "last_action": action_type if action_type != "pattern_mismatch" else "info",
        "final_response": final_output,
        "last_final_response": final_output,
        "products": products, # Pass raw product list for UI rendering
        "has_vehicle": bool(state.get("vehicle_make") and state.get("vehicle_model"))
    }

