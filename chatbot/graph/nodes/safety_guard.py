import logging
import re
from chatbot.graph.state import GraphState
import random
from chatbot.helpers.prompts import VARIATION_POOLS
from langchain_core.messages import AIMessage

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.safety_guard")

def safety_guard_node(state: GraphState):
    """
    DETERMINISTIC SAFETY SHIELD: Data Integrity & Hallucination Guard.
    Validates product names and prices against source data.
    Performs 'Partial Sanitization' rather than hard blocking.
    """
    final_resp = state.get("final_response", "").strip()
    raw_data = state.get("raw_response_data", {})
    products = raw_data.get("products", [])
    
    # 1. EMPTY RESPONSE RECOVERY
    if not final_resp:
        logger.warning("Safety Guard: Empty response. Applying recovery.")
        msg = "Let's get your build started—what car are we working with?"
        return {"final_response": msg, "messages": [AIMessage(content=msg)]}

    # 2. DATA INTEGRITY VALIDATION (Names & Prices)
    if products:
        # Create lookup for valid name -> price
        valid_data = {p.get("marketing_name", "").lower(): str(p.get("price", "")) for p in products}
        
        # Split into lines for partial sanitization
        lines = final_resp.split("\n")
        sanitized_lines = []
        hallucination_triggered = False

        for line in lines:
            # Detect product mentions: **Product Name** (exclude bold prices like **$562.0**)
            all_bold = re.findall(r"\*\*(.*?)\*\*", line)
            product_mentions = [
                m for m in all_bold
                if not m.strip().startswith("$") and not m.strip()[0:1].isdigit()
            ]
            line_is_valid = True
            
            for mention in product_mentions:
                mention_lower = mention.lower().strip()
                
                # Check if name is real
                if mention_lower not in valid_data:
                    logger.error(f"Safety Guard: Hallucinated product name '{mention}'")
                    line_is_valid = False
                    hallucination_triggered = True
                    break
                
                # Check if price is consistent (if mentioned in same line)
                price_match = re.search(r"\$([\d]+(?:\.\d+)?)", line)
                if price_match:
                    try:
                        mentioned_price = float(price_match.group(1))
                        actual_price = float(valid_data[mention_lower])
                        if mentioned_price != actual_price:
                            logger.error(f"Safety Guard: Price mismatch for {mention} (AI: ${mentioned_price} | DB: ${actual_price})")
                            line_is_valid = False
                            hallucination_triggered = True
                            break
                    except (ValueError, TypeError):
                        pass  # If price can't be parsed, skip the check
            
            if line_is_valid:
                sanitized_lines.append(line)

        # 3. CONTEXTUAL RECOVERY
        if not sanitized_lines or (hallucination_triggered and len(sanitized_lines) < 2):
            logger.warning("Safety Guard: Significant hallucination. Serving safe recovery.")
            fallback = random.choice(VARIATION_POOLS.get("hallucination_guard", ["I'm double-checking the specs for you..."]))
            return {"final_response": fallback, "messages": [AIMessage(content=fallback)]}
        
        # Reassemble the sanitized response
        final_resp = "\n".join(sanitized_lines)

    logger.info("Safety Guard: Response cleared (and sanitized if needed).")
    return {
        "final_response": final_resp,
        "messages": [AIMessage(content=final_resp)]
    }
