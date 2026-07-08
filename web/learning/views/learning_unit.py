import datetime
import json
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Case, IntegerField, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from learning.forms import LearningUnitForm
from learning.mixins import UserPermissionMixin
from learning.models import Activity, LearningResource, LearningUnit, StudySession
from learning.services.sessions import upsert_resource_session

_WATCH_SLUG = "watch"
_READ_SLUG = "read"

logger = logging.getLogger(__name__)


class UserResourceMixin:
    """
    Ensures the resource belongs to the logged-in user.
    """

    def get_resource(self):
        return get_object_or_404(
            LearningResource,
            pk=self.kwargs["resource_pk"],
            user=self.request.user,
        )


class UserUnitMixin:
    """
    Ensures the learning unit belongs to the logged-in user.
    """

    def get_unit(self):
        return get_object_or_404(
            LearningUnit,
            pk=self.kwargs["pk"],
            resource__user=self.request.user,
        )


class ResourceRedirectMixin:
    """
    Redirects to the parent resource detail page after a successful action.
    """

    def get_success_url(self):
        return reverse(
            "learning:resource_detail",
            kwargs={"pk": self.kwargs["resource_pk"]},
        )


class LearningUnitCreateView(
    UserPermissionMixin, UserResourceMixin, ResourceRedirectMixin, CreateView
):
    """
    Create a learning unit within a resource.
    """

    permission_required = "learning.add_learningunit"
    model = LearningUnit
    form_class = LearningUnitForm

    def form_valid(self, form):
        form.instance.resource = self.get_resource()
        messages.success(self.request, "Unit created successfully.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request,
            form.errors.get("video_progress_minutes", ["Invalid input"])[0],
        )
        return redirect(self.get_success_url())


class LearningUnitUpdateView(
    UserPermissionMixin, UserResourceMixin, ResourceRedirectMixin, UpdateView
):
    """
    Update an existing learning unit.
    """

    permission_required = "learning.change_learningunit"
    model = LearningUnit
    form_class = LearningUnitForm
    pk_url_kwarg = "unit_pk"

    def get_queryset(self):
        return LearningUnit.objects.filter(resource=self.get_resource())

    def form_valid(self, form):
        if not form.has_changed():
            return redirect(self.get_success_url())

        messages.success(self.request, "Unit updated successfully.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request,
            form.errors.get("video_progress_minutes", ["Invalid input"])[0],
        )
        return redirect(self.get_success_url())


class LearningUnitDeleteView(
    UserPermissionMixin, UserResourceMixin, ResourceRedirectMixin, DeleteView
):
    """
    Delete a learning unit.
    """

    permission_required = "learning.delete_learningunit"
    model = LearningUnit
    pk_url_kwarg = "unit_pk"

    def get_queryset(self):
        return LearningUnit.objects.filter(resource=self.get_resource())

    def form_valid(self, form):
        unit = self.get_object()
        resource = unit.resource

        messages.success(self.request, "Unit deleted successfully.")

        response = super().form_valid(form)

        units = list(LearningUnit.objects.filter(resource=resource).order_by("order"))

        for index, unit in enumerate(units, start=1):
            unit.order = index

        LearningUnit.objects.bulk_update(units, ["order"])

        return response


class LearningUnitReorderView(UserPermissionMixin, UserResourceMixin, View):
    """
    Update learning unit order after drag-and-drop.
    """

    permission_required = "learning.change_learningunit"

    def post(self, request, resource_pk):
        resource = self.get_resource()
        try:
            data = json.loads(request.body)
            order = data["order"]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "Invalid reorder payload for resource %s from user %s: %s",
                resource_pk,
                request.user.pk,
                exc,
            )
            return JsonResponse({"status": "error"}, status=400)

        cases = []
        ids = []

        for item in order:
            ids.append(item["id"])
            cases.append(When(id=item["id"], then=item["order"]))

        LearningUnit.objects.filter(resource=resource, id__in=ids).update(
            order=Case(*cases, output_field=IntegerField())
        )

        return JsonResponse({"status": "ok"})


class LearningUnitUpdateStatusView(UserPermissionMixin, UserUnitMixin, View):
    """
    Update the status of a learning unit (e.g. mark as completed).
    """

    permission_required = "learning.change_learningunit"

    def post(self, request, pk):
        unit = self.get_unit()
        new_status = request.POST.get("status")

        if new_status in dict(LearningUnit.StatusChoices.choices):
            if unit.status != new_status:
                unit.status = new_status
                unit.save()
                messages.success(request, "Unit status updated.")

        return redirect(unit.resource.get_absolute_url())


