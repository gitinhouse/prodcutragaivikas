import logging
from chatbot.graph.state import GraphState
from chatbot.helpers.prompts import RECOMMENDER_PROMPT
from chatbot.services.product_service import ProductService

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.recommender")

async def recommender_node(state: GraphState):
    """
    Expert Recommendation Node.
    Hardened for strict Fitment table relational matching and hard gating.
    """
    entities = state.get("extracted_entities", {})
    vehicle_context = state.get("vehicle_context", {})
    query_text = state.get("last_user_query", "")
    
    # 1. HARD GUARD: Reject eager dumps if required context is missing.
    make = vehicle_context.get("make")
    model = vehicle_context.get("model")
    year = vehicle_context.get("year")
    budget = entities.get("budget_max")
    style = entities.get("style") or entities.get("usage")
    
    if not all([make, model, year, budget, style]):
        logger.warning(f"Recommender: Missing strict context (Make:{make}, Budget:{budget}, Style:{style}). Bouncing.")
        return {
            "raw_response_data": {
                "action": "reply",
                "instruction": "The system bounced the recommendation because the vehicle details (year/make/model), budget, or style preference was missing. Ask the user politely to narrow down whatever is missing so you can look up exact fitments.",
                "allow_lead_capture": False
            }
        }
    
    # 2. STRICT RELATIONAL MATCHING
    logger.info(f"Recommender: Requesting explicit fitment for {year} {make} {model}")
    results = await ProductService.get_wheels_by_fitment(
        make=make,
        model=model,
        year=int(year),
        limit=4
    )
    
    # Optional Semantic Fallback if no strict fitments found
    if not results:
        logger.info("Recommender: Strict fitment yielded 0 results. Firing universal search fallback.")
        results = await ProductService.universal_search(
            query_text=query_text,
            entities={
                "vehicle_type": vehicle_context.get("type"),
                "usage": style,
                "budget_max": budget,
            },
            limit=4
        )
    
    logger.info(f"Recommender: Search returned {len(results)} matches.")
    
    # 3. CONSTRUCT PAYLOAD
    recommended_metadata = results if results else []
    recommended_names = [p["marketing_name"] for p in results] if results else []
    
    return {
        "raw_response_data": {
            "action": "recommend",
            "products": recommended_metadata,
            "instruction": RECOMMENDER_PROMPT,
            "allow_lead_capture": True if results else False
        },
        "recommended_products": recommended_names,
        "recommended_products_metadata": recommended_metadata
    }

