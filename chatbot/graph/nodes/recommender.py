import logging
import re
from chatbot.graph.state import GraphState
from chatbot.services.product_service import ProductService

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.recommender")

async def recommender_node(state: GraphState):
    import re
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
    entities = state.get("extracted_entities", {})
    target_sku = state.get("target_sku")
    has_search_trigger = any(entities.get(k) for k in ["brand", "style", "wheel_brand", "finish", "sku"]) or bool(target_sku)
    
    if phase == "VEHICLE_COLLECTION" and not has_search_trigger:
        logger.info(f"Recommender: Missing vehicle info and no search trigger. No products shown yet.")
        return {
            "raw_response_data": {
                "action": "discovery", 
                "total_results": 0, 
                "products": []
            },
            "has_valid_results": False
        }

    # 1.5 PRODUCT DETAIL RESOLUTION
    # FORCE INTENT if SKU is directly provided from frontend or controller
    if target_sku:
        intent = "product_detail"
        sku = target_sku.replace("#", "").strip() # Clean up any accidental hashes
    else:
        sku = entities.get("sku")
    
    if intent == "product_detail":
        # Absolute Direct Lookup Layer
        product_detail = None
        
        # A. Try SKU first (Multi-Strategy)
        if sku:
            sku = sku.strip()
            from chatbot.models import WheelProduct
            from asgiref.sync import sync_to_async
            # 1. Exact Match
            product_detail = await sync_to_async(
                lambda: WheelProduct.objects.filter(sku__iexact=sku).first(),
                thread_sensitive=False
            )()
            
            # 2. Contains Fallback (Sanity Check)
            if not product_detail:
                product_detail = await sync_to_async(
                    lambda: WheelProduct.objects.filter(sku__icontains=sku).first(),
                    thread_sensitive=False
                )()
        
        # B. Try exact Name fallback
        if not product_detail and resolved_product:
            from chatbot.models import WheelProduct
            from asgiref.sync import sync_to_async
            product_detail = await sync_to_async(
                lambda: WheelProduct.objects.filter(product_name__iexact=resolved_product).first(),
                thread_sensitive=False
            )()

        logger.info(f"Recommender: Precision lookup for SKU={sku} result: {'FOUND' if product_detail else 'MISSING'}")

        if product_detail:
            primary_product = ProductService._serialize_product(product_detail)
            is_oos = primary_product.get("stock", 0) <= 0
            
            logger.info(f"Recommender: SKU found {sku}. Stock={primary_product.get('stock')}. Fetching alternatives.")
            
            # --- RESILIENT ALTERNATIVES SEARCH (Only if OOS) ---
            alternatives = []
            if is_oos:
                logger.info(f"Recommender: SKU {primary_product['sku']} is OOS. Finding alternatives...")
                
                # Step 1: Strict Match (Size + Pattern + Finish)
                search_filters = {
                    "bolt_pattern": primary_product.get("bolt_pattern"),
                    "size": primary_product.get("diameter"),
                    "finish": primary_product.get("finish")
                }
                similar_results = await ProductService.search_products(
                    vehicle_context=vehicle_context,
                    filters=search_filters,
                    exclude=[primary_product["sku"]],
                    limit=3
                )
                alternatives = similar_results.get("products", [])

                # Step 2: Relax Finish (Size + Pattern)
                if len(alternatives) < 3:
                    logger.info("Recommender: Relaxing finish constraint for alternatives...")
                    relaxed_filters = {k: v for k, v in search_filters.items() if k != "finish"}
                    more_results = await ProductService.search_products(
                        vehicle_context=vehicle_context,
                        filters=relaxed_filters,
                        exclude=[primary_product["sku"]] + [p["sku"] for p in alternatives],
                        limit=3 - len(alternatives)
                    )
                    alternatives.extend(more_results.get("products", []))

                # Step 3: Global Size Match (Size only)
                if len(alternatives) < 3:
                    logger.info("Recommender: Relaxing bolt pattern for alternatives...")
                    global_filters = {"size": primary_product.get("diameter")}
                    global_results = await ProductService.search_products(
                        vehicle_context=vehicle_context,
                        filters=global_filters,
                        exclude=[primary_product["sku"]] + [p["sku"] for p in alternatives],
                        limit=3 - len(alternatives)
                    )
                    alternatives.extend(global_results.get("products", []))

            # --- FINAL SELECTION ---
            display_products = []
            if not is_oos:
                display_products.append(primary_product)
            
            display_products.extend(alternatives)
            final_selection = display_products[:3]
            
            # Track shown products to avoid duplicates
            new_shown = list(shown_products)
            for p in final_selection:
                p_sku = p.get('sku')
                if p_sku and p_sku not in new_shown:
                    new_shown.append(p_sku)

            return {
                "raw_response_data": {
                    "action": "recommend",
                    "product_info": primary_product,
                    "products": final_selection,
                    "target_sku_oos": is_oos
                },
                "shown_products": new_shown,
                "has_valid_results": len(final_selection) > 0,
                "resolved_product": primary_product["marketing_name"]
            }
        else:
            logger.warning(f"Recommender: SKU lookup failed for {sku}. Falling through to search.")

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
        limit=3
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
        
    # Append to persistence list (Track by SKU for precision exclusion)
    new_shown = list(shown_products)
    for p in products:
        p_sku = p.get('sku')
        if p_sku and p_sku not in new_shown:
            new_shown.append(p_sku)

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
