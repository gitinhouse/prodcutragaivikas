import logging
import json
import re
from chatbot.graph.state import GraphState, Intent
from chatbot.helpers.constants import SAFE_GREETINGS, WHEEL_KEYWORDS
from chatbot.helpers.prompts import CONTROLLER_PROMPT
from chatbot.services.cache_service import CacheService
from config.llm_config import get_llm

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.controller")

async def controller_node(state: GraphState):
    """
    SUPER-NODE 2: Strategic Intent Classifier & Optimizer.
    Hardened for Domain Resilience (Memory Awareness) and False-Positive Refusal prevention.
    """
    user_query = state.get("last_user_query", "").strip()
    prev_domain = state.get("domain", "wheels") # Default to wheels if unknown
    entities = state.get("extracted_entities", {})
    
    # 0. THE CORE SALES SAFETY-NET (Prevent False Refusals & Memory Awareness)
    # If the user is talking about 'brands', 'help', 'recommendations', or says 'yes/please', it's ALWAYS wheels.
    sales_affirmations = ["yes", "please", "recommendation", "show", "give", "tell", "more", "look", "sure", "okay", "alright", "yeah", "ok"]
    purchase_signals = ["buy", "purchase", "order", "checkout", "quote", "price on", "how much for"]
    catalog_keywords = ["brand", "catalog", "help", "list", "manufactur", "wheel", "rim"]
    
    is_affirming = any(k in user_query.lower() for k in sales_affirmations)
    is_buying = any(k in user_query.lower() for k in purchase_signals)
    has_catalog_keyword = any(k in user_query.lower() for k in catalog_keywords)

    # 0.1 PII EXTRACTION & REDACTION (Secure Lead Capture)
    email_regex = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    name_patterns = [
        r"(?i)my name is\s+([a-zA-Z\s]+)",
        r"(?i)i am\s+([a-zA-Z\s]+)",
        r"(?i)this is\s+([a-zA-Z\s]+)",
    ]
    
    # --- Extraction ---
    found_emails = re.findall(email_regex, user_query)
    extracted_email = found_emails[0] if found_emails else None
    
    extracted_name = None
    for pattern in name_patterns:
        match = re.search(pattern, user_query)
        if match:
            extracted_name = match.group(1).strip().split('\n')[0] # Clean up name
            break

    # --- Redaction (Sanitization) ---
    sanitized_query = user_query
    if extracted_email:
        sanitized_query = re.sub(email_regex, "[EMAIL_CAPTURED]", sanitized_query)
    if extracted_name:
        # We redact only the name part to avoid breaking the sentence structure
        sanitized_query = sanitized_query.replace(extracted_name, "[NAME_CAPTURED]")

    # Check if we were already in a lead capture attempt
    was_leaded = state.get("lead_status", {}).get("attempts", 0) > 0
    has_existing_email = bool(state.get("customer_email"))

    # 0.2 BUDGET, HESITATION & STATUS SIGNALS (Empathy Guard)
    hesitation_signals = ["budget", "price", "too much", "expensive", "costly", "afford", "cheaper"]
    status_signals = ["where is", "track", "status", "check my", "order status", "receive", "received", "haven't got", "did not get"]
    meta_signals = ["updated", "current", "latest", "data", "database", "inventory list", "what brands", "what do you have"]
    pivot_signals = {
        "tires": ["tire", "rubber", "nitto", "suretrac", "michelin", "toyo", "recon grappler", "275/40", "225/70"],
        "lift_kits": ["lift", "leveling", "rough country", "suspension", "spacers", "headers", "subaru wrx", "fa20"]
    }
    
    has_hesitation = any(k in user_query.lower() for k in hesitation_signals)
    has_status_request = any(k in user_query.lower() for k in status_signals)
    has_meta_request = any(k in user_query.lower() for k in meta_signals)
    
    detected_pivot = None
    for category, keywords in pivot_signals.items():
        if any(k in user_query.lower() for k in keywords):
            detected_pivot = category
            break

    # Numerical Budget Extraction (e.g. "under 400", "budget is 2000")
    budget_match = re.search(r'(?:budget|under|cap|max|around)\s*(?:\$)?\s*(\d{3,5})', user_query.lower())
    extracted_budget = float(budget_match.group(1)) if budget_match else None

    # 0.3 SALES STAGE PROGRESSION
    from chatbot.models import AgentSession
    from chatbot.services.vehicle_service import VehicleService
    
    current_stage = state.get("sales_stage", AgentSession.Stage.DISCOVERY)
    adv_history = state.get("advisor_history", [])
    vehicle_context = state.get("vehicle_context", {})
    
    vehicle_match = VehicleService.resolve_vehicle(user_query)
    if vehicle_match:
        vehicle_context.update(vehicle_match)
    
    # Progress steps based on what entities we have
    if current_stage == AgentSession.Stage.DISCOVERY and (entities.get("vehicle_type") or vehicle_context or "truck" in user_query.lower() or "suv" in user_query.lower()):
        current_stage = AgentSession.Stage.FITMENT_VALIDATION
    elif current_stage == AgentSession.Stage.FITMENT_VALIDATION and (len(entities) > 1 or extracted_budget):
        current_stage = AgentSession.Stage.READY_TO_RECOMMEND
        
    if current_stage not in adv_history:
        adv_history.append(current_stage)

    # PURCHASE LOCK: If they want to buy or just provided an email/name, lock the intent
    # BUT: If they show hesitation OR ask about status OR tire/lift pivot OR meta-data, we BREAK the lock.
    if (is_buying or extracted_email or extracted_name or (was_leaded and is_affirming)) and not has_hesitation and not has_status_request and not detected_pivot and not has_meta_request:
        logger.info(f"Controller [SALES LOCK]: Purchase Intent detected.")
        
        # Update messages history with sanitized content for privacy
        messages = state.get("messages", [])
        if messages and sanitized_query != user_query:
            messages[-1].content = sanitized_query

        # Prepare merged entities for the state
        final_entities = entities.copy()
        if extracted_budget:
            final_entities["budget_max"] = extracted_budget
            
        current_stage = AgentSession.Stage.CLOSING

        return {
            "intent": Intent.PURCHASE_INTENT if not has_hesitation else Intent.HESITANT,
            "domain": "wheels",
            "last_user_query": sanitized_query,
            "messages": messages,
            "extracted_entities": final_entities,
            "customer_email": extracted_email if extracted_email else state.get("customer_email"),
            "customer_name": extracted_name if extracted_name else state.get("customer_name"),
            "sales_stage": current_stage,
            "advisor_history": adv_history,
            "vehicle_context": vehicle_context,
            "muzzle_response": False,
            "is_greeting": False
        }

    # DOMAIN LOCKING: If we are already in 'wheels' domain and the user says 'yes please', STAY in wheels.
    if prev_domain == "wheels" and is_affirming:
        logger.info(f"Controller [DOMAIN LOCK]: Stay in wheels for affirmative query: '{user_query}'")
        # Pre-emptive return for very short affirmations to avoid AI classification noise
        if len(user_query.split()) <= 4:
            # LEAD LOCK: If we already have their info, don't trigger a new search on 'thanks'
            final_intent = Intent.PRODUCT_QUERY if not was_leaded else Intent.INFO_REQUEST
            
            return {
                "intent": final_intent,
                "domain": "wheels",
                "extracted_entities": entities, # PRESERVE ENTITIES for relaxation
                "sales_stage": current_stage,
                "advisor_history": adv_history,
                "vehicle_context": vehicle_context,
                "muzzle_response": False,
                "is_greeting": False
            }

    if has_catalog_keyword:
        logger.info(f"Controller: Catalog keyword detected. Forcing wheel domain.")
        state["domain"] = "wheels"

    # 1. THE GREETING BYPASS (Persona Polishing)
    # Aggressively normalized query for greeting check
    clean_query = re.sub(r'[^a-zA-Z]', '', user_query.lower()).strip()
    logger.info(f"Controller: Normalized Query for Greeting Check: '{clean_query}'")
    
    if clean_query in SAFE_GREETINGS:
        logger.info(f"Controller [BYPASS HIT]: PURE GREETING detected for '{user_query}'. Bypassing AI.")
        return {
            "intent": Intent.NEEDS_CLARITY,
            "domain": "wheels",
            "extracted_entities": {},
            "vehicle_context": vehicle_context,
            "muzzle_response": False,
            "is_greeting": True
        }
    else:
        logger.info(f"Controller [BYPASS MISS]: No greeting match for '{clean_query}'")

    # 2. STRATEGIC CACHE LAYER
    cache_key = f"v3_intent_{user_query.lower().replace(' ', '_')}"
    cached_result = await CacheService.get(cache_key)
    if cached_result:
        logger.info(f"Controller: STRATEGIC CACHE HIT for '{user_query}'")
        return cached_result

    # 3. AI CLASSIFICATION TRACK
    logger.info(f"Controller: STRATEGIC CACHE MISS: Invoking AI Classifier for '{user_query}'")
    
    llm = get_llm().with_structured_output({
        "title": "ControllerOutput",
        "type": "object",
        "properties": {
            "intent": {"enum": [i.value for i in Intent]},
            "domain": {"enum": ["wheels", "out_of_scope"]},
            "product_type": {"type": "string"},
            "confidence": {"type": "number"},
            "attributes": {"type": "object"}
        },
        "required": ["intent", "confidence", "domain"]
    })
    
    try:
        result = await llm.ainvoke([
            {"role": "system", "content": CONTROLLER_PROMPT},
            {"role": "user", "content": f"CONVERSATION_CONTEXT: Domain is currently {prev_domain}. USER_QUERY: {user_query}"}
        ])
        
        # Mapping attributes to extracted_entities
        attrs = result.get("attributes", {})
        entities = {
            "brand": attrs.get("brand"),
            "size": attrs.get("size"),
            "bolt_pattern": attrs.get("bolt_pattern"),
            "vehicle_type": attrs.get("vehicle_type"),
            "style": attrs.get("style")
        }
        entities = {k: v for k, v in entities.items() if v}
        
        # LLM Vehicle Extraction Fallback (If Fuzzy Matcher missed it)
        if not vehicle_context.get("make") and attrs.get("vehicle_make"):
            vehicle_context["make"] = str(attrs.get("vehicle_make")).title()
        if not vehicle_context.get("model") and attrs.get("vehicle_model"):
            vehicle_context["model"] = str(attrs.get("vehicle_model")).title()
        if not vehicle_context.get("year") and attrs.get("vehicle_year"):
            try:
                vehicle_context["year"] = int(attrs.get("vehicle_year"))
            except ValueError:
                pass

        logger.info(f"AI Classification SUCCESS: Intent={result.get('intent')} | Domain={result.get('domain')}")
        
        # Determine domain: Pivots are still technically 'in scope' for the advisor but marked for soft-pivot.
        final_domain = result.get("domain", "wheels")
        if detected_pivot:
            final_domain = "wheels" # Keep in wheels domain so the advisor can help with fitment
            
        # Merge budget with AI-extracted entities
        if extracted_budget:
            entities["budget_max"] = extracted_budget
            
        # Merge with pre-existing entities from previous turns
        merged_entities = state.get("extracted_entities", {}).copy()
        merged_entities.update(entities)

        final_state = {
            "intent": Intent(result.get("intent", "needs_clarity")) if not has_hesitation else Intent.HESITANT,
            "domain": final_domain,
            "extracted_entities": merged_entities,
            "detected_violation_category": detected_pivot,
            "sales_stage": current_stage,
            "advisor_history": adv_history,
            "vehicle_context": vehicle_context,
            "muzzle_response": True if result.get("domain") == "out_of_scope" and not detected_pivot else False,
            "is_greeting": False
        }
        
        await CacheService.set(cache_key, final_state, timeout=3600)
        return final_state
        
    except Exception as e:
        logger.error(f"Controller CRITICAL FAILURE: {str(e)}")
        return {"intent": Intent.NEEDS_CLARITY, "domain": "wheels"}
