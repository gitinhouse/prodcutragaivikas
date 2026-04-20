"""
SEBASTIAN SALES AI - DOMAIN CONSTANTS & MASTER LISTS
Single Source of Truth (DRY Restoration Standard)
RELEVANCE > HELPFULNESS (Iron Boundary Enforced)
"""

# --- 1. WHITELIST (CORE DOMAIN) ---
WHEEL_KEYWORDS = [
    "wheel", "rim", "mag", "alloy", "offset", "bolt", "lug", "bore", 
    "diameter", "width", "finish", "black", "chrome", "matte", "gloss",
    "fuel", "dirty life", "method", "american", "truxx", "at1914", "sku",
    "truck", "suv", "jeep", "wrangler", "f150", "specs", "price", "size"
]

# --- 2. SAFE CONTEXTS (GREETINGS & PLEASANTRIES) ---
# Allowing standard entries into the sales funnel
SAFE_GREETINGS = [
    "hello", "hi", "hey", "greetings", "morning", "evening", "afternoon", 
    "howdy", "sup", "yo", "helloo", "thanks", "thank you", "great"
]

# --- 3. BLACKLISTS (RESTRICED CATEGORIES) ---

BANNED_OUT_OF_CATALOG = [
    "cake", "pen", "food", "shoe", "bread", "insurance", "oil", "bakery",
    "butterscotch", "medical", "doctor", "lawyer", "finance", "politics"
]

BANNED_UNSUPPORTED_AUTOMOTIVE = [
    "tire", "tyre", "lift kit", "suspension", "brake", "transmission", 
    "engine", "shocks", "shock absorber", "exhaust", "battery", "service",
    "repair", "alignment"
]

# Used by the Nuclear Response Gate for a deterministic refusal
DENIAL_MASTER_LIST = BANNED_OUT_OF_CATALOG + BANNED_UNSUPPORTED_AUTOMOTIVE

# For State Observability
VIOLATION_MAP = {
    "out_of_catalog": BANNED_OUT_OF_CATALOG,
    "unsupported_automotive": BANNED_UNSUPPORTED_AUTOMOTIVE
}
