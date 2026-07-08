import calendar as _calendar
import datetime

from django.db.models import Count, F, QuerySet, Sum, Value
from django.db.models.functions import Greatest

from learning.models import StudySession
from learning.services.types import CalendarData, DayData


def upsert_resource_session(
    user, resource, date, activity_type, delta_minutes, unit=None
):
    """
    Create or update a session keyed on (user, resource, unit, date, activity_type).

    ``unit`` should be passed for auto-logged sessions (video watch, reading) so
    each learning unit gets its own row.  Manual sessions leave ``unit=None``.

    delta_minutes semantics:
      > 0  — forward progress: create or increment existing session
      < 0  — backward correction (slider moved back): decrement, floored at 0
      = 0  — reading logged without a tracked duration: create if not exists
      None — no-op, returns None

    Same-day example (video, unit provided):
      Slider 0→5  today → delta=5,  new row for (unit, today)
      Slider 5→20 today → delta=15, same row updated to 20
    Cross-day example:
      Slider 20→30 tomorrow → delta=10, NEW row for (unit, tomorrow)
    Backward correction:
      Slider 20→10 same day → delta=-10, row decremented to max(0, 10)
    """
    if delta_minutes is None:
        return None

    qs = StudySession.objects.filter(
        user=user,
        resource=resource,
        unit=unit,
        date=date,
        activity_type=activity_type,
    )

    if delta_minutes > 0:
        session, created = StudySession.objects.get_or_create(
            user=user,
            resource=resource,
            unit=unit,
            date=date,
            activity_type=activity_type,
            defaults={"duration_minutes": delta_minutes},
        )
        if not created:
            qs.update(duration_minutes=F("duration_minutes") + delta_minutes)
    elif delta_minutes < 0:
        qs.update(
            duration_minutes=Greatest(Value(0), F("duration_minutes") + delta_minutes)
        )
    else:
        # delta=0: reading completion logged without a timed duration
        StudySession.objects.get_or_create(
            user=user,
            resource=resource,
            unit=unit,
            date=date,
            activity_type=activity_type,
            defaults={"duration_minutes": 0},
        )

    return qs.first()


def get_month_calendar(
    session_qs: QuerySet,
    year: int,
    month: int,
) -> CalendarData:
    """
    Return calendar grid data for the given month.

    Runs two aggregate queries (done sessions, planned sessions) and merges
    them into a flat list of per-day objects. The caller can serialise this
    directly to JSON for both the SSR page and AJAX month-navigation.
    """
    today = datetime.date.today()

    done_qs = session_qs.filter(status=StudySession.Status.LOGGED)
    daily_done_mins: dict[datetime.date, int] = {}
    daily_done_count: dict[datetime.date, int] = {}
    for row in (
        done_qs.for_month(year, month)
        .values("date")
        .annotate(total=Sum("duration_minutes"), cnt=Count("id"))
    ):
        daily_done_mins[row["date"]] = row["total"]
        daily_done_count[row["date"]] = row["cnt"]

    planned_qs = session_qs.filter(status=StudySession.Status.PLANNED)
    daily_planned: dict[datetime.date, int] = {}
    for row in (
        planned_qs.for_month(year, month).values("date").annotate(cnt=Count("id"))
    ):
        daily_planned[row["date"]] = row["cnt"]

    first_of_month = datetime.date(year, month, 1)
    # Python weekday() is 0=Mon … 6=Sun — matches Monday-first grid directly.
    start_offset: int = first_of_month.weekday()

    days_in_month = _calendar.monthrange(year, month)[1]
    days = []
    for d in range(1, days_in_month + 1):
        dt = datetime.date(year, month, d)
        done_mins = daily_done_mins.get(dt, 0)
        done_count = daily_done_count.get(dt, 0)
        planned_count = daily_planned.get(dt, 0)
        days.append(
            {
                "day": d,
                "date": dt.isoformat(),
                "done_minutes": done_mins,
                "done_count": done_count,
                "planned_count": planned_count,
                "overdue": planned_count > 0 and dt < today,
                "is_today": dt == today,
                "is_future": dt > today,
            }
        )

    total_mins = sum(daily_done_mins.values())
    active_days = sum(1 for t in daily_done_mins.values() if t > 0)

    prev_date = datetime.date(year, month, 1) - datetime.timedelta(days=1)
    next_date = datetime.date(year, month, 28) + datetime.timedelta(days=4)

    return CalendarData(
        year=year,
        month=month,
        month_name=first_of_month.strftime("%B %Y"),
        start_offset=start_offset,
        days=days,
        total_minutes=total_mins,
        active_days=active_days,
        prev_year=prev_date.year,
        prev_month=prev_date.month,
        next_year=next_date.year,
        next_month=next_date.month,
    )


def get_day_sessions(
    session_qs: QuerySet,
    date: datetime.date,
) -> DayData:
    """
    Return all sessions for a given date, annotated with overdue status.

    Planned sessions whose date is before today are marked is_overdue=True
    so the day panel can render "Missed" badges and swap buttons.
    """
    today = datetime.date.today()
    sessions = list(
        session_qs.filter(date=date).select_related("resource").order_by("created_at")
    )

    result = []
    for s in sessions:
        d = s.to_dict()
        d["is_overdue"] = s.status == StudySession.Status.PLANNED and date < today
        result.append(d)

    done_sessions = [s for s in result if s["status"] == "logged"]
    planned_sessions = [s for s in result if s["status"] == "planned"]

    return DayData(
        day_sessions=result,
        day_done_count=len(done_sessions),
        day_total_minutes=sum(s["duration_minutes"] for s in done_sessions),
        day_planned_count=len(planned_sessions),
    )
