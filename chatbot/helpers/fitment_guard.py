import logging
import re
from chatbot.helpers.config_cache import ConfigCache

logger = logging.getLogger("chatbot.helpers.fitment_guard")

class FitmentGuard:
    """
    DETERMINISTIC FITMENT SAFETY: The 'Sanity Check' Layer.
    Prevents the LLM/DB from recommending physically impossible wheels.
    Example: 22" wheels on an Audi A4.
    """

    @staticmethod
    async def validate(vehicle_context, product):
        """
        Returns True if product is within sane physical limits for the vehicle type.
        """
        v_type = str(vehicle_context.get("type", "sedan")).lower()
        make = str(vehicle_context.get("make", "")).lower()
        model = str(vehicle_context.get("model", "")).lower()
        
        # 1. HEURISTIC OVERRIDE: If type is missing, infer from common sedans
        sedan_brands = ["audi", "bmw", "mercedes", "honda", "toyota", "lexus", "tesla"]
        if not v_type or v_type == "none":
            if any(b in make for b in sedan_brands):
                v_type = "sedan"
            if any(m in model for m in ["civic", "accord", "a4", "a3", "3 series", "c class", "corolla"]):
                v_type = "sedan"

        # 2. RESOLVE LIMITS (Dynamic from DB via ConfigCache)
        limits = await ConfigCache.get_vehicle_limits(v_type)
        
        # 3. EXTRACT PRODUCT DIMENSIONS
        name = product.get("marketing_name", "")
        # Try to get from attributes first
        diameter = product.get("diameter")
        width = product.get("width")
        
        # Fallback to name regex
        if not diameter or not width:
            dimensions = re.search(r"(\d{2})x(\d{1,2}\.?\d?)", name)
            if dimensions:
                diameter = diameter or float(dimensions.group(1))
                width = width or float(dimensions.group(2))
        
        if diameter and width:
            # 4. ENFORCE LIMITS
            if diameter > limits["max_diameter"]:
                logger.warning(f"FitmentGuard: REJECTED {name} for {v_type} (Diameter {diameter} > {limits['max_diameter']})")
                return False
            
            if width > limits["max_width"]:
                logger.warning(f"FitmentGuard: REJECTED {name} for {v_type} (Width {width} > {limits['max_width']})")
                return False

        return True

    @staticmethod
    async def validate_pattern(vehicle_make, product_pattern, vehicle_model=None):
        """
        Technical verification of bolt pattern against make and model standards.
        """
        if not vehicle_make or not product_pattern:
            return True # Insufficient data to reject
            
        make_low = vehicle_make.lower().strip()
        model_low = vehicle_model.lower().strip() if vehicle_model else None
        pattern_low = product_pattern.lower().replace(" ", "")
        
        # 1. Get patterns (Dynamic from DB via ConfigCache)
        valid_patterns = await ConfigCache.get_patterns(make_low, model_low)
        
        if not valid_patterns:
            return True # No rules defined for this vehicle
            
        if any(p.lower() in pattern_low for p in valid_patterns):
            return True
            
        logger.warning(f"FitmentGuard: REJECTED. {product_pattern} is impossible for {vehicle_make} {vehicle_model or ''}.")
        return False
