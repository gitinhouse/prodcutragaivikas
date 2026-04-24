import json
import logging
import re
from langchain_core.messages import AIMessage
from chatbot.graph.state import GraphState
from chatbot.helpers.constants import SAFE_GREETINGS, STATIC_GREETINGS, DomainTypes, STATIC_MESSAGES
from chatbot.helpers.prompts import SYNTHESIZER_PROMPT_TEMPLATE
from config.llm_config import get_llm

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.synthesizer")

async def synthesizer_node(state: GraphState):
    """
    SUPER-NODE 11: The Trusted Closer.
    Incorporates Live Inventory Status into the expert voice.
    """
    domain = state.get("domain", DomainTypes.IN_SCOPE)
    action_type = state.get("action_type", "discovery")
    cta_intent = state.get("cta_intent", "ask_vehicle")
    sales_stage = state.get("sales_stage", "discovery")
    full_history = state.get("messages", [])
    
    # 1. ZERO-LATENCY GREETING
    is_greeting = state.get("is_greeting", False)
    if is_greeting and len(full_history) <= 1:
        import random
        greeting = random.choice(STATIC_GREETINGS)
        return {"messages": [AIMessage(content=greeting)], "final_response": greeting}

    # 2. FORMAT PRODUCT DATA
    raw_data = state.get("raw_response_data", {})
    products = raw_data.get("products", [])
    product_info = raw_data.get("product_info", {})
    is_relaxed = raw_data.get("is_relaxed_search", False)
    stock_confirmed = raw_data.get("stock_confirmed", False)
    
    formatted_products = ""
    if cta_intent == "product_detail" and product_info:
        # Format spec sheet for detail turn
        formatted_products = (
            f"WHEEL SPEC SHEET:\n"
            f"- Brand: {product_info.get('brand')}\n"
            f"- Model: {product_info.get('name')}\n"
            f"- Inventory Status: {product_info.get('stock')} units available\n"
            f"- Bolt Pattern: {product_info.get('bolt_pattern')}\n"
            f"- Size: {product_info.get('size')}\n"
            f"- Finish: {product_info.get('finish')}\n"
            f"- Price: ${product_info.get('price')}\n"
            f"- Details: {product_info.get('details')}"
        )
    elif products:
        product_lines = []
        for p in products:
            reason = p.get("ai_reason", "Premium fitment")
            stock = p.get("stock", 0)
            price = f"${p.get('price')}" if p.get("price") else "N/A"
            finish = p.get("finish", "Premium")
            pattern = p.get("bolt_pattern", "Verified Fitment")
            product_lines.append(f"- **{p.get('marketing_name')}** | {price} ({stock} in stock)\n  *Specs: {finish} | {pattern} | {reason}*")
        formatted_products = "\n".join(product_lines)
    else:
        if action_type == "no_fitment_found":
            formatted_products = "[FITMENT_CONFLICT] Technical incompatibility."
        else:
            formatted_products = "[NOT_FOUND] No matches."

    # 3. RENDER TEMPLATE
    attrs = state.get("extracted_entities", {})
    vehicle_context = state.get("vehicle_context", {})
    vehicle_name = f"{vehicle_context.get('year','')} {vehicle_context.get('make','')} {vehicle_context.get('model','')}".strip()
    
    full_system_prompt = SYNTHESIZER_PROMPT_TEMPLATE.format(
        cta_intent=cta_intent,
        sales_stage=sales_stage,
        action_type=action_type,
        vehicle_type=vehicle_name if vehicle_name else "your vehicle",
        budget=f"${attrs.get('budget_max')}" if attrs.get("budget_max") else "your budget",
        style=attrs.get("style") or "Not specified",
        resolved_product=state.get("resolved_product") or "None",
        is_relaxed=str(is_relaxed),
        stock_confirmed=str(stock_confirmed),
        product_data=formatted_products,
        presentation_mode="NEW_OPTIONS" if raw_data.get("is_new_recommendation") else "PREVIOUS_RECAP",
        vehicle_make=vehicle_context.get("make") or "your vehicle",
        vehicle_model=vehicle_context.get("model") or "the vehicle",
        customer_name=state.get("customer_name") or "valued customer",
        customer_contact=state.get("customer_email") or state.get("has_email") or "Not on file",
        total_results=raw_data.get("total_results", 0),
        shown_results=raw_data.get("shown_results", 0),
        last_response=state.get("last_final_response", "None")
    )
    
    # 3.5 LOYALTY GUARD: Don't hallucinate "On File" if it's empty
    has_contact = bool(state.get("customer_email") or state.get("has_email"))
    if not has_contact:
        # If we are in 'confirm_order_on_file' but have no email, FORCE back to 'ask_lead_info'
        if cta_intent == "confirm_order_on_file":
            logger.warning("Synthesizer: Redirecting confirm_order_on_file -> ask_lead_info (No contact found)")
            cta_intent = "ask_lead_info"
            full_system_prompt = full_system_prompt.replace("confirm_order_on_file", "ask_lead_info")

    # 4. LLM INVOCATION
    synth_history = full_history[-4:] if len(full_history) > 4 else full_history
    
    llm = get_llm()
    full_content = ""
    async for chunk in llm.astream([
        {"role": "system", "content": full_system_prompt},
        *synth_history
    ]):
        full_content += chunk.content

    # 5. POST-GENERATION ENFORCEMENT
    logger.info(f"Synthesizer: Strategy='{cta_intent}' Products={len(products)} LLM_Length={len(full_content)}")

    # --- REPETITION GUARD (SIMILARITY) ---
    last_resp = state.get("last_final_response", "").lower()
    if last_resp and full_content.lower().strip() == last_resp.strip():
        logger.warning("Synthesizer: Perfect repetition detected. Forcing variation.")
        if cta_intent == "show_options":
            full_content = f"Beyond those styles, we also have {raw_data.get('total_results')} other matches. Are you looking for a specific finish like matte black or silver?"
        elif cta_intent == "ask_vehicle":
             full_content = "To get the technical fitment 100% right, I just need to confirm the year of your vehicle. What year are we outfitting?"
        else:
            full_content = "I'm here to ensure your build is perfect. What other details can I clarify about these options for you?"

    # Strip filler
    filler_patterns = [r"just a moment", r"let me check", r"searching inventory", r"one second"]
    for pattern in filler_patterns:
        full_content = re.sub(pattern, "", full_content, flags=re.IGNORECASE).strip()

    # --- GLOBAL STRATEGY FIREWALL ---
    # 5. HALLUCINATION FIREWALL (CRITICAL)
    # If we have 0 results, nuke any text that tries to use the 'show_options' template.
    if raw_data.get("total_results", 0) == 0:
        zero_results_pattern = r"(?i).*(identified 0|top 0|0 styles|0 options|0 matches).*"
        if re.search(zero_results_pattern, full_content):
            logger.warning("Synthesizer: LLM tried to use results template for 0 results. Nuking.")
            if cta_intent == "ask_vehicle":
                full_content = f"Excellent, a {vehicle_context.get('make', 'BMW')}. To pull the exact fitment specs from our database, could you let me know what year you're driving?"
            else:
                full_output = f"I've checked our expert inventory for the {vehicle_name}. While I didn't find a perfect match for those specific specs, I can suggest some elite alternatives if we adjust the size or brand. What year is your vehicle?"
                full_content = full_output

    # If we are NOT in the closing stage, or we have NO lead info, block purchase/loyalty hallucinations.
    if sales_stage != "closing" or not has_contact:
        hallucination_pattern = r"(?i).*(excellent choice|stock is confirmed|since I have your details|details on file|info on file|sending the quote|quote (is )?on the way).*"
        if re.search(hallucination_pattern, full_content):
            logger.warning(f"Synthesizer: Hallucination detected in stage '{sales_stage}'. Nuking LLM text.")
            if cta_intent == "show_options":
                full_content = f"I've verified the fitment for your {vehicle_name}. Here are some premium options for your build:"
            elif cta_intent == "ask_vehicle":
                full_content = f"I've got a great selection of wheels for your {vehicle_name}. To be 100% sure on fitment, is that the exact model you're outfitting?"
            else:
                full_content = "I'm ready to find your perfect wheels. What specifically are you looking for in terms of style or performance?"

    # --- FINAL ASSEMBLY ---
    # ABSOLUTE INTENT ENFORCEMENT: If the tactical goal is to ask for a vehicle/year,
    # we MUST NOT allow the LLM to talk about results (which would be 0 anyway).
    if cta_intent == "ask_vehicle":
        # Force a professional, helpful recovery based on what we know
        make = vehicle_context.get('make')
        if make:
            final_output = f"Excellent choice on the {make}. To pull the exact technical fitment specs from our database, could you let me know what year you're driving?"
        else:
            final_output = "I'm ready to find the perfect wheels for your build. To get started, what kind of vehicle are we outfitting today?"
    
    elif raw_data.get("total_results", 0) == 0 or "identified 0" in full_content:
        # Fallback for no_results or other failures
        final_output = f"I've checked our expert inventory for the {vehicle_name}. While I didn't find a perfect fitment match for those specific specs, I can suggest some elite alternatives if we adjust the size or brand. What year is your vehicle?"
    else:
        # Normal flow: Use LLM content but ensure it has text
        lines = full_content.strip().split("\n")
        text_lines = [l for l in lines if not l.strip().startswith("-")]
        product_lines = [l for l in lines if l.strip().startswith("-")]
        
        if not text_lines:
             text_lines = [f"I've identified these premium options for your {vehicle_name}:"]
        
        final_output = "\n".join(text_lines[:3]).strip()
        if product_lines:
            final_output += "\n\n" + "\n".join(product_lines)
    
    # --- SAFETY NET: Never return a blank bubble ---
    if not final_output:
        logger.warning(f"Synthesizer: Empty output generated for stage {sales_stage}. Using safety fallback.")
        if cta_intent == "ask_vehicle":
            final_output = "I'm ready to find the perfect wheels for your build. To get started, what kind of vehicle are we outfitting today?"
        elif cta_intent == "show_options":
            final_output = "I've pulled some premium options that match your vehicle's fitment specs. Which of these styles stands out to you?"
        else:
            final_output = "I'm here to ensure your build is perfect. How can I best assist you with your wheel selection today?"

    if product_lines:
        final_output += "\n\n" + "\n".join(product_lines)

    return {
        "messages": [AIMessage(content=final_output)],
        "last_action": action_type,
        "final_response": final_output,
        "last_final_response": final_output
    }
