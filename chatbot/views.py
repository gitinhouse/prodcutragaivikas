import json
import logging
import hashlib
import re
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.http import StreamingHttpResponse, JsonResponse
from django.views import View
from django.shortcuts import render
from django.views.generic import TemplateView
from chatbot.services.stream_service import StreamService
from chatbot.services.upload_service import UploadService

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.views")

class ChatFrontendView(TemplateView):
    template_name = "chatbot/chat.html"

class ChatUploadView(View):
    """
    Handles Knowledge Base file uploads with strict security validation.
    """
    template_name = "chatbot/upload.html"
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_TYPES = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'text/csv'
    ]

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        if 'file' not in request.FILES:
            return JsonResponse({"error": "No file uploaded"}, status=400)
        
        file_obj = request.FILES['file']
        logger.info(f"Upload process started for file: {file_obj.name}")
        
        if file_obj.size > self.MAX_FILE_SIZE:
            return render(request, self.template_name, {"error": "File too large. Max size is 5MB."})
            
        if file_obj.content_type not in self.ALLOWED_TYPES:
            return render(request, self.template_name, {"error": "Invalid file type. Please upload Excel or CSV."})
        
        file_content = file_obj.read()
        import_type = request.POST.get('import_type', 'legacy')
        results = UploadService.process_file(file_content, file_obj.name, import_type=import_type)
        
        if results.get("errors"):
            logger.warning(f"Upload completed with {len(results['errors'])} errors.")
            return render(request, self.template_name, {
                "results": results,
                "error": "Some rows failed to import. Check details below."
            })
            
        logger.info(f"Upload successful: {results['success']} products imported.")
        return render(request, self.template_name, {
            "results": results,
            "success": f"Successfully processed {results['success']} products!"
        })

class ChatStreamView(View):
    """
    Native HTTP Streaming (SSE) view for Chat interactions.
    Now instrumented with deep observability logs.
    """
    
    def _mask_pii(self, text: str) -> str:
        """
        Masks PII at the ingress point.
        (Emails allowed for Lead Capture functionality).
        """
        phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
        masked = re.sub(phone_pattern, "[PHONE_MASKED]", text)
        return masked

    async def post(self, request, thread_id):
        try:
            # 1. Session Binding
            def _get_session_key(req):
                if not req.session.session_key:
                    req.session.create()
                return req.session.session_key
            
            session_key = await sync_to_async(_get_session_key)(request)
            
            # 2. Rate Limiting (Logged)
            throttle_key = f"throttle_{session_key}"
            request_count = await sync_to_async(cache.get)(throttle_key, 0)
            
            if request_count >= 20:
                logger.error(f"RATE LIMIT TRIGGERED: Session={session_key[:8]}")
                return JsonResponse({"error": "Rate limit exceeded."}, status=429)
            
            await sync_to_async(cache.set)(throttle_key, request_count + 1, 60)

            # 3. Secure Thread (Logged)
            user_hash = hashlib.blake2b(
                session_key.encode(),
                key=settings.SECRET_KEY[:32].encode(),
                digest_size=16
            ).hexdigest()
            secure_thread_id = f"user_{user_hash}_{thread_id}"
            
            logger.info(f"--- 🚀 MESSAGE INGRESS [Thread: {secure_thread_id[:12]}...] ---")

            # 4. Input Validation & Masking
            body = json.loads(request.body)
            raw_input = body.get('message', '')
            
            if not raw_input:
                return JsonResponse({"error": "No message"}, status=400)
            
            # --- 🔥 TRACE: PII MASKING ---
            safe_input = self._mask_pii(raw_input)
            if safe_input != raw_input:
                logger.info("PII Shield: Sensitive data masked successfully.")

            # 5. Initialize the Stream (Logged)
            logger.info(f"Handing off to StreamService for generation...")
            stream_gen = StreamService.get_stream(safe_input, secure_thread_id)
            
            response = StreamingHttpResponse(stream_gen, content_type='text/event-stream')
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response

        except Exception as e:
            logger.exception("FAULT in ChatStreamView")
            return JsonResponse({"error": str(e)}, status=500)

class ChatClearView(View):
    """
    Secure purge of the current conversation thread.
    """
    async def post(self, request, thread_id):
        try:
            def _get_key(req):
                key = req.session.session_key
                if not key:
                    req.session.create()
                    key = req.session.session_key
                return key
                
            session_key = await sync_to_async(_get_key)(request)
            
            user_hash = hashlib.blake2b(
                session_key.encode(),
                key=settings.SECRET_KEY[:32].encode(),
                digest_size=16
            ).hexdigest()
            secure_thread_id = f"user_{user_hash}_{thread_id}"

            logger.info(f"--- 🗑️ PURGE REQUEST [Thread: {secure_thread_id[:12]}...] ---")
            checkpointer = await StreamService.get_checkpointer()
            await checkpointer.adelete_thread(thread_id=secure_thread_id)
            
            logger.info(f"Purge successful for thread: {secure_thread_id}")
            return JsonResponse({"status": "success"})

        except Exception as e:
            logger.exception("FAULT in ChatClearView")
            return JsonResponse({"error": str(e)}, status=500)
