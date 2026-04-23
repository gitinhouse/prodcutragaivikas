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
            "price": float(p.price),
            "stock": p.stock,
            "part_number": p.part_number,
            "stock": p.stock,
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
            # Broad search to find the closest match
            match = Product.objects.select_related('brand').filter(
                Q(name__icontains=product_name) | Q(part_number__icontains=product_name)
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
        exclude_ids: Optional[List[str]] = None,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        def _execute_search_logic():
            sku_candidate = ProductService._extract_sku_candidate(query_text) or ProductService._extract_sku_candidate(entities.get("brand", ""))
            if sku_candidate:
                sku_match = Product.objects.select_related('brand').filter(
                    Q(part_number__iexact=sku_candidate) | 
                    Q(part_number__icontains=sku_candidate)
                ).first()
                if sku_match: return [sku_match]

            queryset = Product.objects.select_related('brand')
            if exclude_ids: queryset = queryset.exclude(id__in=exclude_ids)

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
            if len(results) >= 2: return results

            if query_vector:
                results = list(Product.objects.select_related('brand').exclude(embedding__isnull=True).annotate(distance=CosineDistance("embedding", query_vector)).order_by("distance")[:limit])
                if results: return results
            
            clean_query = " ".join([w for w in query_text.split() if len(w) > 2])
            results = list(Product.objects.select_related('brand').filter(Q(name__icontains=clean_query) | Q(searchable_text__icontains=clean_query)).order_by('?')[:limit])
            return results

        raw_results = await sync_to_async(_execute_search_logic, thread_sensitive=False)()
        return [ProductService._serialize_product(p) for p in raw_results]

    @staticmethod
    async def get_wheels_by_fitment(
        make: str, model: str, year: int, 
        entities: Optional[Dict[str, Any]] = None,
        limit: int = 12
    ) -> List[Dict[str, Any]]:
        def _execute():
            # 1. Base Fitment Set
            fitments = Fitment.objects.select_related('product', 'product__brand').filter(
                make__iexact=make, model__iexact=model,
                year_from__lte=year, year_to__gte=year
            )
            product_ids = fitments.values_list('product_id', flat=True).distinct()
            base_queryset = Product.objects.select_related('brand').filter(id__in=product_ids)
            
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