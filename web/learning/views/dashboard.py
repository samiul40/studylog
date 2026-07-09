from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from learning.services.dashboard import get_dashboard_stats


def _build_sessions_area_chart(session_weekly_chart):
    """Precompute SVG path data for the sessions-per-week chart.

    Shows all 8 data points (including zero weeks) — every point carries a dot
    and value label per the v6 design spec.
    viewBox: 0 0 800 205. Baseline Y=170, top Y=20.
    """
    if not session_weekly_chart:
        return None

    n = len(session_weekly_chart)
    x_start, x_end = 20, 780
    y_base, y_top = 170, 20

    xs = [round(x_start + (x_end - x_start) * i / max(n - 1, 1), 1) for i in range(n)]
    counts = [w["count"] for w in session_weekly_chart]
    max_count = max(counts) if any(counts) else 1

    def y_for(count):
        if max_count == 0:
            return y_base
        return round(y_top + (y_base - y_top) * (1 - count / max_count), 1)

    ys = [y_for(c) for c in counts]

    coords = " ".join(f"L{xs[i]},{ys[i]}" for i in range(n))
    line_d = f"M{xs[0]},{ys[0]} {coords[2:]}"
    area_d = f"M{xs[0]},{ys[0]} {coords[2:]} L{xs[-1]},{y_base} L{xs[0]},{y_base} Z"

    points = [
        {
            "x": xs[i],
            "y": ys[i],
            "count": counts[i],
            "label": session_weekly_chart[i]["label"],
            "val_y": ys[i] - 12 if ys[i] > 26 else ys[i] + 20,
            "is_current": session_weekly_chart[i]["is_current"],
            "anchor": ("start" if i == 0 else "end" if i == n - 1 else "middle"),
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

    area_chart = _build_sessions_area_chart(stats.get("session_weekly_chart", []))

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
