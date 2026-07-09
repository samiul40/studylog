import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# SVG icons keyed by activity slug — used in the recent sessions feed.
_ACTIVITY_ICONS = {
    "flashcards": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="7" width="14" height="12" rx="2"></rect>'
        '<path d="M7 4h13a1 1 0 0 1 1 1v11"></path></svg>'
    ),
    "practice": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 11l3 3L22 4"></path>'
        '<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1'
        ' 2-2h11"></path></svg>'
    ),
    "pastpapers": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0'
        ' 2-2V8z"></path>'
        '<path d="M14 2v6h6M8 13h8M8 17h5"></path></svg>'
    ),
    "review": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M2 4h7a3 3 0 0 1 3 3v13a2.5 2.5 0 0 0-2.5-2.5H2z">'
        "</path>"
        '<path d="M22 4h-7a3 3 0 0 0-3 3v13a2.5 2.5 0 0 1'
        ' 2.5-2.5H22z"></path></svg>'
    ),
    "writing": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 20h9"></path>'
        '<path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z">'
        "</path></svg>"
    ),
    "watch": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="5 3 19 12 5 21 5 3"></polygon></svg>'
    ),
    "read": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M2 4h7a3 3 0 0 1 3 3v13a2.5 2.5 0 0 0-2.5-2.5H2z">'
        "</path>"
        '<path d="M22 4h-7a3 3 0 0 0-3 3v13a2.5 2.5 0 0 1'
        ' 2.5-2.5H22z"></path></svg>'
    ),
}
_DEFAULT_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="9"></circle>'
    '<path d="M12 7v5l3 2"></path></svg>'
)


@register.simple_tag
def activity_icon(slug):
    """Return an inline SVG icon for the given activity slug."""
    return mark_safe(_ACTIVITY_ICONS.get(slug, _DEFAULT_ICON))


@register.filter
def format_duration(minutes):
    """Convert a total-minutes integer to a human-readable string.

    Examples: 0 → "0m", 45 → "45m", 90 → "1h 30m", 120 → "2h"
    """
    if not minutes:
        return "0m"
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


@register.filter
def hours_from_minutes(minutes):
    """Whole-hours component of a minutes value. Returns 0 for falsy input."""
    if not minutes:
        return 0
    return int(minutes) // 60


@register.filter
def remaining_mins(minutes):
    """Sub-hour minutes component. Returns 0 for falsy input."""
    if not minutes:
        return 0
    return int(minutes) % 60


@register.filter
def ring_offset(pct, circumference):
    """SVG stroke-dashoffset for a given circumference and percentage."""
    c = float(circumference)
    offset = c * (1 - (int(pct) if pct else 0) / 100)
    return f"{offset:.1f}"


@register.filter
def ring_offset_pct(done, total):
    """Return a 0-100 integer percentage given done/total minute values."""
    try:
        t = int(total or 0)
        d = int(done or 0)
        return min(100, round(d / t * 100)) if t else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def tojson(value):
    """Serialize a Python value to a JSON literal, safe for inline <script>."""
    return mark_safe(json.dumps(value, ensure_ascii=False))
