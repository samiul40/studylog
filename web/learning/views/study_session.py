import datetime
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from learning.forms import StudySessionForm
from learning.mixins import UserPermissionMixin
from learning.models import LearningResource, LearningUnit, StudySession
from learning.services.sessions import get_day_sessions, get_month_calendar

MANUAL_ACTIVITIES = [
    ("flashcards", "Flashcards / Anki"),
    ("practice", "Practice problems"),
    ("past_papers", "Past papers"),
    ("review_notes", "Review notes"),
    ("writing", "Writing / essays"),
]


def _parse_date(value: str | None) -> datetime.date | None:
    """Return a date from an ISO string, or None on invalid/missing input."""
    try:
        return datetime.date.fromisoformat(value) if value else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseStudySessionView(UserPermissionMixin):
    model = StudySession

    def get_queryset(self):
        return StudySession.objects.for_user(self.request.user)


# ---------------------------------------------------------------------------
# CRUD views
# ---------------------------------------------------------------------------


class StudySessionCreateView(UserPermissionMixin, CreateView):
    permission_required = "learning.add_studysession"
    model = StudySession
    form_class = StudySessionForm
    template_name = "sessions/session_create.html"
    success_url = reverse_lazy("learning:session_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        resources = (
            LearningResource.objects.for_user(user)
            .active()
            .select_related("resource_type")
            .order_by("title")
        )
        ctx["resources_json"] = json.dumps(
            [
                {
                    "id": r.id,
                    "name": r.title,
                    "kind": r.resource_type.content_kind,
                    "tag": r.resource_type.name,
                }
                for r in resources
            ]
        )

        units_qs = (
            LearningUnit.objects.filter(resource__in=resources)
            .order_by("resource_id", "order")
            .values("id", "title", "resource_id")
        )
        units_by_resource: dict[str, list] = {}
        for u in units_qs:
            key = str(u["resource_id"])
            units_by_resource.setdefault(key, []).append(
                {"id": u["id"], "title": u["title"]}
            )
        ctx["units_by_resource_json"] = json.dumps(units_by_resource)

        ctx["recent_sessions"] = (
            StudySession.objects.for_user(user)
            .filter(status=StudySession.Status.LOGGED)
            .select_related("resource")[:4]
        )
        ctx["today_iso"] = datetime.date.today().isoformat()
        ctx["resource_prefill"] = self.request.GET.get("resource", "")
        return ctx

    def form_valid(self, form):
        form.instance.user = self.request.user
        planned = form.instance.status == StudySession.Status.PLANNED
        label = "Session planned." if planned else "Session logged."
        messages.success(self.request, label)
        return super().form_valid(form)


class StudySessionUpdateView(BaseStudySessionView, UpdateView):
    permission_required = "learning.change_studysession"
    form_class = StudySessionForm
    success_url = reverse_lazy("learning:session_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Session updated.")
        return super().form_valid(form)


class StudySessionDeleteView(BaseStudySessionView, DeleteView):
    permission_required = "learning.delete_studysession"
    success_url = reverse_lazy("learning:session_list")

    def form_valid(self, form):
        messages.success(self.request, "Session deleted.")
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Calendar / day panel views
# ---------------------------------------------------------------------------


class StudySessionListView(UserPermissionMixin, View):
    """Full sessions page (SSR). Month grid + selected day panel on initial load."""

    permission_required = "learning.view_studysession"

    def get(self, request):
        today = datetime.date.today()
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        activity = request.GET.get("activity", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity:
            session_qs = session_qs.filter(activity_type=activity)

        selected_date = _parse_date(request.GET.get("date")) or today

        cal_data = get_month_calendar(session_qs, year, month)
        day_data = get_day_sessions(session_qs, selected_date)

        return render(
            request,
            "sessions/session_list.html",
            {
                "cal_data_json": json.dumps(cal_data),
                "day_data_json": json.dumps(day_data),
                "selected_date_iso": selected_date.isoformat(),
                "today_iso": today.isoformat(),
                "activity_filter": activity,
                "manual_activities": MANUAL_ACTIVITIES,
            },
        )


class StudySessionCalendarView(UserPermissionMixin, View):
    """AJAX: per-day totals for month navigation (prev/next buttons)."""

    permission_required = "learning.view_studysession"

    def get(self, request):
        try:
            year = int(request.GET["year"])
            month = int(request.GET["month"])
        except (KeyError, ValueError):
            return JsonResponse({"error": "year and month required"}, status=400)

        activity = request.GET.get("activity", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity:
            session_qs = session_qs.filter(activity_type=activity)

        return JsonResponse(get_month_calendar(session_qs, year, month))


class StudySessionDayView(UserPermissionMixin, View):
    """AJAX: sessions for a clicked date (day detail panel)."""

    permission_required = "learning.view_studysession"

    def get(self, request):
        date = _parse_date(request.GET.get("date"))
        if not date:
            return JsonResponse({"error": "valid date required"}, status=400)

        activity = request.GET.get("activity", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity:
            session_qs = session_qs.filter(activity_type=activity)

        return JsonResponse(get_day_sessions(session_qs, date))


# ---------------------------------------------------------------------------
# AJAX mutation views (used by the edit sheet)
# ---------------------------------------------------------------------------


class StudySessionPatchView(BaseStudySessionView, View):
    """AJAX: update a session's fields from the edit sheet."""

    permission_required = "learning.change_studysession"

    def post(self, request, pk):
        session = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if "activity_type" in data:
            val = data["activity_type"]
            if val in dict(StudySession.ActivityType.choices):
                session.activity_type = val

        if "duration_minutes" in data:
            try:
                mins = int(data["duration_minutes"])
                if mins < 1:
                    return JsonResponse(
                        {"error": "Duration must be at least 1 minute"},
                        status=400,
                    )
                session.duration_minutes = mins
            except (TypeError, ValueError):
                return JsonResponse({"error": "Invalid duration"}, status=400)

        if "topic" in data:
            session.topic = str(data["topic"]).strip()

        if "date" in data:
            d = _parse_date(data["date"])
            if d is None:
                return JsonResponse({"error": "Invalid date"}, status=400)
            session.date = d

        session.save()
        return JsonResponse({"ok": True, "session": session.to_dict()})


class StudySessionMarkDoneView(BaseStudySessionView, View):
    """AJAX: flip a planned session to logged, applying any pending edits."""

    permission_required = "learning.change_studysession"

    def post(self, request, pk):
        session = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            data = json.loads(request.body) if request.body else {}
        except (json.JSONDecodeError, ValueError):
            data = {}

        if "activity_type" in data:
            val = data["activity_type"]
            if val in dict(StudySession.ActivityType.choices):
                session.activity_type = val

        if "duration_minutes" in data:
            try:
                mins = int(data["duration_minutes"])
                if mins >= 1:
                    session.duration_minutes = mins
            except (TypeError, ValueError):
                pass

        if "topic" in data:
            session.topic = str(data["topic"]).strip()

        if "date" in data:
            d = _parse_date(data["date"])
            if d is not None:
                session.date = d

        session.status = StudySession.Status.LOGGED
        session.save()
        return JsonResponse({"ok": True, "session": session.to_dict()})


class StudySessionDeleteAjaxView(BaseStudySessionView, View):
    """AJAX: delete a session and return JSON."""

    permission_required = "learning.delete_studysession"

    def post(self, request, pk):
        session = get_object_or_404(self.get_queryset(), pk=pk)
        session.delete()
        return JsonResponse({"ok": True})
