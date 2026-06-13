import json
import logging

import requests
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django_ratelimit.decorators import ratelimit

from learning.services.youtube import fetch_youtube_metadata

logger = logging.getLogger(__name__)


@method_decorator(
    ratelimit(key="user", rate="20/h", method="POST", block=False),
    name="dispatch",
)
class YouTubePreviewView(LoginRequiredMixin, View):
    def post(self, request):
        if getattr(request, "limited", False):
            return JsonResponse(
                {"error": "Too many requests. Please wait before trying again."},
                status=429,
            )

        try:
            body = json.loads(request.body)
            url = (body.get("url") or "").strip()
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"error": "Invalid request body."}, status=400)

        if not url:
            return JsonResponse({"error": "URL is required."}, status=400)

        try:
            metadata = fetch_youtube_metadata(url)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.RequestException as exc:
            logger.warning("YouTube API request failed: %s", exc)
            return JsonResponse(
                {"error": "Could not reach YouTube. Please try again."}, status=502
            )

        return JsonResponse(metadata)
