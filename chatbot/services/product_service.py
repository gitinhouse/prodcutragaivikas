import re
import json
import logging
from typing import List, Optional, Dict, Any, Union
from django.db.models import Q, Case, When, Value, FloatField
from asgiref.sync import sync_to_async
from pgvector.django import CosineDistance
from chatbot.models import Product, Brand, Category, Fitment
from .cache_service import CacheService

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.services.product")

class ProductService:
    """
    Universal Hybrid Search Engine (Production 7 Standard).
    Hardened for Style Diversity, Keyword Boosting, and Variety Shuffle.
    """

    @staticmethod
    def _normalize_ref(text: str) -> str:
        """Strips all non-alphanumeric noise and uppercases."""
        return re.sub(r'[^A-Z0-9]', '', text.upper())

    @staticmethod
    def _extract_sku_candidate(text: str) -> Optional[str]:
        """Extracts the most 'SKU-like' part of a string."""
        match = re.search(r'([A-Z0-9]+-[A-Z0-9.-]+|[A-Z]{2,}[0-9]{3,}|[A-Z0-9]{5,})', text.upper())
        return match.group(1) if match else None

    @staticmethod
    def _serialize_product(p: Product) -> Dict[str, Any]:
        """Helper to convert model to dict safely inside a sync context."""
        return {
            "id": str(p.id),
            "name": p.name,
            "brand_name": p.brand.name,
            "marketing_name": f"{p.brand.name} {p.name}",
            "price": float(p.price),
            "part_number": p.part_number,
            "ai_summary": p.ai_summary,
            "specification": {
                "diameter": p.diameter,
                "width": p.width,
                "finish": p.finish,
                "bolt_pattern": p.bolt_pattern
            },
            "attributes": p.attributes
        }

    @staticmethod
    async def universal_search(
        query_text: str,
        entities: Dict[str, Any],
        query_vector: Optional[List[float]] = None,
        exclude_ids: Optional[List[str]] = None,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        """
        THE COMMAND CENTER: Unified Waterfall Retrieval.
        Hardened with Style-Weighted Boosting and Refinement Shuffle.
        """
        
        def _execute_search_logic():
            # --- STAGE 0: SKU RESOLUTION ---
            sku_candidate = ProductService._extract_sku_candidate(query_text) or ProductService._extract_sku_candidate(entities.get("brand", ""))
            if sku_candidate:
                sku_match = Product.objects.select_related('brand').filter(
                    Q(part_number__iexact=sku_candidate) | 
                    Q(part_number__icontains=sku_candidate)
                ).first()
                if sku_match:
                    return [sku_match]

            # --- STAGE 1: TECHNICAL & CASE-RESILIENT JSONB ---
            queryset = Product.objects.select_related('brand')
            
            # Exclusion Filter (Refinement Shuffle)
            if exclude_ids:
                queryset = queryset.exclude(id__in=exclude_ids)

            # A. Technical Filters
            diameter = entities.get("size")
            bolt_pattern = entities.get("bolt_pattern")
            price_max = entities.get("budget_max") or entities.get("price_max")
            
            if diameter:
                try:
                    d_val = float(re.search(r'(\d+)', str(diameter)).group(1))
                    queryset = queryset.filter(diameter=d_val)
                except Exception: pass
            
            if bolt_pattern:
                queryset = queryset.filter(bolt_pattern__icontains=bolt_pattern)

            if price_max:
                try:
                    p_val = float(price_max)
                    logger.info(f"Universal Search: Applying Budget Cap of ${p_val}")
                    queryset = queryset.filter(price__lte=p_val)
                except Exception: pass

            # B. Style Tracking for Boosting
            usage = entities.get("usage") or entities.get("style", "")
            v_type = entities.get("vehicle_type")
            
            # --- STAGE 2: KEYWORD-WEIGHTED BOOSTING ---
            # If 'off-road' or similar is in the query, we boost results matching those keywords.
            style_boost_terms = ["rugged", "off-road", "trail", "mud", "aggressive", "sport", "luxury"]
            active_style_terms = [t for t in style_boost_terms if t in query_text.lower() or t in usage.lower()]
            
            if active_style_terms or v_type:
                logger.info(f"Universal Search: Applying Style-Weighted Boosting for {active_style_terms}")
                
                # We build a 'relevance_score' via CASE
                when_clauses = []
                for term in active_style_terms:
                    # Boost if the searchable_text contains the term
                    when_clauses.append(When(searchable_text__icontains=term, then=Value(10.0)))
                
                if v_type:
                    when_clauses.append(When(attributes__vehicle_type__contains=[v_type.upper()], then=Value(5.0)))
                    when_clauses.append(When(attributes__vehicle_type__contains=[v_type.capitalize()], then=Value(5.0)))

                if when_clauses:
                    queryset = queryset.annotate(
                        relevance_score=Case(*when_clauses, default=Value(1.0), output_field=FloatField())
                    ).order_by('-relevance_score', 'price')
                else:
                    queryset = queryset.order_by('price')
            else:
                queryset = queryset.order_by('price')

            # Stage 1 Final: Attempt specific JSONB containment first
            if usage:
                norm_usage = usage.replace("-", " ").title()
                u_cases = [norm_usage.upper(), norm_usage, norm_usage.lower(), norm_usage.replace(" ", "-")]
                specific_results = list(queryset.filter(
                    Q(attributes__usage__has_any_keys=u_cases) |
                    Q(attributes__usage__contains=[u_cases[0]]) |
                    Q(attributes__style__contains=[u_cases[0]])
                )[:limit])
                if len(specific_results) >= 2:
                    return specific_results

            # --- STAGE 3: EXECUTION (Annotated Boosting) ---
            results = list(queryset.exclude(embedding__isnull=True)[:limit])
            
            if len(results) >= 2:
                return results

            # --- STAGE 4: SEMANTIC FALLBACK (Vector) ---
            if query_vector:
                results = list(
                    Product.objects.select_related('brand')
                    .exclude(embedding__isnull=True)
                    .annotate(distance=CosineDistance("embedding", query_vector))
                    .order_by("distance")[:limit]
                )
                if results: return results
            
            # --- STAGE 5: BROAD SAFETY NET (Variety Fallback) ---
            # If everything else fails, fetch items by query keywords directly
            clean_query = " ".join([w for w in query_text.split() if len(w) > 2])
            results = list(
                Product.objects.select_related('brand')
                .filter(Q(name__icontains=clean_query) | Q(searchable_text__icontains=clean_query))
                .order_by('?')[:limit]
            )
            if results: return results

            # --- STAGE 6: WATERFALL RELAXATION (Crucial for Rule 2 & 4) ---
            # If we STILL have nothing, and we had technical filters, try relaxing them
            if not results and (diameter or bolt_pattern or brand):
                logger.info("Universal Search: Triggering Waterfall Relaxation...")
                relaxed_queryset = Product.objects.select_related('brand')
                
                # Try just brand + size (ignore pattern)
                if brand and diameter:
                    relaxed = list(relaxed_queryset.filter(brand__name__icontains=brand, diameter=diameter)[:limit])
                    if relaxed: return relaxed
                
                # Try just size + bolt_pattern (different brands)
                if diameter and bolt_pattern:
                    relaxed = list(relaxed_queryset.filter(diameter=diameter, bolt_pattern__icontains=bolt_pattern)[:limit])
                    if relaxed: return relaxed

                # Final Hail Mary: Just brand or just size
                if brand:
                    relaxed = list(relaxed_queryset.filter(brand__name__icontains=brand)[:limit])
                    if relaxed: return relaxed
                
                if diameter:
                    relaxed = list(relaxed_queryset.filter(diameter=diameter)[:limit])
                    if relaxed: return relaxed

            return results

        # Execute and Serialize
        raw_results = await sync_to_async(_execute_search_logic, thread_sensitive=False)()
        return [ProductService._serialize_product(p) for p in raw_results]

    @staticmethod
    async def get_catalog_overview() -> Dict[str, Any]:
        """Returns a summary of available brands."""
        def _get_brands():
            brands = list(Brand.objects.values_list('name', flat=True).order_by('name'))
            return {"brands": brands, "count": len(brands)}
        return await sync_to_async(_get_brands, thread_sensitive=False)()

    @staticmethod
    async def get_wheels_by_fitment(make: str, model: str, year: int, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Retrieves products via strict relational Fitment table mapping.
        """
        def _execute():
            fitments = Fitment.objects.select_related('product', 'product__brand').filter(
                make__iexact=make,
                model__iexact=model,
                year_from__lte=year,
                year_to__gte=year
            )
            product_ids = fitments.values_list('product_id', flat=True).distinct()[:limit]
            products = Product.objects.select_related('brand').filter(id__in=product_ids)
            return list(products)
            
        raw_results = await sync_to_async(_execute, thread_sensitive=False)()
        return [ProductService._serialize_product(p) for p in raw_results]