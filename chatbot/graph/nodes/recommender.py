import logging
import re
from chatbot.graph.state import GraphState
from chatbot.services.product_service import ProductService
from chatbot.helpers.fitment_guard import FitmentGuard

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.recommender")

async def recommender_node(state: GraphState):
    """
    Expert Recommendation Node V9.
    Implements Filter Persistence and Phase-Aware Candidate Generation.
    """
    # 0. INGRESS
    phase = state.get("phase", "VEHICLE_COLLECTION")
    intent = state.get("intent", "")
    shown_products = state.get("shown_products", [])
    rejected_products = state.get("rejected_products", [])
    resolved_product = state.get("resolved_product")
    
    vehicle_context = state.get("vehicle_context", {})
    make = vehicle_context.get("make")
    model = vehicle_context.get("model")
    year = vehicle_context.get("year")
    
    # 1. SOFT GUARD: Missing Vehicle
    if phase == "VEHICLE_COLLECTION":
        logger.info(f"Recommender: Missing vehicle info. Showing featured options while asking for vehicle.")
        featured_wheels = await ProductService.universal_search(query_text="popular wheels", limit=3)
        return {
            "raw_response_data": {
                "action": "discovery", 
                "total_results": len(featured_wheels), 
                "products": featured_wheels
            },
            "has_valid_results": len(featured_wheels) > 0
        }

    # 1.5 PRODUCT DETAIL RESOLUTION
    if intent == "product_detail" and resolved_product:
        logger.info(f"Recommender: Fetching technical details for {resolved_product}")
        # Search explicitly for this product by name to get full specs
        detail_results = await ProductService.search_products(
            vehicle_context=vehicle_context,
            filters={"style": resolved_product}, # Use name as style filter for targeted lookup
            limit=1
        )
        product_detail = detail_results.get("products", [])[0] if detail_results.get("products") else None
        
        if product_detail:
            return {
                "raw_response_data": {
                    "action": "product_detail",
                    "product_info": product_detail,
                    "products": [product_detail]
                },
                "has_valid_results": True,
                "resolved_product": resolved_product
            }
        else:
            logger.warning(f"Recommender: Detail lookup failed for {resolved_product}")

    # 2. INVENTORY CHECK (PURCHASE Phase)
    if phase == "PURCHASE" and resolved_product:
        logger.info(f"Recommender: Performing LIVE inventory check for {resolved_product}")
        stock_status = await ProductService.check_inventory_status(resolved_product)
        if stock_status.get("is_available"):
            return {
                "raw_response_data": {
                    "action": "recommend",
                    "products": [stock_status["product"]],
                    "stock_confirmed": True
                },
                "has_valid_results": True
            }
        else:
            return {
                "raw_response_data": {
                    "action": "out_of_stock",
                    "original_product": resolved_product
                },
                "has_valid_results": False
            }

    # 3. FILTER CONTEXT (Persistence Layer)
    # Combine extracted entities with persistent session filters
    active_filters = state.get("active_filters", {})
    entities = state.get("extracted_entities", {})
    
    search_entities = {**active_filters, **entities}
    # Security: Ensure year/make/model from context override any extracted typos
    search_entities.update({
        "vehicle_year": year,
        "vehicle_make": make,
        "vehicle_model": model
    })

    # 4. SEARCH EXECUTION
    # This high-level API handles fitment, additional filters, and relaxation internally.
    results = await ProductService.search_products(
        vehicle_context=vehicle_context,
        filters=search_entities,
        exclude=shown_products + rejected_products,
        limit=5
    )
    
    products = results.get("products", [])
    total_results = results.get("total_results", 0)
    
    # 5. VIEW TRACKING
    new_view_count = state.get("view_count", 0)
    if len(products) > 0:
        new_view_count += 1
    
    # 6. ACTION RESOLUTION
    action = "recommend" if products else "no_fitment_found"
    user_query = state.get("sanitized_input", "").lower()
    has_explicit_pattern = bool(re.search(r"\d+x\d+\.?\d*", user_query))
    
    if not products and has_explicit_pattern:
        action = "pattern_mismatch"
        logger.warning(f"Recommender: Explicit pattern request {user_query} mismatch for {make} {model}")
        
    # Append to persistence list
    new_shown = list(shown_products)
    for p in products:
        m_name = p.get('marketing_name')
        if m_name and m_name not in new_shown:
            new_shown.append(m_name)

    return {
        "raw_response_data": {
            "action": action,
            "products": products,
            "total_results": total_results,
            "validation_status": results.get("validation_status"),
            "relaxation_steps": results.get("relaxation_steps")
        },
        "shown_products": new_shown,
        "view_count": new_view_count,
        "has_valid_results": len(products) > 0
    }
