from calendar import Calendar
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from core.permissions import can_manage_meetings

from .models import Meeting


def get_visible_meetings(user):
    queryset = Meeting.objects.select_related(
        "organisee_par",
        "validee_par",
    ).prefetch_related(
        "services_concernes",
        "membres_invites",
    )

    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    if can_manage_meetings(user):
        return queryset.distinct()

    profile = getattr(user, "profil", None)
    service = getattr(profile, "service", None)

    filters = Q(membres_invites=user) | Q(organisee_par=user)
    if service:
        filters |= Q(services_concernes=service)

    return queryset.filter(filters).exclude(statut=Meeting.Status.BROUILLON).distinct()


def get_next_meeting_for_user(user):
    return (
        get_visible_meetings(user)
        .filter(
            statut=Meeting.Status.VALIDEE,
            date_heure__gte=timezone.now(),
        )
        .order_by("date_heure")
        .first()
    )


def _get_day_bounds(day):
    current_timezone = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(day, time.min), current_timezone)
    day_end = timezone.make_aware(datetime.combine(day, time.max), current_timezone)
    return day_start, day_end


def get_week_bounds(anchor_day):
    week_start = anchor_day - timedelta(days=anchor_day.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_meetings_for_day(queryset, day):
    day_start, day_end = _get_day_bounds(day)
    return queryset.filter(date_heure__range=(day_start, day_end)).order_by("date_heure")


def get_meetings_for_week(queryset, anchor_day):
    week_start, week_end = get_week_bounds(anchor_day)
    period_start, _ = _get_day_bounds(week_start)
    _, period_end = _get_day_bounds(week_end)
    return queryset.filter(date_heure__range=(period_start, period_end)).order_by("date_heure")


def build_calendar_weeks(queryset, anchor_day):
    calendar_weeks = Calendar(firstweekday=0).monthdatescalendar(anchor_day.year, anchor_day.month)
    visible_days = [day for week in calendar_weeks for day in week]
    period_start, _ = _get_day_bounds(min(visible_days))
    _, period_end = _get_day_bounds(max(visible_days))

    meetings = queryset.filter(date_heure__range=(period_start, period_end)).order_by("date_heure")
    meetings_by_day = defaultdict(list)
    for meeting in meetings:
        meetings_by_day[timezone.localtime(meeting.date_heure).date()].append(meeting)

    today = timezone.localdate()
    weeks = []
    for week in calendar_weeks:
        weeks.append(
            [
                {
                    "date": day,
                    "in_month": day.month == anchor_day.month,
                    "is_today": day == today,
                    "meetings": meetings_by_day.get(day, []),
                }
                for day in week
            ]
        )
    return weeks
