from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import CreateView
from django_ratelimit.decorators import ratelimit

from learning.forms import FeatureRequestForm
from learning.mixins import UserPermissionMixin
from learning.models import FeatureRequest


@method_decorator(
    ratelimit(key="user", rate="5/h", method="POST", block=False),
    name="dispatch",
)
class FeatureRequestView(UserPermissionMixin, CreateView):
    """
    Collect a feature suggestion from the logged-in user.
    """

    permission_required = "learning.add_featurerequest"
    model = FeatureRequest
    form_class = FeatureRequestForm
    template_name = "feature_requests/feature_request_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submitted"] = "submitted" in self.request.GET
        return context

    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            messages.error(
                request,
                "You've sent a few ideas recently — try again in a little while.",
            )
            return redirect("feature_request")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Thanks for the suggestion!")
        return response

    def get_success_url(self):
        return f"{reverse('feature_request')}?submitted=1"
