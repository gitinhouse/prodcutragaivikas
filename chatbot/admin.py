from django.contrib import admin
from .models import (
    VehicleYear, VehicleMake, VehicleModel, WheelProduct
)

@admin.register(VehicleYear)
class VehicleYearAdmin(admin.ModelAdmin):
    list_display = ('year',)
    ordering = ('-year',)

@admin.register(VehicleMake)
class VehicleMakeAdmin(admin.ModelAdmin):
    list_display = ('make_fitment_value', 'years', 'make_fitment_id')
    list_filter = ('years',)
    search_fields = ('make_fitment_value', 'make_fitment_id')

@admin.register(VehicleModel)
class VehicleModelAdmin(admin.ModelAdmin):
    list_display = ('model_fitment_value', 'year', 'model_fitment_id')
    list_filter = ('year',)
    search_fields = ('model_fitment_value', 'model_fitment_id')

@admin.register(WheelProduct)
class WheelProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product_name', 'brand_desc', 'quantity', 'map_usd')
    search_fields = ('sku', 'product_name', 'brand_desc')
    list_filter = ('brand_desc', 'category_name')
