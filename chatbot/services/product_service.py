import re
import json
import logging
from typing import List, Optional, Dict, Any, Union
from django.db.models import Q, Case, When, Value, FloatField
from asgiref.sync import sync_to_async
from pgvector.django import CosineDistance
from chatbot.helpers.config_cache import ConfigCache
from chatbot.models import Product, Brand, Category, Fitment
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
        match = re.search(r'([A-Z0-9]+-[A-Z0-9.-]+|[A-Z]{2,}[0-9]{3,}|[A-Z0-9]{5,})', text.upper())
        return match.group(1) if match else None

    @staticmethod
    def _serialize_product(p: Product) -> Dict[str, Any]:
        return {
            "id": str(p.id),
            "name": p.name,
            "brand_name": p.brand.name,
            "marketing_name": f"{p.brand.name} {p.name}",
            "price": float(p.price) if p.price is not None else None,
            "stock": p.stock,
            "part_number": p.part_number,
            "finish": p.finish,
            "bolt_pattern": p.bolt_pattern,
            "diameter": p.diameter,
            "width": p.width,
            "specification": {
                "diameter": p.diameter,
                "width": p.width,
                "finish": p.finish,
                "bolt_pattern": p.bolt_pattern
            },
            "ai_summary": p.ai_summary
        }

    @staticmethod
    async def check_inventory_status(product_name: str) -> Dict[str, Any]:
        """
        Targeted Real-Time Stock Verification.
        Returns availability status and details.
        """
        def _execute():
            # 1. SMART SEARCH: Split Brand and Model for better matching
            # Handles "Bbs Model-95" by searching for "Model-95"
            name_parts = product_name.split()
            core_name = name_parts[-1] if len(name_parts) > 1 else product_name
            
            match = Product.objects.select_related('brand').filter(
                Q(name__iexact=product_name) | 
                Q(name__iexact=core_name) |
                Q(part_number__iexact=product_name) |
                Q(name__icontains=core_name)
            ).first()
            
            if not match:
                return {"is_available": False, "status": "Not found"}
            
            # SIMULATION: In a real production app, we would query an ERP/API here.
            # Here we assume everything in DB is available unless price is 0 or it's a test SKU.
            is_avail = match.price > 0
            return {
                "is_available": is_avail,
                "product": ProductService._serialize_product(match),
                "status": "In Stock" if is_avail else "Backordered"
            }
            
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
            sku_candidate = ProductService._extract_sku_candidate(query_text) or ProductService._extract_sku_candidate(entities.get("brand", ""))
            if sku_candidate:
                sku_match = Product.objects.select_related('brand').filter(
                    Q(part_number__iexact=sku_candidate) | 
                    Q(part_number__icontains=sku_candidate)
                ).first()
                if sku_match: return [sku_match]

            from django.db.models.functions import Concat
            from django.db.models import Value
            
            queryset = Product.objects.select_related('brand')
            if exclude_names:
                queryset = queryset.annotate(
                    full_m_name=Concat('brand__name', Value(' '), 'name')
                ).exclude(full_m_name__in=exclude_names)

            diameter = entities.get("size")
            bolt_pattern = entities.get("bolt_pattern")
            price_max = entities.get("budget_max") or entities.get("price_max")
            
            if diameter:
                try:
                    d_val = float(re.search(r'(\d+)', str(diameter)).group(1))
                    queryset = queryset.filter(diameter=d_val)
                except: pass
            
            if bolt_pattern: queryset = queryset.filter(bolt_pattern__icontains=bolt_pattern)
            if price_max:
                try: queryset = queryset.filter(price__lte=float(price_max))
                except: pass

            finish = entities.get("finish")
            if finish: queryset = queryset.filter(Q(finish__icontains=finish) | Q(searchable_text__icontains=finish))

            # Apply brand filter to the existing queryset instead of returning early
            wheel_brand = entities.get("wheel_brand") or entities.get("brand")
            
            # Fallback: check query_text for known wheel brands if LLM missed it
            if not wheel_brand:
                for b in known_brands:
                    if b.lower() in query_text.lower():
                        wheel_brand = b
                        break

            if wheel_brand:
                queryset = queryset.filter(brand__name__icontains=wheel_brand)
                
            usage = entities.get("usage") or entities.get("style", "")
            v_type = entities.get("vehicle_type")
            
            style_boost_terms = ["rugged", "off-road", "trail", "mud", "aggressive", "sport", "luxury"]
            active_style_terms = [t for t in style_boost_terms if t in query_text.lower() or t in usage.lower()]
            
            if active_style_terms or v_type:
                when_clauses = [When(searchable_text__icontains=t, then=Value(10.0)) for t in active_style_terms]
                if v_type:
                    when_clauses.append(When(attributes__vehicle_type__contains=[v_type.upper()], then=Value(5.0)))
                if when_clauses:
                    queryset = queryset.annotate(relevance_score=Case(*when_clauses, default=Value(1.0), output_field=FloatField())).order_by('-relevance_score', 'price')
                else: queryset = queryset.order_by('price')
            else: queryset = queryset.order_by('price')

            results = list(queryset.exclude(embedding__isnull=True)[:limit])
            if len(results) >= 1: return results
            
            if query_vector:
                results = list(Product.objects.select_related('brand').exclude(embedding__isnull=True).annotate(distance=CosineDistance("embedding", query_vector)).order_by("distance")[:limit])
                if results: return results
            
            clean_query = " ".join([w for w in query_text.split() if len(w) > 2])
            results = list(Product.objects.select_related('brand').filter(Q(name__icontains=clean_query) | Q(searchable_text__icontains=clean_query)).order_by('?')[:limit])
            return results

        raw_results = await sync_to_async(_execute_search_logic, thread_sensitive=False)(known_brands)
        logger.info(f"ProductService: Returning {len(raw_results)} final products: {[p.name for p in raw_results]}")
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
        def _execute():
            # 1. Flexible Model Matching
            # Normalize 'f150' -> 'f-150' or 'f 150'
            clean_model = model.replace("-", "").replace(" ", "").lower()
            
            # 2. Base Fitment Set
            query = Q(make__iexact=make)
            if year is not None:
                query &= Q(year_from__lte=year, year_to__gte=year)

            # Try exact model match first
            exact_query = query & Q(model__iexact=model)
            fitments = Fitment.objects.select_related('product', 'product__brand').filter(exact_query)
            
            if not fitments.exists():
                # Fallback to flexible matching
                if clean_model == "f150":
                    flex_query = query & (Q(model__icontains="f-150") | Q(model__icontains="f150"))
                else:
                    flex_query = query & Q(model__icontains=model)
                fitments = Fitment.objects.select_related('product', 'product__brand').filter(flex_query)
            
            from django.db.models.functions import Concat
            from django.db.models import Value
            
            product_ids = fitments.values_list('product_id', flat=True).distinct()
            base_queryset = Product.objects.select_related('brand').filter(id__in=product_ids)
            logger.info(f"ProductService: Found {base_queryset.count()} total fitment candidates for {make} {model}.")
            
            if exclude_names:
                base_queryset = base_queryset.annotate(
                    full_m_name=Concat('brand__name', Value(' '), 'name')
                ).exclude(full_m_name__in=exclude_names)
                logger.info(f"ProductService: After excluding {len(exclude_names)} shown products, {base_queryset.count()} candidates remain.")

            # --- SMART TECHNICAL FIREWALL: Bolt Pattern Alignment ---
            valid_patterns = ConfigCache.get_patterns_sync(make, model)
            if valid_patterns:
                # We trust the Fitment Table, but we FILTER OUT obvious mechanical mismatches
                # (e.g., if the car is 6x135, we don't show a 5x114.3 wheel even if linked in DB)
                pattern_query = Q()
                for p in valid_patterns:
                    pattern_query |= Q(bolt_pattern__iexact=p) | Q(bolt_pattern__icontains=f"{p}")
                
                # Apply the filter but allow a fallback if it kills EVERY result
                filtered_queryset = base_queryset.filter(pattern_query)
                if filtered_queryset.exists():
                    base_queryset = filtered_queryset
                    logger.info(f"ProductService: Filtered out mismatches for {make} {model}. Remaining: {base_queryset.count()}")
                else:
                    logger.warning(f"ProductService: Strict pattern filter would return 0 results. Trusting Fitment Table mapping for {make} {model}.")
            
            # 2. Refined Search (Style/Budget)
            refined_queryset = base_queryset
            
            if entities:
                price_max = entities.get("budget_max") or entities.get("price_max")
                if price_max:
                    try: refined_queryset = refined_queryset.filter(price__lte=float(price_max))
                    except: pass
                
                usage = entities.get("usage") or entities.get("style")
                if usage:
                    # SOFT FILTER: Try to match style, but don't return 0 if no style match
                    style_query = refined_queryset.filter(Q(searchable_text__icontains=usage) | Q(attributes__usage__contains=[usage.upper()]))
                    if style_query.exists():
                        refined_queryset = style_query
                    else:
                        logger.warning(f"ProductService: Style '{usage}' found no matches for {make} {model}. Relaxing style.")

                finish = entities.get("finish")
                if finish:
                    # FINISH GUARD: Filter by color/finish if specified
                    finish_query = refined_queryset.filter(Q(finish__icontains=finish) | Q(searchable_text__icontains=finish))
                    if finish_query.exists():
                        refined_queryset = finish_query
                    else:
                        logger.warning(f"ProductService: Finish '{finish}' found no matches for {make} {model}. Relaxing finish.")

            results = list(refined_queryset[:limit])
            
            # 3. Fallback: If refined search (e.g. style) killed all results, use base set
            if not results and base_queryset.exists():
                logger.warning(f"ProductService: Filtered search failed for {make} {model}. Falling back to base fitment.")
                results = list(base_queryset[:limit])
                
            return results

        raw_results = await sync_to_async(_execute, thread_sensitive=False)()
        return [ProductService._serialize_product(p) for p in raw_results]