import re
import json
import logging
from typing import List, Optional, Dict, Any, Union
from django.db.models import Q, Case, When, Value, FloatField
from asgiref.sync import sync_to_async
from pgvector.django import CosineDistance
from chatbot.helpers.config_cache import ConfigCache
from chatbot.models import WheelProduct, VehicleMake, VehicleModel
from .cache_service import CacheService

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.services.product")

class ProductService:
    """
    Universal Hybrid Search Engine (Production 8 Standard).
    Now includes Live Inventory Verification logic.
    """

    @staticmethod
    def _normalize_ref(text: str) -> str:
        return re.sub(r'[^A-Z0-9]', '', text.upper())

    @staticmethod
    def _extract_sku_candidate(text: str) -> Optional[str]:
        # Prioritize Dash-separated patterns or long Alphanumeric strings (8+) before the short (2+3) legacy pattern
        match = re.search(r'([A-Z0-9]+-[A-Z0-9.-]+|[A-Z0-9]{8,}|[A-Z]{2,}[0-9]{3,})', text.upper())
        return match.group(1) if match else None

    @staticmethod
    def _serialize_product(p: WheelProduct) -> Dict[str, Any]:
        # Clean up marketing name to avoid brand repetition
        brand = p.brand_desc.strip()
        name = p.product_name.strip()
        
        if name.lower().startswith(brand.lower()):
            clean_name = name[len(brand):].strip()
        else:
            clean_name = name
            
        # Strip common spec patterns (e.g. 17x8.5, 6x139.7, +0, -18)
        clean_name = re.sub(r'\d+x\d+\.?\d*', '', clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'[+-]?\d+\s+\d+x\d+', '', clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'\d+x\d+', '', clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        marketing_name = f"{brand} {clean_name}"

        # Deterministic Badge Logic
        if p.quantity == 0:
            badge = {"text": "OUT OF STOCK", "bg": "#64748B"}
        elif p.map_usd and p.map_usd > 1200:
            badge = {"text": "⚡ HIGH PERFORMANCE", "bg": "#EF4444"}
        elif "off-road" in (p.product_desc or "").lower() or "terrain" in (p.product_desc or "").lower():
            badge = {"text": "⭐ BEST FOR OFF-ROAD", "bg": "#2563EB"}
        else:
            # Deterministic choice based on SKU to keep it consistent
            import hashlib
            h = int(hashlib.md5(p.sku.encode()).hexdigest(), 16)
            deterministic_badges = [
                {"text": "🔥 MOST POPULAR", "bg": "#10B981"},
                {"text": "💎 PREMIUM PICK", "bg": "#8B5CF6"},
                {"text": "⭐ BEST FOR OFF-ROAD", "bg": "#2563EB"},
                {"text": "⚡ HIGH PERFORMANCE", "bg": "#EF4444"}
            ]
            badge = deterministic_badges[h % len(deterministic_badges)]
        
        bullets = [
            f"Precision {p.diameter}x{p.width} Fitment",
            f"Premium {p.fancy_finish_desc or 'Finish'}",
            "High Load Capacity & Durability"
        ]

        return {
            "id": str(p.id),
            "name": name,
            "brand_name": brand,
            "marketing_name": marketing_name,
            "price": float(p.map_usd) if p.map_usd is not None else 0.0,
            "stock": p.quantity,
            "sku": p.sku,
            "finish": p.fancy_finish_desc,
            "bolt_pattern": p.bolt_pattern_metric,
            "diameter": p.diameter,
            "width": p.width,
            "image_url": p.image_url1,
            "specification": {
                "diameter": p.diameter,
                "width": p.width,
                "finish": p.fancy_finish_desc,
                "bolt_pattern": p.bolt_pattern_metric,
                "offset": p.wheel_offset
            },
            "ai_summary": p.product_desc or "Built for extreme durability and premium styling.",
            "top_badge": badge,
            "bullets": bullets,
            "fitment_text": "Fits your vehicle"
        }

    @staticmethod
    async def check_inventory_status(product_name: str) -> Dict[str, Any]:
        """
        Targeted Real-Time Stock Verification.
        Returns availability status and details.
        """
        logger.info(f"ProductService: Checking inventory for '{product_name}'")
        def _execute():
            # 1. SMART SEARCH: Match by SKU or Name (Strip whitespace for robustness)
            search_term = product_name.strip()
            match = WheelProduct.objects.filter(
                Q(product_name__iexact=search_term) | 
                Q(sku__iexact=search_term) |
                Q(sku__icontains=search_term) |
                Q(product_name__icontains=search_term)
            ).first()
            
            if not match:
                logger.warning(f"ProductService: No match found for '{product_name}' in DB.")
                return {"is_available": False, "status": "Not found"}
            
            is_avail = match.quantity > 0
            res = {
                "is_available": is_avail,
                "product": ProductService._serialize_product(match),
                "status": "In Stock" if is_avail else "Backordered"
            }
            logger.info(f"ProductService: Match found for '{product_name}' -> SKU: {match.sku}, Status: {res['status']}")
            return res
            
        return await sync_to_async(_execute, thread_sensitive=False)()

    @staticmethod
    async def universal_search(
        query_text: str,
        entities: Dict[str, Any],
        query_vector: Optional[List[float]] = None,
        exclude_names: Optional[List[str]] = None,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        known_brands = await ConfigCache.get_wheel_brands()
        
        def _execute_search_logic(known_brands):
            # Prioritize explicit SKU from entities (passed from frontend)
            sku_entity = entities.get("sku")
            if sku_entity:
                sku_match = WheelProduct.objects.filter(sku__iexact=sku_entity).first()
                if sku_match: return [sku_match]

            sku_candidate = ProductService._extract_sku_candidate(query_text)
            if sku_candidate:
                sku_match = WheelProduct.objects.filter(
                    Q(sku__iexact=sku_candidate) | 
                    Q(sku__icontains=sku_candidate)
                ).first()
                if sku_match: return [sku_match]

            queryset = WheelProduct.objects.filter(map_usd__gt=0, quantity__gt=0)
            if exclude_names:
                queryset = queryset.exclude(sku__in=exclude_names).exclude(product_name__in=exclude_names)

            diameter = entities.get("size")
            bolt_pattern = entities.get("bolt_pattern")
            price_max = entities.get("budget_max") or entities.get("price_max")
            
            if diameter:
                try:
                    d_val = float(re.search(r'(\d+)', str(diameter)).group(1))
                    queryset = queryset.filter(diameter=d_val)
                except: pass
            
            if bolt_pattern: queryset = queryset.filter(bolt_pattern_metric__icontains=bolt_pattern)
            if price_max:
                try: queryset = queryset.filter(map_usd__lte=float(price_max))
                except: pass

            finish = entities.get("finish")
            if finish:
                queryset = queryset.filter(
                    Q(fancy_finish_desc__iregex=rf"\b{re.escape(finish)}\b") | 
                    Q(embedding_text__iregex=rf"\b{re.escape(finish)}\b")
                )

            wheel_brand = entities.get("wheel_brand") or entities.get("brand")
            if not wheel_brand:
                for b in known_brands:
                    if b.lower() in query_text.lower():
                        wheel_brand = b
                        break

            if wheel_brand:
                queryset = queryset.filter(brand_desc__icontains=wheel_brand)
                
            usage = entities.get("usage") or entities.get("style", "")
            
            style_boost_terms = ["rugged", "off-road", "trail", "mud", "aggressive", "sport", "luxury"]
            active_style_terms = [t for t in style_boost_terms if t in query_text.lower() or t in usage.lower()]
            
            if active_style_terms:
                when_clauses = [When(embedding_text__icontains=t, then=Value(10.0)) for t in active_style_terms]
                queryset = queryset.annotate(relevance_score=Case(*when_clauses, default=Value(1.0), output_field=FloatField())).order_by('-relevance_score', '-quantity')
            else: 
                queryset = queryset.order_by('-quantity', 'map_usd')

            results = list(queryset.exclude(embedding__isnull=True)[:limit])
            if len(results) >= 1: return results
            
            if query_vector:
                results = list(WheelProduct.objects.exclude(embedding__isnull=True).annotate(distance=CosineDistance("embedding", query_vector)).order_by("distance")[:limit])
                if results: return results
            
            clean_query = " ".join([w for w in query_text.split() if len(w) > 2])
            results = list(WheelProduct.objects.filter(Q(product_name__icontains=clean_query) | Q(embedding_text__icontains=clean_query)).order_by('?')[:limit])
            return results

        raw_results = await sync_to_async(_execute_search_logic, thread_sensitive=False)(known_brands)
        logger.info(f"ProductService: Returning {len(raw_results)} final products: {[p.product_name for p in raw_results]}")
        return [ProductService._serialize_product(p) for p in raw_results]

    @staticmethod
    async def search_products(
        vehicle_context: Dict[str, Any],
        filters: Dict[str, Any],
        exclude: Optional[List[str]] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        HIGH-LEVEL SEARCH API: Fitment-First, Filter-Second.
        """
        make = vehicle_context.get("make")
        model = vehicle_context.get("model")
        year = vehicle_context.get("year")
        
        relaxation_steps = []
        
        # 1. BASE FITMENT FETCH
        # If we have vehicle info, use it as a hard constraint
        if make and model:
            products = await ProductService.get_wheels_by_fitment(
                make=make, model=model, year=year,
                entities=filters, exclude_names=exclude, limit=limit
            )
            # Check if any filtering happened inside get_wheels_by_fitment
            # (Note: get_wheels_by_fitment already does some internal relaxation)
            return {
                "products": products,
                "total_results": len(products),
                "validation_status": "fitment_verified",
                "relaxation_steps": relaxation_steps
            }
        
        # 2. UNIVERSAL SEARCH (If no vehicle)
        products = await ProductService.universal_search(
            query_text=filters.get("style", "premium wheels"),
            entities=filters,
            exclude_names=exclude,
            limit=limit
        )
        return {
            "products": products,
            "total_results": len(products),
            "validation_status": "generic_search",
            "relaxation_steps": relaxation_steps
        }

    @staticmethod
    async def get_wheels_by_fitment(
        make: str, model: str, year: Optional[int] = None, 
        entities: Optional[Dict[str, Any]] = None,
        exclude_names: Optional[List[str]] = None,
        limit: int = 12
    ) -> List[Dict[str, Any]]:
        """
        BRIDGE LOGIC: Resolves vehicle to IDs, fetches precise specs from API, then queries WheelProduct.
        """
        # 0. DIRECT SKU BYPASS (Maximum Precision)
        if entities and entities.get("sku"):
            sku = entities.get("sku")
            logger.info(f"ProductService: Direct SKU lookup triggered for {sku}")
            sku_match = await sync_to_async(
                lambda: WheelProduct.objects.filter(sku=sku).first(),
                thread_sensitive=False
            )()
            if sku_match:
                return [ProductService._serialize_product(sku_match)]

        from chatbot.services.fitment_api_service import FitmentApiService

        def _execute():
            # 1. Resolve IDs from Vehicle Tables
            # We look for the model fitment value that matches the user's model
            v_model = VehicleModel.objects.filter(
                model_fitment_value__icontains=model,
                year=year or 2024 # Fallback
            ).first()
            
            # 2. Fetch Precise Specs from Fitment Group API
            api_specs = {}
            if v_model:
                logger.info(f"ProductService: Found DB model {v_model.model_fitment_value}. Fetching API specs...")
                api_specs = FitmentApiService.get_fitment_specs(
                    year_id=v_model.year,
                    make_id=v_model.make_fitment_id,
                    model_id=v_model.model_fitment_id
                )
            
            # 3. Determine Search Criteria (API Priority > Cache Fallback)
            bolt_pattern = api_specs.get("bolt_pattern")
            plus_sizes = api_specs.get("plus_sizes", [])
            
            if not bolt_pattern:
                logger.warning(f"ProductService: API failed for {make} {model}. Using fallback patterns.")
                valid_patterns = ConfigCache.get_patterns_sync(make, model)
            else:
                logger.info(f"ProductService: API resolved bolt pattern: {bolt_pattern}")
                valid_patterns = [bolt_pattern]

            # 4. Query WheelProduct
            queryset = WheelProduct.objects.filter(map_usd__gt=0, quantity__gt=0).order_by('-quantity')
            
            # 4a. Bolt Pattern Filter (Hard Firewall)
            if valid_patterns:
                pattern_query = Q()
                for p in valid_patterns:
                    # Metric match or Standard match
                    pattern_query |= Q(bolt_pattern_metric__icontains=p) | Q(bolt_pattern_standard__icontains=p)
                queryset = queryset.filter(pattern_query)
            
            # 4b. Configuration Filter (Diameter & Width from Plus Sizes)
            if plus_sizes:
                config_query = Q()
                for ps in plus_sizes:
                    d = ps.get("rimDiameter")
                    w = ps.get("rimWidth")
                    if d and w:
                        # Match wheels that fit one of the manufacturer-approved configurations
                        config_query |= Q(diameter=d, width=w)
                
                if config_query:
                    allowed_sizes = [f"{ps.get('rimDiameter')}x{ps.get('rimWidth')}" for ps in plus_sizes]
                    logger.info(f"ProductService: Filtering by {len(plus_sizes)} API-approved size configurations: {allowed_sizes}")
                    queryset = queryset.filter(config_query)

            # 5. Apply User Preference Filters
            if entities:
                sku = entities.get("sku")
                if sku:
                    logger.info(f"ProductService: Precision SKU lookup for {sku}")
                    queryset = queryset.filter(sku=sku)

                price_max = entities.get("budget_max") or entities.get("price_max")
                if price_max: queryset = queryset.filter(map_usd__lte=float(price_max))
                
                usage = entities.get("usage") or entities.get("style")
                if usage: queryset = queryset.filter(embedding_text__icontains=usage)
                
                finish = entities.get("finish")
                if finish:
                    queryset = queryset.filter(fancy_finish_desc__iregex=rf"\b{re.escape(finish)}\b")
                
                # User-specified size overrides or narrows the API list
                user_size = entities.get("size")
                if user_size:
                    try:
                        d_val = float(re.search(r'(\d+)', str(user_size)).group(1))
                        queryset = queryset.filter(diameter=d_val)
                    except: pass

            if exclude_names:
                queryset = queryset.exclude(sku__in=exclude_names).exclude(product_name__in=exclude_names)

            results = list(queryset.order_by('map_usd')[:limit])
            return results

        raw_results = await sync_to_async(_execute, thread_sensitive=False)()
        return [ProductService._serialize_product(p) for p in raw_results]