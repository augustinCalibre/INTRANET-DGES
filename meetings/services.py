from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import Notification

from .models import Meeting


def find_room_conflicts(salle, debut, duree_minutes=60, exclude_pk=None):
    """Reunions qui occupent deja cette salle sur le creneau demande.

    Le chevauchement est evalue en Python plutot qu'en SQL : calculer une fin
    de reunion en base demanderait une expression de duree variable, mal
    portable entre SQLite et PostgreSQL. Le nombre de reunions par salle et
    par jour etant faible, on presele une fenetre puis on filtre.
    """
    if not salle or not debut:
        return []

    fin = debut + timedelta(minutes=duree_minutes or 60)
    fenetre_debut = debut - timedelta(minutes=Meeting.DUREE_MAX_MINUTES)

    candidats = (
        Meeting.objects.filter(
            salle_reservee=salle,
            statut__in=Meeting.OCCUPYING_STATUSES,
            date_heure__lt=fin,
            date_heure__gt=fenetre_debut,
        )
        .select_related("organisee_par")
        .order_by("date_heure")
    )
    if exclude_pk:
        candidats = candidats.exclude(pk=exclude_pk)

    return [reunion for reunion in candidats if reunion.date_fin > debut]


def get_room_occupancy(salle, now=None):
    """Etat d'occupation d'une salle : en cours et prochaine reservation."""
    now = now or timezone.now()

    en_cours = None
    for reunion in (
        salle.reunions.filter(
            statut__in=Meeting.OCCUPYING_STATUSES,
            date_heure__lte=now,
            date_heure__gt=now - timedelta(minutes=Meeting.DUREE_MAX_MINUTES),
        )
        .select_related("organisee_par")
        .order_by("-date_heure")
    ):
        if reunion.date_fin > now:
            en_cours = reunion
            break

    prochaine = (
        salle.reunions.filter(
            statut__in=Meeting.OCCUPYING_STATUSES,
            date_heure__gt=now,
        )
        .select_related("organisee_par")
        .order_by("date_heure")
        .first()
    )

    return {
        "salle": salle,
        "occupee": en_cours is not None,
        "reunion_en_cours": en_cours,
        "prochaine_reunion": prochaine,
    }


def format_meeting_datetime(value):
    local_value = timezone.localtime(value)
    return local_value.strftime("%d/%m/%Y a %H:%M")


def get_meeting_recipients(meeting):
    service_ids = meeting.services_concernes.values_list("id", flat=True)
    member_ids = meeting.membres_invites.values_list("id", flat=True)

    users = User.objects.filter(is_active=True, profil__actif=True)
    users = users.filter(models.Q(id__in=member_ids) | models.Q(profil__service_id__in=service_ids))
    return users.distinct()


def create_meeting_notifications(meeting, mode="validation"):
    recipients = get_meeting_recipients(meeting)
    meeting_url = reverse("meetings:list")
    when_label = format_meeting_datetime(meeting.date_heure)

    if mode == "annulation":
        title = f"Reunion annulee : {meeting.titre}"
        message = f"La reunion prevue le {when_label} en salle {meeting.salle} a ete annulee."
    elif mode == "report":
        title = f"Reunion reportee : {meeting.titre}"
        message = f"La reunion est reportee. Nouvelle programmation : {when_label} en salle {meeting.salle}."
    elif mode == "rappel_60":
        title = f"Rappel reunion dans 1 heure : {meeting.titre}"
        message = f"Rappel interne : reunion prevue a {when_label} en salle {meeting.salle}."
    elif mode == "rappel_15":
        title = f"Rappel reunion imminente : {meeting.titre}"
        message = f"Votre reunion commence bientot, a {when_label} en salle {meeting.salle}."
    elif mode == "mise_a_jour":
        title = f"Reunion mise a jour : {meeting.titre}"
        message = f"La reunion validee est desormais fixee au {when_label} en salle {meeting.salle}."
    else:
        title = f"Nouvelle reunion validee : {meeting.titre}"
        message = f"Vous etes concerne par une reunion programmee le {when_label} en salle {meeting.salle}."

    notifications = [
        Notification(
            utilisateur=user,
            type_notification=Notification.Type.MEETING,
            titre=title,
            message=message,
            url=meeting_url,
        )
        for user in recipients
    ]
    Notification.objects.bulk_create(notifications)


def reset_meeting_reminders(meeting):
    meeting.rappel_60_envoye_at = None
    meeting.rappel_15_envoye_at = None


def dispatch_due_meeting_reminders():
    now = timezone.now()
    reminder_windows = (
        ("rappel_60_envoye_at", timedelta(minutes=60), timedelta(minutes=15), "rappel_60"),
        ("rappel_15_envoye_at", timedelta(minutes=15), timedelta(seconds=0), "rappel_15"),
    )

    for field_name, upper_bound, lower_bound, mode in reminder_windows:
        queryset = (
            Meeting.objects.filter(
                statut=Meeting.Status.VALIDEE,
                date_heure__gt=now + lower_bound,
                date_heure__lte=now + upper_bound,
                **{f"{field_name}__isnull": True},
            )
            .prefetch_related("services_concernes", "membres_invites")
            .order_by("date_heure")
        )

        for meeting in queryset:
            updated = Meeting.objects.filter(
                pk=meeting.pk,
                **{f"{field_name}__isnull": True},
            ).update(**{field_name: now})
            if not updated:
                continue

            setattr(meeting, field_name, now)
            create_meeting_notifications(meeting, mode=mode)


def build_countdown_label(meeting):
    if not meeting:
        return ""

    delta = timezone.localtime(meeting.date_heure) - timezone.localtime(timezone.now())
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "Reunion imminente"

    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    if days > 0:
        return f"Dans {days} j {hours} h"
    if hours > 0:
        return f"Dans {hours} h {minutes} min"
    return f"Dans {minutes} min"
