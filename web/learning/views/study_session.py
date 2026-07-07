import calendar as _calendar
import datetime
import json

from django.contrib import messages
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from learning.forms import StudySessionForm
from learning.mixins import UserPermissionMixin
from learning.models import LearningResource, StudySession

# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------


def _parse_date(value):
    """Return a date from an ISO string, or None on invalid/missing input."""
    try:
        return datetime.date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _get_month_calendar(session_qs, year, month):
    """
    Return calendar grid data for the given month.
    Used by both the SSR page and the AJAX month-navigation endpoint.
    """
    daily_totals = {
        row["date"]: row["total"]
        for row in session_qs.for_month(year, month)
        .values("date")
        .annotate(total=Sum("duration_minutes"))
    }

    cal = _calendar.Calendar(firstweekday=0)  # Monday-anchored
    weeks = [
        [
            {
                "date": d.isoformat(),
                "day": d.day,
                "in_month": d.month == month,
                "total_minutes": daily_totals.get(d, 0),
            }
            for d in week
        ]
        for week in cal.monthdatescalendar(year, month)
    ]

    all_totals = list(daily_totals.values())
    prev_date = datetime.date(year, month, 1) - datetime.timedelta(days=1)
    next_date = datetime.date(year, month, 28) + datetime.timedelta(days=4)

    return {
        "year": year,
        "month": month,
        "month_name": datetime.date(year, month, 1).strftime("%B %Y"),
        "total_minutes": sum(all_totals),
        "active_days": sum(1 for t in all_totals if t > 0),
        "weeks": weeks,
        "prev_year": prev_date.year,
        "prev_month": prev_date.month,
        "next_year": next_date.year,
        "next_month": next_date.month,
    }


def _get_day_sessions(session_qs, date):
    """Return sessions for a specific date, ready for the day panel."""
    sessions = list(session_qs.filter(date=date).select_related("resource"))
    return {
        "day_sessions": [s.to_dict() for s in sessions],
        "day_total_minutes": sum(s.duration_minutes for s in sessions),
        "day_session_count": len(sessions),
    }


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
        ctx["resources_json"] = json.dumps([
            {
                "id": r.id,
                "name": r.title,
                "kind": r.resource_type.content_kind,
                "tag": r.resource_type.name,
            }
            for r in resources
        ])

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
        label = "Session planned." if form.instance.status == StudySession.Status.PLANNED else "Session logged."
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
        status_filter = request.GET.get("status", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity:
            session_qs = session_qs.filter(activity_type=activity)
        if status_filter:
            session_qs = session_qs.filter(status=status_filter)

        selected_date = _parse_date(request.GET.get("date")) or today

        return render(
            request,
            "sessions/session_list.html",
            {
                **_get_month_calendar(session_qs, year, month),
                **_get_day_sessions(session_qs, selected_date),
                "selected_date": selected_date,
                "activity_types": StudySession.ActivityType.choices,
                "status_choices": StudySession.Status.choices,
                "selected_activity": activity,
                "selected_status": status_filter,
                "form": StudySessionForm(user=request.user),
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
        status_filter = request.GET.get("status", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity:
            session_qs = session_qs.filter(activity_type=activity)
        if status_filter:
            session_qs = session_qs.filter(status=status_filter)

        return JsonResponse(_get_month_calendar(session_qs, year, month))


class StudySessionDayView(UserPermissionMixin, View):
    """AJAX: sessions for a clicked date (day detail panel)."""

    permission_required = "learning.view_studysession"

    def get(self, request):
        date = _parse_date(request.GET.get("date"))
        if not date:
            return JsonResponse({"error": "valid date required"}, status=400)

        activity = request.GET.get("activity", "").strip()
        status_filter = request.GET.get("status", "").strip()

        session_qs = StudySession.objects.for_user(request.user)
        if activity:
            session_qs = session_qs.filter(activity_type=activity)
        if status_filter:
            session_qs = session_qs.filter(status=status_filter)

        return JsonResponse(_get_day_sessions(session_qs, date))
