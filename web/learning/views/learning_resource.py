import json

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from learning.forms import LearningResourceForm
from learning.mixins import UserPermissionMixin
from learning.models import LearningResource, LearningUnit, ResourceType
from learning.services import get_resource_progress


class BaseUserResourceView(UserPermissionMixin):
    """
    Base view for learning resource views that restricts the queryset
    to resources owned by the currently authenticated user.
    """

    model = LearningResource

    def get_queryset(self):
        return (
            LearningResource.objects.for_user(self.request.user)
            .active()
            .order_by("-created_at")
        )


class ResourceListView(BaseUserResourceView, ListView):
    """
    Display all learning resources belonging to the logged-in user.
    """

    permission_required = "learning.view_learningresource"
    template_name = "resources/resource_list.html"
    context_object_name = "resources"

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .with_progress()
            .with_weekly_units()
            .with_time_logged()
            .select_related("user", "resource_type")
        )

        search_query = self.request.GET.get("search", "").strip()
        type_slug = self.request.GET.get("type", "").strip()

        if search_query:
            qs = qs.filter(title__icontains=search_query)

        if type_slug:
            qs = qs.filter(resource_type__slug=type_slug)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Materialise the queryset once so we can compute page-level stats
        # without hitting the DB again for each count.
        resources = list(context["resources"])
        context["resources"] = resources

        def is_in_progress(r):
            return 0 < r.percentage < 100

        def completed_this_week(r):
            return r.percentage >= 100 and getattr(r, "units_this_week", 0) > 0

        in_progress_count = sum(1 for r in resources if is_in_progress(r))
        completed_this_week_count = sum(1 for r in resources if completed_this_week(r))
        context["page_stats"] = {
            "total": len(resources),
            "in_progress": in_progress_count,
            "completed_this_week": completed_this_week_count,
        }
        context["search_query"] = self.request.GET.get("search", "")
        context["selected_type"] = self.request.GET.get("type", "")
        context["archived_count"] = (
            LearningResource.objects.for_user(self.request.user).archived().count()
        )
        context["resource_types"] = ResourceType.objects.filter(
            Q(is_system=True) | Q(user=self.request.user)
        )
        return context


class ResourceDetailView(BaseUserResourceView, DetailView):
    """
    Display details of a single learning resource.
    """

    permission_required = "learning.view_learningresource"
    template_name = "resources/resource_detail.html"
    context_object_name = "resource"

    def get_queryset(self):
        # Include archived so the user can view and unarchive from the detail.
        return (
            LearningResource.objects.for_user(self.request.user)
            .with_progress()
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_resource_progress(self.object))
        return context


class ResourceCreateView(UserPermissionMixin, CreateView):
    """
    Create a new learning resource.
    """

    permission_required = "learning.add_learningresource"
    model = LearningResource
    form_class = LearningResourceForm
    template_name = "resources/resource_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("learning:resource_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)

        youtube_units_json = form.cleaned_data.get("youtube_units", "")
        unit_count = form.cleaned_data.get("unit_count")

        if youtube_units_json:
            try:
                units_data = json.loads(youtube_units_json)
            except (json.JSONDecodeError, ValueError):
                units_data = []
            units = []
            for i, u in enumerate(units_data):
                unit = LearningUnit(
                    resource=self.object,
                    title=u.get("title") or f"Unit {i + 1}",
                    duration_minutes=u.get("duration_minutes") or None,
                    order=i + 1,
                )
                units.append(unit)
            LearningUnit.objects.bulk_create(units)
        elif unit_count:
            unit_label = self.object.resource_type.unit_label
            units = [
                LearningUnit(
                    resource=self.object,
                    title=f"{unit_label} {i + 1}",
                    order=i + 1,
                )
                for i in range(unit_count)
            ]
            LearningUnit.objects.bulk_create(units)

        messages.success(self.request, "Resource created successfully.")
        return response


class ResourceUpdateView(BaseUserResourceView, UpdateView):
    """
    Update an existing learning resource belonging to the user.
    """

    permission_required = "learning.change_learningresource"
    form_class = LearningResourceForm
    template_name = "resources/resource_form.html"

    def get_queryset(self):
        # Include archived resources so users can edit without restoring first.
        return LearningResource.objects.for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Resource updated successfully.")
        return super().form_valid(form)


class ResourceDeleteView(BaseUserResourceView, DeleteView):
    """
    Delete a learning resource belonging to the user.
    """

    permission_required = "learning.delete_learningresource"
    model = LearningResource
    template_name = "resources/resource_confirm_delete.html"
    success_url = reverse_lazy("learning:resource_list")

    def get_queryset(self):
        # Include archived resources so users can delete without restoring first.
        return LearningResource.objects.for_user(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Resource deleted successfully.")
        return super().form_valid(form)


class ResourceArchiveView(UserPermissionMixin, View):
    """
    Toggle the archived state of a learning resource (POST only).
    """

    permission_required = "learning.change_learningresource"

    def post(self, request, pk):
        resource = get_object_or_404(LearningResource, pk=pk, user=request.user)
        resource.is_archived = not resource.is_archived
        resource.save(update_fields=["is_archived", "updated_at"])
        if resource.is_archived:
            messages.success(request, "Resource archived.")
            return redirect("learning:resource_list")
        messages.success(request, "Resource unarchived.")
        return redirect(resource.get_absolute_url())


class ResourceArchiveListView(BaseUserResourceView, ListView):
    """
    Display all archived learning resources belonging to the logged-in user.
    """

    permission_required = "learning.view_learningresource"
    template_name = "resources/resource_archive_list.html"
    context_object_name = "resources"

    _SORT_MAP = {
        "-updated_at": "-updated_at",
        "updated_at": "updated_at",
        "-percentage": "-percentage",
        "percentage": "percentage",
    }

    def get_queryset(self):
        qs = (
            LearningResource.objects.for_user(self.request.user)
            .archived()
            .with_progress()
            .select_related("user", "resource_type")
        )
        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(title__icontains=search)
        sort = self.request.GET.get("sort", "-updated_at")
        return qs.order_by(self._SORT_MAP.get(sort, "-updated_at"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("search", "")
        context["sort"] = self.request.GET.get("sort", "-updated_at")
        return context
