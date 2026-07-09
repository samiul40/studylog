import datetime
import json
import zoneinfo

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone as dj_timezone
from django.utils.text import slugify
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from learning.forms import StudySessionForm
from learning.mixins import UserPermissionMixin
from learning.models import Activity, LearningResource, LearningUnit, StudySession
from learning.services.sessions import get_day_sessions, get_month_calendar


def _parse_date(value: str | None) -> datetime.date | None:
    """Return a date from an ISO string, or None on invalid/missing input."""
    try:
        return datetime.date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _user_today(request) -> datetime.date:
    """Return today's date in the user's profile timezone."""
    tz_name = getattr(getattr(request.user, "profile", None), "timezone", None) or "UTC"
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
        return dj_timezone.now().astimezone(tz).date()
    except Exception:
        return datetime.date.today()


def _find_or_create_activity(name: str, user) -> Activity | None:
    """
    Case-insensitive find-or-create for a user's custom activity.
    Returns None if name is empty or exceeds 32 chars.
    """
    name = name.strip()[:32]
    if not name:
        return None
    slug = slugify(name)
    existing = Activity.objects.filter(
        Q(is_system=True, slug=slug) | Q(is_system=False, user=user, slug=slug)
    ).first()
    if existing:
        return existing
    activity, _ = Activity.objects.get_or_create(
        slug=slug,
        user=user,
        is_system=False,
        defaults={"name": name},
    )
    return activity


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

    def get_success_url(self):
        next_url = self.request.GET.get("next", "")
        if next_url and next_url.startswith("/"):
            return next_url
        return reverse("learning:session_list")

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

        # System activities + user's own custom activities for the picker.
        activities = list(
            Activity.objects.for_user(user).order_by("-is_system", "name")
        )
        ctx["activities_json"] = json.dumps(
            [
                {
                    "id": a.id,
                    "slug": a.slug,
                    "name": a.name,
                    "is_system": a.is_system,
                }
                for a in activities
            ]
        )

        ctx["recent_sessions"] = (
            StudySession.objects.for_user(user)
            .filter(status=StudySession.Status.LOGGED)
            .select_related("resource", "activity")[:4]
        )
        ctx["today_iso"] = _user_today(self.request).isoformat()
        ctx["resource_prefill"] = self.request.GET.get("resource", "")
        ctx["date_prefill"] = self.request.GET.get("date", "")
        return ctx

    def form_valid(self, form):
        # If the user typed a new custom activity name, find-or-create it.
        new_name = form.cleaned_data.get("new_activity_name", "").strip()
        if new_name:
            activity = _find_or_create_activity(new_name, self.request.user)
            if not activity:
                form.add_error(
                    None,
                    "Activity name is required (max 32 characters).",
                )
                return self.form_invalid(form)
            form.instance.activity = activity

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
        new_name = form.cleaned_data.get("new_activity_name", "").strip()
        if new_name:
            activity = _find_or_create_activity(new_name, self.request.user)
            if activity:
                form.instance.activity = activity
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
        today = _user_today(request)
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        activity_slug = request.GET.get("activity", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity_slug:
            session_qs = session_qs.filter(activity__slug=activity_slug)

        selected_date = _parse_date(request.GET.get("date")) or today

        cal_data = get_month_calendar(session_qs, year, month)
        day_data = get_day_sessions(session_qs, selected_date)

        # Activities for the filter bar: system + user's custom.
        filter_activities = list(
            Activity.objects.for_user(request.user).order_by("-is_system", "name")
        )
        filter_activities_json = json.dumps(
            [
                {
                    "slug": a.slug,
                    "name": a.name,
                    "is_system": a.is_system,
                }
                for a in filter_activities
            ]
        )

        return render(
            request,
            "sessions/session_list.html",
            {
                "cal_data_json": json.dumps(cal_data),
                "day_data_json": json.dumps(day_data),
                "selected_date_iso": selected_date.isoformat(),
                "today_iso": today.isoformat(),
                "activity_filter": activity_slug,
                "filter_activities_json": filter_activities_json,
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

        activity_slug = request.GET.get("activity", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity_slug:
            session_qs = session_qs.filter(activity__slug=activity_slug)

        return JsonResponse(get_month_calendar(session_qs, year, month))


class StudySessionDayView(UserPermissionMixin, View):
    """AJAX: sessions for a clicked date (day detail panel)."""

    permission_required = "learning.view_studysession"

    def get(self, request):
        date = _parse_date(request.GET.get("date"))
        if not date:
            return JsonResponse({"error": "valid date required"}, status=400)

        activity_slug = request.GET.get("activity", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity_slug:
            session_qs = session_qs.filter(activity__slug=activity_slug)

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

        if "activity_slug" in data:
            slug = str(data["activity_slug"]).strip()
            activity = Activity.objects.for_user(request.user).filter(slug=slug).first()
            if activity:
                session.activity = activity

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

        if "title" in data:
            session.title = str(data["title"]).strip()

        if "topic" in data:
            session.topic = str(data["topic"]).strip()

        if "notes" in data:
            session.notes = str(data["notes"]).strip()

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

        if "activity_slug" in data:
            slug = str(data["activity_slug"]).strip()
            activity = Activity.objects.for_user(request.user).filter(slug=slug).first()
            if activity:
                session.activity = activity

        if "duration_minutes" in data:
            try:
                mins = int(data["duration_minutes"])
                if mins >= 1:
                    session.duration_minutes = mins
            except (TypeError, ValueError):
                pass

        if "title" in data:
            session.title = str(data["title"]).strip()

        if "topic" in data:
            session.topic = str(data["topic"]).strip()

        if "notes" in data:
            session.notes = str(data["notes"]).strip()

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
