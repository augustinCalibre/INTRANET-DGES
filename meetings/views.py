from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Notification
from core.permissions import can_manage_all_meetings, can_manage_meetings, is_admin_user
from core.utils import log_activity, safe_next_url

from .forms import MeetingForm, SalleForm
from .models import Meeting, Salle
from .selectors import (
    build_calendar_weeks,
    get_meetings_for_day,
    get_meetings_for_week,
    get_next_meeting_for_user,
    get_visible_meetings,
    get_week_bounds,
)
from .services import (
    build_countdown_label,
    create_meeting_notifications,
    dispatch_due_meeting_reminders,
    get_room_occupancy,
    reset_meeting_reminders,
)

FRENCH_MONTHS = {
    1: "Janvier",
    2: "Fevrier",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Aout",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Decembre",
}


def can_modify_meeting(meeting, user):
    """Chacun gere ses propres reunions ; le secretariat gere celles de tous.

    Le planning du Directeur General releve du secretariat, mais un agent
    reste maitre des reunions qu'il a lui-meme organisees.
    """
    if can_manage_all_meetings(user):
        return True
    return meeting.organisee_par_id == getattr(user, "id", None)


def _mark_notifications_as_read(user):
    Notification.objects.filter(
        utilisateur=user,
        type_notification=Notification.Type.MEETING,
        lu=False,
    ).update(
        lu=True,
        date_lecture=timezone.now(),
    )


def _meeting_targets_label(meeting):
    services = list(meeting.services_concernes.values_list("nom", flat=True))
    members = [
        member.get_full_name().strip() or member.username
        for member in meeting.membres_invites.all()
    ]
    return ", ".join(services + members) or "Sans cible"


def _parse_month_anchor(raw_value):
    if raw_value:
        try:
            return datetime.strptime(raw_value, "%Y-%m").date().replace(day=1)
        except ValueError:
            pass
    return timezone.localdate().replace(day=1)


def _format_month_label(day_value):
    return f"{FRENCH_MONTHS[day_value.month]} {day_value.year}"


def _get_filtered_meetings(request):
    status_filter = request.GET.get("statut", "").strip()
    search_term = request.GET.get("q", "").strip()
    meetings = get_visible_meetings(request.user)

    if status_filter:
        meetings = meetings.filter(statut=status_filter)
    if search_term:
        meetings = meetings.filter(
            Q(titre__icontains=search_term)
            | Q(description__icontains=search_term)
            | Q(salle_reservee__nom__icontains=search_term)
            | Q(services_concernes__nom__icontains=search_term)
            | Q(membres_invites__first_name__icontains=search_term)
            | Q(membres_invites__last_name__icontains=search_term)
            | Q(membres_invites__username__icontains=search_term)
        ).distinct()

    return meetings, status_filter, search_term


def _build_shared_meeting_context(request, meetings):
    today = timezone.localdate()
    week_start, week_end = get_week_bounds(today)
    next_meeting = get_next_meeting_for_user(request.user)
    reminder_notifications = Notification.objects.filter(
        utilisateur=request.user,
        type_notification=Notification.Type.MEETING,
        titre__istartswith="Rappel",
    )[:5]

    return {
        "status_choices": Meeting.Status.choices,
        "can_manage_meetings": can_manage_meetings(request.user),
        "can_delete_meetings": is_admin_user(request.user),
        "next_meeting": next_meeting,
        "next_meeting_countdown": build_countdown_label(next_meeting),
        "today_meetings": get_meetings_for_day(meetings, today),
        "week_meetings": get_meetings_for_week(meetings, today),
        "today_label": today,
        "week_start": week_start,
        "week_end": week_end,
        "reminder_notifications": reminder_notifications,
        "current_time": timezone.now(),
    }


@login_required
def meeting_list(request):
    dispatch_due_meeting_reminders()
    _mark_notifications_as_read(request.user)

    meetings, status_filter, search_term = _get_filtered_meetings(request)
    context = {
        "meetings": meetings,
        "status_filter": status_filter,
        "search_term": search_term,
        "active_view": "list",
    }
    context.update(_build_shared_meeting_context(request, meetings))
    return render(request, "meetings/list.html", context)


