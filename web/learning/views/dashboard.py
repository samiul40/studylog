from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from learning.services.dashboard import get_dashboard_stats


def _build_area_chart(weekly_activity):
    """Precompute SVG path data for the weekly area/line chart.

    viewBox is 0 0 800 205. Baseline Y=170, top Y=20.
    8 data points are spread from X=20 to X=780.
    """
    if not weekly_activity:
        return None

    n = len(weekly_activity)
    x_start, x_end = 20, 780
    y_base, y_top = 170, 20

    xs = [round(x_start + (x_end - x_start) * i / (n - 1), 1) for i in range(n)]
    counts = [w["count"] for w in weekly_activity]
    max_count = max(counts) if any(counts) else 1

    def y_for(count):
        if max_count == 0:
            return y_base
        return round(y_top + (y_base - y_top) * (1 - count / max_count), 1)

    ys = [y_for(c) for c in counts]

    coords = " ".join(f"L{xs[i]},{ys[i]}" for i in range(n))
    line_d = f"M{xs[0]},{ys[0]} {coords[2:]}"  # replace first L with M
    area_d = f"M{xs[0]},{ys[0]} {coords[2:]} L{xs[-1]},{y_base} Z"

    points = [
        {
            "x": xs[i],
            "y": ys[i],
            "count": counts[i],
            "label": weekly_activity[i]["label"],
            "val_y": max(ys[i] - 12, 8),
            "is_current": weekly_activity[i]["is_current"],
        }
        for i in range(n)
    ]

    return {
        "line_d": line_d,
        "area_d": area_d,
        "points": points,
        "y_base": y_base,
        "has_data": any(counts),
    }


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
    area_chart = _build_area_chart(stats.get("weekly_activity", []))

    return render(
        request,
        "dashboard/dashboard.html",
        {
            **stats,
            "greeting": greeting,
            "first_name": first_name,
            "today_label": today_label,
            "area_chart": area_chart,
        },
    )
