from django.db.models import Sum

from learning.models import LearningResource

from .utils import calculate_percentage


def get_resource_progress(resource: LearningResource) -> dict[str, int]:
    """
    Calculate progress statistics for a learning resource.
    """
    units = resource.units.all().order_by("order")

    total_units = units.count()
    completed_units = units.filter(status="completed").count()
    remaining_units = total_units - completed_units

    is_reading = resource.resource_type.content_kind == "reading"

    total_duration = units.aggregate(total=Sum("duration_minutes"))["total"] or 0

    completed_duration = (
        units.filter(status="completed").aggregate(total=Sum("duration_minutes"))[
            "total"
        ]
        or 0
    )

    # Also count video_progress_minutes for in-progress units towards time done
    in_progress_duration = (
        units.filter(status="in_progress").aggregate(
            total=Sum("video_progress_minutes")
        )["total"]
        or 0
    )

    time_done = completed_duration + in_progress_duration
    remaining_duration = total_duration - time_done

    # Use time-based percentage when durations are available; fall back to unit count
    if total_duration > 0:
        completion_percentage = calculate_percentage(time_done, total_duration)
    else:
        completion_percentage = calculate_percentage(completed_units, total_units)

    # Reading-specific stats: sum of per-chapter logged minutes
    time_read_total = 0
    chapters_with_read = 0
    if is_reading:
        agg = units.filter(status="completed").aggregate(total=Sum("reading_minutes"))
        time_read_total = agg["total"] or 0
        chapters_with_read = units.filter(
            status="completed",
            reading_minutes__isnull=False,
            reading_minutes__gt=0,
        ).count()

    return {
        "units": units,
        "total_units": total_units,
        "completed_units": completed_units,
        "remaining_units": remaining_units,
        "completion_percentage": completion_percentage,
        "total_duration": total_duration,
        "completed_duration": time_done,
        "remaining_duration": remaining_duration,
        "is_reading": is_reading,
        "time_read_total": time_read_total,
        "chapters_with_read": chapters_with_read,
    }
