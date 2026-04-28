import logging
import time
from typing import Dict, List, Any, Optional
from asgiref.sync import sync_to_async
from django.utils.timezone import now

logger = logging.getLogger("chatbot.helpers.config_cache")

class ConfigCache:
    """
    In-Memory Cache for fitment rules and brand configurations.
    Prevents database bottlenecks during agent execution.
    """
    
    _last_updated = 0
    _ttl = 600  # 10 minutes
    
    # Cached Data
    WHEEL_BRANDS: List[str] = []
    VEHICLE_LIMITS: Dict[str, Dict[str, float]] = {}
    MAKE_PATTERNS: Dict[str, List[str]] = {}
    MODEL_PATTERNS: Dict[str, Dict[str, List[str]]] = {}
    KNOWN_MAKES: List[str] = []

    @classmethod
    async def refresh_if_needed(cls, force=False):
        """Asynchronously refreshes the cache if TTL has expired or force is True."""
        if force or (time.time() - cls._last_updated > cls._ttl):
            await cls._load_from_db()

    @classmethod
    @sync_to_async
    def _load_from_db(cls):
        """Loads data from the database into memory."""
        from chatbot.models import Brand, VehicleTypeLimit, BoltPatternRule, Fitment
        
        logger.info("ConfigCache: Refreshing from database...")
        start_time = time.time()
        
        try:
            # 1. Brands
            cls.WHEEL_BRANDS = list(Brand.objects.filter(is_wheel_brand=True).values_list('name', flat=True))
            
            # 2. Vehicle Type Limits
            cls.VEHICLE_LIMITS = {
                obj.vehicle_type: {
                    'max_diameter': obj.max_diameter,
                    'max_width': obj.max_width
                }
                for obj in VehicleTypeLimit.objects.all()
            }
            
            # 3. Bolt Pattern Rules
            make_rules = {}
            model_rules = {}
            
            for rule in BoltPatternRule.objects.all():
                make_low = rule.make.lower()
                if not rule.model:
                    make_rules[make_low] = rule.patterns
                else:
                    model_low = rule.model.lower()
                    if make_low not in model_rules:
                        model_rules[make_low] = {}
                    model_rules[make_low][model_low] = rule.patterns
            
            cls.MAKE_PATTERNS = make_rules
            cls.MODEL_PATTERNS = model_rules
            
            # 4. Known Automotive Makes
            # We derive this from the Fitment table (actual inventory coverage)
            # plus any explicitly defined BoltPatternRules
            inv_makes = list(Fitment.objects.values_list('make', flat=True).distinct())
            rule_makes = list(BoltPatternRule.objects.values_list('make', flat=True).distinct())
            cls.KNOWN_MAKES = list(set([m.lower() for m in inv_makes + rule_makes if m]))
            
            cls._last_updated = time.time()
            logger.info(f"ConfigCache: Refresh complete in {cls._last_updated - start_time:.4f}s. "
                        f"Loaded {len(cls.WHEEL_BRANDS)} brands and {len(cls.KNOWN_MAKES)} makes.")
            
        except Exception as e:
            logger.error(f"ConfigCache: Failed to load from database: {e}")

    @classmethod
    async def get_wheel_brands(cls) -> List[str]:
        await cls.refresh_if_needed()
        return cls.WHEEL_BRANDS

    @classmethod
    async def get_vehicle_limits(cls, v_type: str) -> Dict[str, float]:
        await cls.refresh_if_needed()
        return cls.VEHICLE_LIMITS.get(v_type.lower(), cls.VEHICLE_LIMITS.get("sedan", {"max_diameter": 20, "max_width": 9.5}))

    @classmethod
    async def get_patterns(cls, make: str, model: Optional[str] = None) -> List[str]:
        await cls.refresh_if_needed()
        make_low = make.lower()
        
        # Check model override
        if model:
            model_low = model.lower()
            model_rule = cls.MODEL_PATTERNS.get(make_low, {}).get(model_low)
            if model_rule:
                return model_rule
        
        # Fallback to make default
        return cls.MAKE_PATTERNS.get(make_low, [])

    @classmethod
    def get_patterns_sync(cls, make: str, model: Optional[str] = None) -> List[str]:
        """Synchronous version with flexible matching for model rules."""
        make_low = make.lower()
        make_rules = cls.MAKE_PATTERNS.get(make_low, [])
        
        if model:
            model_low = model.lower()
            model_rules_map = cls.MODEL_PATTERNS.get(make_low, {})
            
            # 1. Exact Match
            if model_low in model_rules_map:
                return model_rules_map[model_low]
            
            # 2. Flexible Match (e.g. 'Civic' -> 'Civic Sedan')
            for m_key, m_patterns in model_rules_map.items():
                if model_low in m_key or m_key in model_low:
                    logger.info(f"ConfigCache: Flexible pattern match '{model_low}' -> '{m_key}'")
                    return m_patterns
        
        # 3. Hard-Coded Manufacturer Fallback (Failsafe)
        fallbacks = {
            "honda": ["5x114.3", "4x100"],
            "bmw": ["5x120", "5x112"],
            "toyota": ["5x114.3", "5x100", "6x139.7"],
            "tesla": ["5x114.3", "5x120"],
            "audi": ["5x112"],
            "mercedes": ["5x112"],
            "ford": ["5x114.3", "6x135", "5x108"],
            "jeep": ["5x127", "5x114.3"]
        }
        
        return fallbacks.get(make_low, [])

    @classmethod
    async def is_known_make(cls, make: str) -> bool:
        await cls.refresh_if_needed()
        return make.lower() in cls.KNOWN_MAKES