class LearningUnitInlinePatchView(UserPermissionMixin, View):
    """
    AJAX endpoint for inline field edits on the resource detail page.
    Accepts a JSON body with any subset of: duration_minutes,
    video_progress_minutes, notes. Returns the updated unit state.
    """

    permission_required = "learning.change_learningunit"

    def post(self, request, resource_pk, unit_pk):
        unit = get_object_or_404(
            LearningUnit,
            pk=unit_pk,
            resource__pk=resource_pk,
            resource__user=request.user,
        )

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Invalid inline patch payload for unit %s from user %s: %s",
                unit_pk,
                request.user.pk,
                exc,
            )
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

        # Capture before patching so we can compute deltas after save.
        old_progress = unit.video_progress_minutes
        old_status = unit.status

        # Detect a reading chapter being unchecked (completed → not_started).
        is_reading_uncheck = (
            data.get("status") == LearningUnit.StatusChoices.NOT_STARTED
            and old_status == LearningUnit.StatusChoices.COMPLETED
            and unit.resource.resource_type.content_kind == "reading"
        )

        if "duration_minutes" in data:
            val = data["duration_minutes"]
            unit.duration_minutes = int(val) if val not in (None, "") else None

        if "video_progress_minutes" in data:
            val = data["video_progress_minutes"]
            unit.video_progress_minutes = int(val) if val not in (None, "") else None

        if "status" in data and unit.video_progress_minutes is None:
            val = data["status"]
            if val in dict(LearningUnit.StatusChoices.choices):
                unit.status = val

        if is_reading_uncheck:
            unit.reading_minutes = None

        if "title" in data:
            val = str(data["title"]).strip()
            if val:
                unit.title = val

        if "notes" in data:
            unit.notes = str(data["notes"])

        try:
            unit.save()
        except ValidationError as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        # Reading chapter unchecked — delete its per-unit session.
        if is_reading_uncheck:
            read_activity = Activity.objects.filter(
                slug=_READ_SLUG, is_system=True
            ).first()
            if read_activity:
                StudySession.objects.filter(
                    user=request.user,
                    unit=unit,
                    activity=read_activity,
                ).delete()

        # Auto-log a watch session when video progress changes.
        if "video_progress_minutes" in data and unit.video_progress_minutes is not None:
            delta = unit.video_progress_minutes - (old_progress or 0)
            watch_activity = Activity.objects.filter(
                slug=_WATCH_SLUG, is_system=True
            ).first()
            if delta != 0 and watch_activity:
                upsert_resource_session(
                    user=request.user,
                    resource=unit.resource,
                    unit=unit,
                    date=datetime.date.today(),
                    activity=watch_activity,
                    delta_minutes=delta,
                )
            # Slider rewound to 0 — remove the now-empty session.
            if unit.video_progress_minutes == 0 and watch_activity:
                StudySession.objects.filter(
                    user=request.user,
                    unit=unit,
                    activity=watch_activity,
                    duration_minutes=0,
                ).delete()

        return JsonResponse({"ok": True, "unit": unit.to_inline_dict()})


class LearningUnitCompleteReadingView(UserPermissionMixin, UserUnitMixin, View):
    """
    Combined endpoint for reading chapter completion.
    Marks the unit as COMPLETED and logs a READING session.
    Accepts JSON: {"duration_minutes": <int>}
    Returns the updated unit state (same shape as inline patch).
    duration_minutes=0 is valid — session is logged even without a timed duration.
    """

    permission_required = "learning.change_learningunit"

    def post(self, request, pk):
        unit = self.get_unit()

        try:
            data = json.loads(request.body)
            new_duration = int(data.get("duration_minutes", 0))
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

        unit.status = LearningUnit.StatusChoices.COMPLETED
        unit.reading_minutes = new_duration if new_duration > 0 else None
        unit.save()

        # One session per chapter — update on re-log, create on first log.
        read_activity = Activity.objects.filter(slug=_READ_SLUG, is_system=True).first()
        if read_activity:
            StudySession.objects.update_or_create(
                user=request.user,
                unit=unit,
                activity=read_activity,
                defaults={
                    "resource": unit.resource,
                    "date": datetime.date.today(),
                    "duration_minutes": new_duration,
                    "status": StudySession.Status.LOGGED,
                },
            )

        return JsonResponse({"ok": True, "unit": unit.to_inline_dict()})
