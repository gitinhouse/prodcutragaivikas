from django.urls import path
from .views import ChatStreamView, ChatFrontendView, ChatUploadView, ChatClearView

urlpatterns = [
    # Modern Native Frontend (Django Templates)
    path("", ChatFrontendView.as_view(), name="home"),
    path("upload/", ChatUploadView.as_view(), name="chat_upload"),
    
    # Modern Streaming & Control Endpoints
    path("chat/<str:thread_id>/stream/", ChatStreamView.as_view(), name="chat_stream"),
    path("chat/<str:thread_id>/clear/", ChatClearView.as_view(), name="chat_clear"),
]
