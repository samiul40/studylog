from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from learning.services.dashboard import get_dashboard_stats


@login_required
def dashboard_view(request):
    resource_type = request.GET.get("type")
    stats = get_dashboard_stats(
        user=request.user,
        resource_type=resource_type,
    )

    local_now = timezone.localtime()
    hour = local_now.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    first_name = request.user.first_name or request.user.username
    today_label = local_now.strftime("%a %-d %b %Y")

    return render(
        request,
        "dashboard/dashboard.html",
        {
            **stats,
            "greeting": greeting,
            "first_name": first_name,
            "today_label": today_label,
        },
    )
