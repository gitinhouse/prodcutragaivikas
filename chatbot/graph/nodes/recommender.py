import logging
from chatbot.graph.state import GraphState
from chatbot.helpers.prompts import RECOMMENDER_PROMPT
from chatbot.services.product_service import ProductService

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.recommender")

async def recommender_node(state: GraphState):
    """
    Expert Recommendation Node.
    Hardened for Technical Fitment, Usage Retrieval, and Variety Shuffle.
    """
    entities = state.get("extracted_entities", {})
    query_text = state.get("last_user_query", "")
    prev_metadata = state.get("recommended_products_metadata", [])
    
    # VARIETY SHUFFLE: Collect previously shown IDs to avoid 'Same Answer' loops
    exclude_ids = [str(p.get("id")) for p in prev_metadata if p.get("id")] if prev_metadata else []
    
    # 1. EXTRACT FILTERS
    diameter = entities.get("size")
    max_price = entities.get("budget_max")
    brand = entities.get("brand")
    bolt_pattern = entities.get("bolt_pattern")
    vehicle_type = entities.get("vehicle_type")
    usage = entities.get("usage") or entities.get("style", "")
    
    # Check if this turn is a style refinement (e.g. 'off-road', 'rugged')
    is_refinement = any(k in query_text.lower() for k in ["off-road", "rugged", "trail", "different", "other", "more"])
    
    # 2. CALL UNIVERSAL SEARCH ENGINE
    logger.info(f"Recommender: Universal Search (v_type={vehicle_type}, usage={usage}, shuffle={is_refinement})")
    
    # If it's a refinement, we use the shuffle; otherwise, we allow the best matches (even if repeat)
    results = await ProductService.universal_search(
        query_text=query_text,
        entities={
            "size": diameter,
            "bolt_pattern": bolt_pattern,
            "brand": brand,
            "vehicle_type": vehicle_type,
            "usage": usage,
            "budget_max": max_price
        },
        exclude_ids=exclude_ids if is_refinement else None,
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
