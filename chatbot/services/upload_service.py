import pandas as pd
import io
import logging
import re
import json
from typing import Dict, Any, List
from django.db import transaction
from django.core.exceptions import ValidationError
from chatbot.models import Product, Brand, Category, Fitment
from config.llm_config import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class UploadService:
    """
    Advanced AI Catalog Engine with strict relational importing.
    Handles Legacy AI guessing, Strict Wheels mapping, and Fitment linking.
    """

    DEFAULT_ATTRIBUTES = {
        "vehicle_type": [],
        "usage": [],
        "style": [],
        "terrain": [],
        "durability": ""
    }

    @classmethod
    def process_file(cls, file_content: bytes, file_name: str, import_type: str = 'legacy') -> Dict[str, Any]:
        """
        Main entry point for processing Knowledge Base files.
        """
        try:
            # 1. Parsing
            if file_name.endswith(('.tsv', '.txt')):
                df = pd.read_csv(io.BytesIO(file_content), sep='\t')
            elif file_name.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_content))
            elif file_name.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(io.BytesIO(file_content))
            else:
                raise ValueError("Unsupported format. Use TSV, CSV, or Excel.")

            # 2. Cleaning Base Layer
            df = df.fillna("")
            df = df.map(lambda x: str(x).strip() if isinstance(x, str) else x)
            df.columns = [str(c).strip().lower() for c in df.columns]

            # 3. Routing
            if import_type == 'wheels':
                return cls._process_wheels_data(df)
            elif import_type == 'fitments':
                return cls._process_fitment_data(df)
            else:
                return cls._process_legacy_data(df)

        except Exception as e:
            logger.error(f"Catalog processing failed: {str(e)}")
            return {"total": 0, "success": 0, "failed": 0, "errors": [str(e)]}

    @classmethod
    def _process_legacy_data(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Legacy logic using AI extraction from product descriptions."""
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

        required_cols = ['name', 'description', 'price', 'category_name', 'brand_name']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        results = {"total": len(df), "success": 0, "failed": 0, "errors": []}
        products_to_embed = []

        for index, row in df.iterrows():
            try:
                name = str(row['name'])
                desc = str(row['description'])
                price = float(row['price'])
                
                specs = cls._extract_specs_from_name(name)
                ai_data = cls._extract_ai_data(name, desc)
                final_attributes = cls._merge_attributes(ai_data.get("attributes", {}))
                price_cat = cls._get_price_category(price)
                
                embedding_text = cls._build_embedding_text(
                    summary=ai_data.get("ai_summary", ""),
                    attributes=final_attributes,
                    features=ai_data.get("features", []),
                    name=name,
                    raw_desc=desc
                )

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

        if products_to_embed:
            EmbeddingService.batch_update_products_sync(products_to_embed)
            
        return results

    @classmethod
    def _process_wheels_data(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Processes strictly mapped precision Wheel Data."""
        results = {"total": len(df), "success": 0, "failed": 0, "errors": []}
        products_to_embed = []
        
        required = ['item_id', 'brand', 'model', 'size', 'price']
        for r in required:
            if r not in df.columns:
                raise ValueError(f"Missing required strict column: {r}")

        for index, row in df.iterrows():
            try:
                item_id = str(row['item_id'])
                brand_name = str(row['brand']).title()
                model_name = str(row['model']).title()
                full_name = f"{model_name} ({row['size']})"
                
                # Extract pure diameter from size (e.g. 20x9 -> 20)
                diameter_val = None
                if 'x' in str(row['size']).lower():
                    try:
                        diameter_val = float(str(row['size']).lower().split('x')[0])
                    except: pass
                
                # Convert floats safely
                def _safe_float(val):
                    try: return float(val) if val != "" else None
                    except: return None
                
                with transaction.atomic():
                    brand, _ = Brand.objects.get_or_create(name=brand_name)
                    category, _ = Category.objects.get_or_create(name="Wheels")

                    product, _ = Product.objects.update_or_create(
                        part_number=item_id,
                        defaults={
                            'name': full_name,
                            'brand': brand,
                            'description': f"Premium {brand_name} {model_name} wheel ({row['size']}). Finish: {row.get('finish', 'Standard')}",
                            'price': _safe_float(row['price']) or 0.0,
                            'category': category,
                            'stock': int(row.get('stock', 0) or 0),
                            'diameter': diameter_val,
                            'width': _safe_float(row.get('width')),
                            'offset': _safe_float(row.get('offset')),
                            'bolt_pattern': str(row.get('bolt_pattern', '')),
                            'finish': str(row.get('finish', '')),
                            'price_category': cls._get_price_category(_safe_float(row['price']) or 0.0),
                            'embedding_text': ""
                        }
                    )
                    
                    # Generate simple embedding text directly
                    product.embedding_text = f"Product: {brand_name} {model_name} Wheel. Size: {row.get('size')}. Finish: {row.get('finish')}. Bolt Pattern: {row.get('bolt_pattern')}."
                    product.save(update_fields=['embedding_text'])
                    
                    products_to_embed.append(product)
                    results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Row {index+1} (Item {row.get('item_id')}): {str(e)}")

        if products_to_embed:
            EmbeddingService.batch_update_products_sync(products_to_embed)
        return results

    @classmethod
    def _process_fitment_data(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Processes strictly mapped Vehicle Fitment Data."""
        results = {"total": len(df), "success": 0, "failed": 0, "errors": []}
        
        required = ['item_id', 'make', 'model', 'year_from', 'year_to']
        for r in required:
            if r not in df.columns:
                raise ValueError(f"Missing required fitment column: {r}")

        for index, row in df.iterrows():
            try:
                item_id = str(row['item_id'])
                
                def _safe_float(val):
                    try: return float(val) if val != "" else None
                    except: return None
                
                with transaction.atomic():
                    # Link to existing product explicitly
                    product = Product.objects.filter(part_number=item_id).first()
                    if not product:
                        raise ValueError(f"Wheel Item {item_id} not found in DB.")

                    Fitment.objects.get_or_create(
                        product=product,
                        make=str(row['make']).title(),
                        model=str(row['model']).title(),
                        year_from=int(row['year_from']),
                        year_to=int(row['year_to']),
                        defaults={
                            'bolt_pattern': str(row.get('bolt_pattern', '')),
                            'center_bore': _safe_float(row.get('center_bore')),
                            'offset_min': _safe_float(row.get('offset_min')),
                            'offset_max': _safe_float(row.get('offset_max')),
                        }
                    )
                    results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Row {index+1} (Item {row.get('item_id')}): {str(e)}")

        return results

    # --- Legacy Helpers Below ---

    @staticmethod
    def _extract_specs_from_name(name: str) -> Dict[str, Any]:
        name_upper = name.upper()
        specs = {
            "diameter": None, "width": None, "offset": None, 
            "bolt_pattern": None, "finish": None
        }

        dim_match = re.search(r'(\d+)X(\d+)', name_upper)
        if dim_match:
            specs["diameter"] = float(dim_match.group(1))
            specs["width"] = float(dim_match.group(2))

        off_match = re.search(r'([-+]?\d+)MM', name_upper)
        if off_match:
            specs["offset"] = float(off_match.group(1))

        bolt_match = re.search(r'\b([4568]X\d+(?:\.\d+)?)\b', name_upper)
        if bolt_match:
            specs["bolt_pattern"] = bolt_match.group(1)
        elif not specs["diameter"]: 
            any_match = re.search(r'(\d+X\d+(?:\.\d+)?)', name_upper)
            if any_match:
                specs["bolt_pattern"] = any_match.group(1)

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
        final = cls.DEFAULT_ATTRIBUTES.copy()
        if not isinstance(extracted, dict):
            return final
            
        for key in final.keys():
            val = extracted.get(key)
            if val:
                if isinstance(val, list):
                    normalized_list = []
                    for item in val:
                        clean_item = str(item).strip().title()
                        if clean_item.endswith('s') and len(clean_item) > 4:
                             clean_item = clean_item[:-1]
                        normalized_list.append(clean_item)
                    final[key] = list(set(normalized_list)) 
                else:
                    clean_val = str(val).strip().title()
                    if clean_val.endswith('s') and len(clean_val) > 4:
                        clean_val = clean_val[:-1]
                    final[key] = clean_val
        return final

    @staticmethod
    def _get_price_category(price: float) -> str:
        if price < 1000: return "budget"
        if price <= 1800: return "mid-range"
        return "premium"

    @staticmethod
    def _build_embedding_text(summary: str, attributes: Dict, features: List, name: str, raw_desc: str) -> str:
        baseline = f"Product: {name}. {summary if summary else raw_desc[:200]}"
        enrichments = []
        for k, v in attributes.items():
            if v: enrichments.append(f"{k}: {v}")
        if features:
            enrichments.append(f"Features: {', '.join(features)}")
        return f"{baseline} {' '.join(enrichments)}".strip()
