from typing import List, Optional, TypedDict


class ResourceProgress(TypedDict):
    id: int
    title: str
    percent: int


class WeekActivity(TypedDict):
    """One bar in the weekly chart. height_pct is 0–100 relative to the max week."""

    label: str
    count: int
    is_current: bool  # True for the current ISO week (renders green)
    height_pct: int  # proportional bar height; max week = 100


class DailyCompletion(TypedDict):
    label: str
    count: int


class WeeklySummary(TypedDict):
    units_completed: int
    learning_time_minutes: int
    resources_worked_on: int
    daily_completions: List[DailyCompletion]


class BacklogStats(TypedDict):
    total: int
    completed: int
    in_progress: int
    not_started: int
    pct: int
    completed_pct: int
    in_progress_pct: int
    not_started_pct: int


class TimeInvested(TypedDict):
    this_week: str
    this_week_raw: int
    this_month: str
    all_time: str


class StaleResource(TypedDict):
    title: str
    type_name: str
    type_slug: str
    content_kind: str
    idle_days: int
    url: str


class MomentumStats(TypedDict):
    """This-week vs last-week. *_pct are bar widths relative to the bigger week.
    delta_dir: 'up' | 'down' | 'new' (last week was zero)."""

    units_this_week: int
    units_last_week: int
    units_delta_pct: int  # absolute % change vs last week
    units_delta_dir: str  # 'up' | 'down' | 'new'
    units_this_pct: int  # bar width 0-100, relative to larger week
    units_last_pct: int
    time_this_week: int  # raw minutes
    time_last_week: int
    time_this_week_display: str  # formatted e.g. "2h 10m"
    time_last_week_display: str
    time_delta_pct: int
    time_delta_dir: str
    time_this_pct: int
    time_last_pct: int


class HeatmapCell(TypedDict):
    """One day cell. level 0–4 (0=none/future, 4=4+ units).
    show=False for padding days outside the current year."""

    date: str  # ISO date string, empty for out-of-year padding cells
    label: str  # human-readable e.g. "12 Jun 2026"
    count: int  # units completed that day (0 for future/out-of-year)
    level: int  # activity intensity 0–4
    in_year: bool
    show: bool


class HeatmapMonthLabel(TypedDict):
    label: str  # e.g. "Jan"
    col: int  # zero-based column index in the grid
    left_px: int  # precomputed pixel offset (col * 16) for CSS positioning


class HeatmapData(TypedDict):
    """Full-year heatmap. weeks is Monday-start columns, each with 7 cells (Mon→Sun)."""

    year: int
    weeks: List[List[HeatmapCell]]
    month_labels: List[HeatmapMonthLabel]
    total_units: int
    active_days: int


class ResourceTableRow(TypedDict):
    id: int
    title: str
    type_name: str
    type_slug: str
    content_kind: str
    total_units: int
    completed_units: int
    pct: int
    pace_display: str
    pace_float: float
    last_activity: str
    idle_days: Optional[int]
    is_idle: bool
    est_finish: str
    url: str


class DashboardStats(TypedDict):
    # --- legacy keys (used by admin dashboard) ---
    total_resources: int
    total_units: int
    completed_units: int
    incomplete_units: int
    completion_rate: int
    resource_progress: List[ResourceProgress]
    most_progress: Optional[ResourceProgress]
    least_progress: Optional[ResourceProgress]
    recent_resources: list
    active_filter: Optional[str]
    resource_types_with_counts: list
    weekly_completions: list
    weekly_summary: WeeklySummary

    in_progress_count: int
    study_streak: int
    month_started: int
    month_finished: int
    weekly_activity: List[WeekActivity]
    backlog: BacklogStats
    time_invested: TimeInvested
    stale_resources: List[StaleResource]
    momentum: MomentumStats
    heatmap: HeatmapData
    resources_table: List[ResourceTableRow]
    greeting_headline: Optional[str]
