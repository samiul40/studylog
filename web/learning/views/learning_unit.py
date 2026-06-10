import json

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
from learning.models import LearningResource, LearningUnit


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
        except (json.JSONDecodeError, KeyError):
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
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

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

        if "notes" in data:
            unit.notes = str(data["notes"])

        try:
            unit.save()
        except ValidationError as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        return JsonResponse({"ok": True, "unit": unit.to_inline_dict()})
