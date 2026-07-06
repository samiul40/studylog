from django.db.models import F, Value
from django.db.models.functions import Greatest

from learning.models import StudySession


def upsert_resource_session(user, resource, date, activity_type, delta_minutes):
    """
    Create or update a resource-linked session keyed on
    (user, resource, date, activity_type).

    delta_minutes semantics:
      > 0  — forward progress: create or increment existing session
      < 0  — backward correction (slider moved back): decrement, floored at 0
      = 0  — reading logged without a tracked duration: create if not exists
      None — no-op, returns None

    Same-day example (video):
      Slider 0→5  today → delta=5,  new session duration=5
      Slider 5→20 today → delta=15, same session updated to 20
    Cross-day example:
      Slider 20→30 tomorrow → delta=10, NEW session for tomorrow, duration=10
    Backward correction:
      Slider 20→10 same day → delta=-10, session decremented to max(0, 10)
    """
    if delta_minutes is None:
        return None

    qs = StudySession.objects.filter(
        user=user,
        resource=resource,
        date=date,
        activity_type=activity_type,
    )

    if delta_minutes > 0:
        session, created = StudySession.objects.get_or_create(
            user=user,
            resource=resource,
            date=date,
            activity_type=activity_type,
            defaults={"duration_minutes": delta_minutes},
        )
        if not created:
            qs.update(duration_minutes=F("duration_minutes") + delta_minutes)
    elif delta_minutes < 0:
        qs.update(
            duration_minutes=Greatest(
                Value(0), F("duration_minutes") + delta_minutes
            )
        )
    else:
        # delta=0: reading completion logged without a timed duration
        StudySession.objects.get_or_create(
            user=user,
            resource=resource,
            date=date,
            activity_type=activity_type,
            defaults={"duration_minutes": 0},
        )

    return qs.first()
