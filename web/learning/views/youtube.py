import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from learning.services.youtube import fetch_youtube_metadata


class YouTubePreviewView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            body = json.loads(request.body)
            url = (body.get("url") or "").strip()
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"error": "Invalid request body."}, status=400)

        if not url:
            return JsonResponse({"error": "URL is required."}, status=400)

        try:
            metadata = fetch_youtube_metadata(url)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        return JsonResponse(metadata)
