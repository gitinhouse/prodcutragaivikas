import pandas as pd
import io
import logging
import re
import json
from typing import Dict, Any, List
from django.db import transaction
from django.core.exceptions import ValidationError
from chatbot.models import Product, Brand, Category
from config.llm_config import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class UploadService:
    """
    Advanced AI Catalog Engine.
    Handles Regex extraction, AI enrichment, and RAG optimization.
    """

    DEFAULT_ATTRIBUTES = {
        "vehicle_type": [],
        "usage": [],
        "style": [],
        "terrain": [],
        "durability": ""
    }

    @classmethod
    def process_file(cls, file_content: bytes, file_name: str) -> Dict[str, Any]:
        """
        Main entry point for processing Knowledge Base files.
        """
        try:
            # 1. Parsing
            if file_name.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_content))
            elif file_name.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(io.BytesIO(file_content))
            else:
                raise ValueError("Unsupported file format. Please use CSV or Excel.")

            # 2. Cleaning
            df = df.fillna("")
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
            df.columns = [str(c).strip().lower() for c in df.columns]

            # 3. Column Mapping
            col_map = {
                'name': 'name', 'product_name': 'name', 'product name': 'name', 'title': 'name',
                'description': 'description', 'details': 'description',
                'price': 'price', 'cost': 'price',
                'category': 'category_name', 'brand': 'brand_name',
                'stock': 'stock', 'inventory': 'stock',
                'part_number': 'part_number', 'sku': 'part_number',
                'barcode': 'barcode', 'upc': 'barcode'
            }
            df = df.rename(columns={c: col_map[c] for c in df.columns if c in col_map})

            # Check core required columns
            required_cols = ['name', 'description', 'price', 'category_name', 'brand_name']
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")

            results = {"total": len(df), "success": 0, "failed": 0, "errors": []}
            products_to_embed = []

            # 4. Processing Loop
            # No atomic transaction globally because AI calls take time and can fail
            for index, row in df.iterrows():
                try:
                    name = str(row['name'])
                    desc = str(row['description'])
                    price = float(row['price'])
                    
                    # A. Regex Extraction (Structured Specs)
                    specs = cls._extract_specs_from_name(name)
                    
                    # B. AI Enhancement (Attributes & Summary)
                    ai_data = cls._extract_ai_data(name, desc)
                    
                    # C. Merging & Categorization
                    final_attributes = cls._merge_attributes(ai_data.get("attributes", {}))
                    price_cat = cls._get_price_category(price)
                    
                    # D. Embedding Text Construction
                    embedding_text = cls._build_embedding_text(
                        summary=ai_data.get("ai_summary", ""),
                        attributes=final_attributes,
                        features=ai_data.get("features", []),
                        name=name,
                        raw_desc=desc
                    )

                    # E. Database Write
                    with transaction.atomic():
                        brand, _ = Brand.objects.get_or_create(name=str(row['brand_name']).title())
                        category, _ = Category.objects.get_or_create(name=str(row['category_name']).title())

                        product, _ = Product.objects.update_or_create(
                            name=name,
                            brand=brand,
                            defaults={
                                'description': desc,
                                'price': price,
                                'category': category,
                                'stock': int(row.get('stock', 0) or 0),
                                'part_number': row.get('part_number', ""),
                                'barcode': row.get('barcode', ""),
                                'diameter': specs['diameter'],
                                'width': specs['width'],
                                'offset': specs['offset'],
                                'bolt_pattern': specs['bolt_pattern'],
                                'finish': specs['finish'],
                                'attributes': final_attributes,
                                'features': ai_data.get("features", []),
                                'ai_summary': ai_data.get("ai_summary", ""),
                                'price_category': price_cat,
                                'embedding_text': embedding_text
                            }
                        )
                        products_to_embed.append(product)
                        results["success"] += 1

                except Exception as e:
                    results["failed"] += 1
                    err_hint = f"Row {index+1} ({row.get('name', 'Unknown')}): {str(e)}"
                    results["errors"].append(err_hint)
                    logger.error(err_hint)

            # 5. Batch Embedding
            if products_to_embed:
                EmbeddingService.batch_update_products_sync(products_to_embed)
                
            return results

        except Exception as e:
            logger.error(f"Catalog processing failed: {str(e)}")
            return {"total": 0, "success": 0, "failed": 0, "errors": [str(e)]}

    @staticmethod
    def _extract_specs_from_name(name: str) -> Dict[str, Any]:
        """
        Uses Regex to pull structured specs from wheel names.
        Example: "20X12 -44MM 8X165.1 GLOSS BLACK"
        """
        name_upper = name.upper()
        specs = {
            "diameter": None, "width": None, "offset": None, 
            "bolt_pattern": None, "finish": None
        }

        # Diameter X Width (e.g., 20X12)
        dim_match = re.search(r'(\d+)X(\d+)', name_upper)
        if dim_match:
            specs["diameter"] = float(dim_match.group(1))
            specs["width"] = float(dim_match.group(2))

        # Offset (e.g., -44MM or +12MM)
        off_match = re.search(r'([-+]?\d+)MM', name_upper)
        if off_match:
            specs["offset"] = float(off_match.group(1))

        # Bolt Pattern (e.g., 8X165.1 or 5X114.3)
        # We use a tighter pattern to avoid matching DiameterXWidth (like 20X12) 
        # Bolt patterns typically start with 4, 5, 6, or 8 (lugs)
        bolt_match = re.search(r'\b([4568]X\d+(?:\.\d+)?)\b', name_upper)
        if bolt_match:
            specs["bolt_pattern"] = bolt_match.group(1)
        elif not specs["diameter"]: 
            # Fallback if no diameter was found earlier, let's look for any DxW
            any_match = re.search(r'(\d+X\d+(?:\.\d+)?)', name_upper)
            if any_match:
                specs["bolt_pattern"] = any_match.group(1)

        # Finish Extraction (Regex-based from a common list)
        finish_patterns = [
            "GLOSS BLACK", "SATIN BLACK", "MATTE BLACK", "CHROME", 
            "POLISHED", "MACHINED", "SILVER", "BRONZE", "ANTHRACITE",
            "CANDY RED", "GLOSS WHITE"
        ]
        for f in finish_patterns:
            if f in name_upper:
                specs["finish"] = f.title()
                break

        return specs

    @classmethod
    def _extract_ai_data(cls, name: str, description: str) -> Dict[str, Any]:
        """
        Calls OpenAI to extract attributes and summary from description.
        Includes full fallback logic.
        """
        llm = get_llm()
        prompt = f"""
        Analyze the wheel product below and extract attributes/summary.
        
        NAME: {name}
        DESCRIPTION: {description}
        
        Return ONLY valid JSON with these keys:
        - "attributes": {{ 
            "vehicle_type": [], 
            "usage": [], 
            "style": [], 
            "terrain": [], 
            "durability": "" 
          }}
        - "features": [] (list of key technical features)
        - "ai_summary": "Clean one-sentence marketing summary"

        CRITICAL: All values in 'attributes' MUST be in Title Case and Singular (e.g., 'Truck', not 'trucks'; 'SUV', not 'suvs').
        """

        try:
            response = llm.invoke([
                SystemMessage(content="You are a wheel catalog specialist. Return strictly structured JSON."),
                HumanMessage(content=prompt)
            ])
            # Extract JSON from response (handling potential markdown formatting)
            json_str = response.content
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(json_str)
            return data
        except Exception as e:
            logger.warning(f"AI Enhancement failed for {name}: {str(e)}. Using fallback.")
            return {
                "attributes": {}, 
                "features": [], 
                "ai_summary": f"High-quality {name} designed for performance and style."
            }

    @classmethod
    def _merge_attributes(cls, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clones default structure and merges AI results to ensure 100% key consistency.
        Also normalizes values to Title Case and Singular where possible.
        """
        final = cls.DEFAULT_ATTRIBUTES.copy()
        if not isinstance(extracted, dict):
            return final
            
        for key in final.keys():
            val = extracted.get(key)
            if val:
                if isinstance(val, list):
                    # Normalize list items: Title Case and remove 's' if at end (basic singularization)
                    normalized_list = []
                    for item in val:
                        clean_item = str(item).strip().title()
                        if clean_item.endswith('s') and len(clean_item) > 4: # Simple heuristic for plurals
                             clean_item = clean_item[:-1]
                        normalized_list.append(clean_item)
                    final[key] = list(set(normalized_list)) # deduplicate
                else:
                    # Normalize string value
                    clean_val = str(val).strip().title()
                    if clean_val.endswith('s') and len(clean_val) > 4:
                        clean_val = clean_val[:-1]
                    final[key] = clean_val
        return final

    @staticmethod
    def _get_price_category(price: float) -> str:
        """
        Assigns standard price buckets.
        """
        if price < 1000:
            return "budget"
        if price <= 1800:
            return "mid-range"
        return "premium"

    @staticmethod
    def _build_embedding_text(summary: str, attributes: Dict, features: List, name: str, raw_desc: str) -> str:
        """
        Constructs the 'Golden String' for RAG.
        Guarantees content even on AI failure (Safe-Search).
        """
        # Baseline Safe-Search
        baseline = f"Product: {name}. {summary if summary else raw_desc[:200]}"
        
        # Enrich if attributes exist
        enrichments = []
        for k, v in attributes.items():
            if v:
                enrichments.append(f"{k}: {v}")
        
        if features:
            enrichments.append(f"Features: {', '.join(features)}")
            
        full_text = f"{baseline} {' '.join(enrichments)}"
        return full_text.strip()