@login_required
def meeting_calendar(request):
    dispatch_due_meeting_reminders()
    meetings, status_filter, search_term = _get_filtered_meetings(request)
    month_anchor = _parse_month_anchor(request.GET.get("month", "").strip())
    previous_month = (month_anchor.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (month_anchor.replace(day=28) + timedelta(days=4)).replace(day=1)

    context = {
        "meetings": meetings,
        "status_filter": status_filter,
        "search_term": search_term,
        "active_view": "calendar",
        "month_anchor": month_anchor,
        "month_label": _format_month_label(month_anchor),
        "previous_month": previous_month,
        "next_month": next_month,
        "calendar_weeks": build_calendar_weeks(meetings, month_anchor),
        "weekdays": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
    }
    context.update(_build_shared_meeting_context(request, meetings))
    return render(request, "meetings/calendar.html", context)


@login_required
def meeting_create(request):
    # Ouvert a tout agent : chacun organise ses propres reunions. Le
    # secretariat conserve la main sur celles des autres et sur le planning
    # du Directeur General.
    if request.method == "POST":
        form = MeetingForm(request.POST)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.organisee_par = request.user
            reset_meeting_reminders(meeting)

            if meeting.statut == Meeting.Status.VALIDEE:
                meeting.validee_par = request.user
                meeting.date_validation = timezone.now()

            meeting.save()
            form.save_m2m()

            if meeting.statut == Meeting.Status.VALIDEE:
                create_meeting_notifications(meeting, mode="validation")

            log_activity(request.user, "Creation d'une reunion", "Reunions", meeting.titre)
            messages.success(request, "La reunion a ete enregistree.")
            return redirect("meetings:list")
    else:
        form = MeetingForm()

    return render(
        request,
        "meetings/form.html",
        {
            "form": form,
            "title": "Programmer une reunion",
            "is_creation": True,
        },
    )


@login_required
def meeting_edit(request, pk):
    meeting = get_object_or_404(get_visible_meetings(request.user), pk=pk)
    if not can_modify_meeting(meeting, request.user):
        raise PermissionDenied

    previous_status = meeting.statut
    previous_date = meeting.date_heure
    previous_room = meeting.salle
    previous_title = meeting.titre
    previous_service_ids = set(meeting.services_concernes.values_list("id", flat=True))
    previous_member_ids = set(meeting.membres_invites.values_list("id", flat=True))

    if request.method == "POST":
        form = MeetingForm(request.POST, instance=meeting)
        if form.is_valid():
            meeting = form.save(commit=False)
            planning_changed = any(
                [
                    previous_date != meeting.date_heure,
                    previous_room != meeting.salle,
                    previous_title != meeting.titre,
                ]
            )

            if meeting.statut == Meeting.Status.VALIDEE and previous_status != Meeting.Status.VALIDEE:
                meeting.validee_par = request.user
                meeting.date_validation = timezone.now()

            if planning_changed or previous_status != meeting.statut:
                reset_meeting_reminders(meeting)

            meeting.save()
            form.save_m2m()

            current_service_ids = set(meeting.services_concernes.values_list("id", flat=True))
            current_member_ids = set(meeting.membres_invites.values_list("id", flat=True))

            targeting_changed = any(
                [
                    previous_service_ids != current_service_ids,
                    previous_member_ids != current_member_ids,
                ]
            )
            notification_changed = planning_changed or targeting_changed

            if meeting.statut == Meeting.Status.ANNULEE and previous_status != Meeting.Status.ANNULEE:
                create_meeting_notifications(meeting, mode="annulation")
            elif meeting.statut == Meeting.Status.REPORTEE and (
                previous_status != Meeting.Status.REPORTEE or notification_changed
            ):
                create_meeting_notifications(meeting, mode="report")
            elif meeting.statut == Meeting.Status.VALIDEE and (
                previous_status != Meeting.Status.VALIDEE or notification_changed
            ):
                create_meeting_notifications(
                    meeting,
                    mode="mise_a_jour" if previous_status in {Meeting.Status.VALIDEE, Meeting.Status.REPORTEE} else "validation",
                )

            log_activity(request.user, "Mise a jour d'une reunion", "Reunions", meeting.titre)
            messages.success(request, "La reunion a ete mise a jour.")
            return redirect("meetings:list")
    else:
        form = MeetingForm(instance=meeting)

    return render(
        request,
        "meetings/form.html",
        {
            "form": form,
            "title": f"Modifier {meeting.titre}",
            "meeting": meeting,
            "is_creation": False,
        },
    )


@login_required
@require_POST
def meeting_status_update(request, pk, status):
    allowed_statuses = {Meeting.Status.TENUE, Meeting.Status.VALIDEE}
    if status not in allowed_statuses:
        raise PermissionDenied

    meeting = get_object_or_404(get_visible_meetings(request.user), pk=pk)
    if not can_modify_meeting(meeting, request.user):
        raise PermissionDenied
    redirect_to = safe_next_url(request, request.POST.get("next"), "meetings:list")

    if status == Meeting.Status.TENUE and meeting.date_heure > timezone.now():
        messages.error(request, "La reunion doit avoir commence avant d'etre marquee comme tenue.")
        return redirect(redirect_to)

    if status == Meeting.Status.VALIDEE and meeting.date_heure <= timezone.now():
        messages.error(request, "La reunion reportee doit etre reprogrammee dans le futur avant validation.")
        return redirect(redirect_to)

    if meeting.statut == status:
        messages.info(request, "Le statut de cette reunion est deja a jour.")
        return redirect(redirect_to)

    previous_status = meeting.statut
    meeting.statut = status

    if status == Meeting.Status.VALIDEE:
        meeting.validee_par = request.user
        meeting.date_validation = timezone.now()
        reset_meeting_reminders(meeting)
        meeting.save(update_fields=["statut", "validee_par", "date_validation", "rappel_60_envoye_at", "rappel_15_envoye_at", "updated_at"])
        create_meeting_notifications(
            meeting,
            mode="mise_a_jour" if previous_status == Meeting.Status.REPORTEE else "validation",
        )
        messages.success(request, "La reunion a ete revalidee.")
    else:
        meeting.save(update_fields=["statut", "updated_at"])
        messages.success(request, "La reunion a ete marquee comme tenue.")

    log_activity(request.user, f"Changement de statut reunion : {previous_status} -> {status}", "Reunions", meeting.titre)
    return redirect(redirect_to)


# ----------------------------------------------------------------- salles


@login_required
def salle_list(request):
    """Etat des salles : libre, occupee, prochaine reservation."""
    salles = Salle.objects.all().prefetch_related("reunions")
    occupations = [get_room_occupancy(salle) for salle in salles]

    return render(
        request,
        "meetings/salle_list.html",
        {
            "occupations": occupations,
            "total_salles": len(occupations),
            "total_occupees": sum(1 for item in occupations if item["occupee"]),
            "can_manage_salles": can_manage_all_meetings(request.user),
            "can_delete": is_admin_user(request.user),
            "current_time": timezone.now(),
        },
    )


@login_required
def salle_create(request):
    if not can_manage_all_meetings(request.user):
        raise PermissionDenied

    if request.method == "POST":
        form = SalleForm(request.POST)
        if form.is_valid():
            salle = form.save()
            log_activity(request.user, "Creation d'une salle", "Reunions", salle.nom)
            messages.success(request, f"La salle {salle.nom} a ete enregistree.")
            return redirect("meetings:salle_list")
    else:
        form = SalleForm()

    return render(
        request,
        "meetings/salle_form.html",
        {"form": form, "title": "Nouvelle salle", "is_creation": True},
    )


@login_required
def salle_edit(request, pk):
    if not can_manage_all_meetings(request.user):
        raise PermissionDenied

    salle = get_object_or_404(Salle, pk=pk)
    if request.method == "POST":
        form = SalleForm(request.POST, instance=salle)
        if form.is_valid():
            salle = form.save()
            log_activity(request.user, "Mise a jour d'une salle", "Reunions", salle.nom)
            messages.success(request, "La salle a ete mise a jour.")
            return redirect("meetings:salle_list")
    else:
        form = SalleForm(instance=salle)

    return render(
        request,
        "meetings/salle_form.html",
        {"form": form, "salle": salle, "title": f"Modifier {salle.nom}", "is_creation": False},
    )


@login_required
@require_POST
def salle_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    salle = get_object_or_404(Salle, pk=pk)
    reservations = salle.reunions.count()
    if reservations:
        messages.error(
            request,
            f"La salle {salle.nom} est rattachée à {reservations} réunion(s) : "
            "désactivez-la plutôt que de la supprimer, l'historique doit rester lisible.",
        )
        return redirect("meetings:salle_list")

    nom = salle.nom
    salle.delete()
    log_activity(request.user, "Suppression d'une salle", "Reunions", nom)
    messages.success(request, f"La salle {nom} a ete supprimee.")
    return redirect("meetings:salle_list")


@login_required
@require_POST
def meeting_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    meeting = get_object_or_404(Meeting, pk=pk)
    meeting_title = meeting.titre
    meeting.delete()
    log_activity(request.user, "Suppression d'une reunion", "Reunions", meeting_title)
    messages.success(request, "La reunion a ete supprimee.")
    return redirect(safe_next_url(request, request.POST.get("next"), "meetings:list"))
