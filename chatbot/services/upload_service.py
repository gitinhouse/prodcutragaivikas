import pandas as pd
import io
import logging
import re
import json
from typing import Dict, Any, List
from django.db import transaction
from django.core.exceptions import ValidationError
from chatbot.models import (
    VehicleYear, VehicleMake, VehicleModel, WheelProduct
)
from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class UploadService:
    """
    Advanced Catalog Engine for Specification-Based Fitment.
    Handles high-speed ingestion of Vehicle Years, Makes, Models, and Wheel Products.
    """

    @classmethod
    def process_file(cls, file_content: bytes, file_name: str, import_type: str = 'wheel_products') -> Dict[str, Any]:
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
            if import_type == 'vehicle_years':
                return cls._process_vehicle_year_data(df)
            elif import_type == 'vehicle_makes':
                return cls._process_vehicle_make_data(df)
            elif import_type == 'vehicle_models':
                return cls._process_vehicle_model_data(df)
            elif import_type == 'wheel_products':
                return cls._process_wheel_product_data(df)
            else:
                raise ValueError(f"Invalid import type: {import_type}")

        except Exception as e:
            logger.error(f"Catalog processing failed: {str(e)}")
            return {"total": 0, "success": 0, "failed": 0, "errors": [str(e)]}

    @classmethod
    def _process_vehicle_year_data(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Processes flat Vehicle Year data."""
        results = {"total": len(df), "success": 0, "failed": 0, "errors": []}
        for index, row in df.iterrows():
            try:
                year_val = int(row.get('years') or row.get('year'))
                VehicleYear.objects.get_or_create(year=year_val)
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Row {index+1}: {str(e)}")
        return results

    @classmethod
    def _process_vehicle_make_data(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Processes flat Vehicle Make data."""
        results = {"total": len(df), "success": 0, "failed": 0, "errors": []}
        for index, row in df.iterrows():
            try:
                # Support both 'year' and 'years' column names
                year_val = row.get('years') or row.get('year')
                # Support both 'make_fitment_value' and 'model_fitment_value' for legacy compatibility
                make_val = row.get('make_fitment_value') or row.get('model_fitment_value')

                VehicleMake.objects.create(
                    make_fitment_id=str(row['make_fitment_id']),
                    years=int(year_val),
                    make_fitment_value=str(make_val)
                )
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Row {index+1}: {str(e)}")
        return results

    @classmethod
    def _process_vehicle_model_data(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Processes flat Vehicle Model data."""
        results = {"total": len(df), "success": 0, "failed": 0, "errors": []}
        for index, row in df.iterrows():
            try:
                VehicleModel.objects.create(
                    make_fitment_id=str(row['make_fitment_id']),
                    year=int(row['year']),
                    model_fitment_id=str(row['model_fitment_id']),
                    model_fitment_value=str(row['model_fitment_value'])
                )
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Row {index+1}: {str(e)}")
        return results

    @classmethod
    def _process_wheel_product_data(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Processes enriched Wheel Product data with Vectorization."""
        results = {"total": len(df), "success": 0, "failed": 0, "errors": []}
        products_to_embed = []
        
        # Rename common column variants if necessary
        col_map = {
            'sku': 'sku', 'product_name': 'product_name', 'product_desc': 'product_desc',
            'brand_desc': 'brand_desc', 'style': 'style', 'fancy_finish_desc': 'fancy_finish_desc',
            'diameter': 'diameter', 'width': 'width', 'bolt_pattern_metric': 'bolt_pattern_metric',
            'bolt_pattern_standard': 'bolt_pattern_standard', 'wheel_offset': 'wheel_offset',
            'backspacing': 'backspacing', 'centerbore': 'centerbore', 'image_url1': 'image_url1',
            'category_name': 'category_name', 'size_desc': 'size_desc', 'quantity': 'quantity',
            'map_usd': 'map_usd'
        }
        
        for index, row in df.iterrows():
            try:
                def _safe_float(val):
                    try: return float(val) if val != "" else None
                    except: return None

                with transaction.atomic():
                    wheel, _ = WheelProduct.objects.update_or_create(
                        sku=str(row['sku']),
                        defaults={
                            'product_name': str(row['product_name']),
                            'product_desc': str(row.get('product_desc', '')),
                            'brand_desc': str(row['brand_desc']),
                            'style': str(row.get('style', '')),
                            'fancy_finish_desc': str(row.get('fancy_finish_desc', '')),
                            'diameter': _safe_float(row.get('diameter')),
                            'width': _safe_float(row.get('width')),
                            'bolt_pattern_metric': str(row.get('bolt_pattern_metric', '')),
                            'bolt_pattern_standard': str(row.get('bolt_pattern_standard', '')),
                            'wheel_offset': str(row.get('wheel_offset', '')),
                            'backspacing': _safe_float(row.get('backspacing')),
                            'centerbore': _safe_float(row.get('centerbore')),
                            'image_url1': str(row.get('image_url1', '')),
                            'category_name': str(row.get('category_name', '')),
                            'size_desc': str(row.get('size_desc', '')),
                            'quantity': int(row.get('quantity', 0) or 0),
                            'map_usd': _safe_float(row.get('map_usd')),
                        }
                    )
                    
                    # Generate Golden String for Vectorization
                    golden_string = f"Brand: {wheel.brand_desc}. Name: {wheel.product_name}. " \
                                    f"Finish: {wheel.fancy_finish_desc}. Style: {wheel.style}. " \
                                    f"Specs: {wheel.diameter}x{wheel.width}, Bolt Pattern: {wheel.bolt_pattern_metric}. " \
                                    f"Description: {wheel.product_desc}"
                    
                    wheel.embedding_text = golden_string
                    wheel.save(update_fields=['embedding_text'])
                    products_to_embed.append(wheel)
                    results["success"] += 1
                    
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Row {index+1} (SKU {row.get('sku')}): {str(e)}")

        if products_to_embed:
            # We need to update EmbeddingService to handle WheelProduct or make it generic
            # For now, I'll assume we can pass any model with embedding fields to a generic batch update
            EmbeddingService.batch_update_products_sync(products_to_embed)
            
        return results

