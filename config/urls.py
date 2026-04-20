from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def api_health_check(request):
    return JsonResponse({
        "status": "online",
        "service": "SalesAI Chatbot API",
        "version": "v1"
    })

urlpatterns = [
    # Main Frontend (Studio Layout)
    path("", include("chatbot.urls")),
    
    # Admin & Diagnostics
    path("admin/", admin.site.urls),
    path("api/health/", api_health_check, name="api_health"),
]
