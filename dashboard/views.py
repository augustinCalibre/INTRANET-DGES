from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from accounts.models import Service, UserProfile
from core.models import ActivityLog, Notification
from core.permissions import (
    can_access_courriers,
    can_access_diplomas,
    can_manage_meetings,
    can_transmit_to_dg,
    can_validate_as_dg,
    can_view_all_activity,
)
from courriers.models import Courrier
from courriers.selectors import (
    get_courriers_awaiting_dg,
    get_courriers_awaiting_secretariat,
    get_status_counts as get_courrier_status_counts,
    get_urgent_open_courriers,
    get_visible_courriers,
)
from diplomas.selectors import (
    get_lot_status_counts,
    get_lots_awaiting_signature,
    get_lots_with_anomalies,
    get_visible_diplomas,
    get_visible_lots,
)
from documents.selectors import get_visible_documents
from meetings.models import Meeting
from meetings.selectors import get_next_meeting_for_user, get_visible_meetings
from meetings.services import build_countdown_label, dispatch_due_meeting_reminders
from tasks.models import Task
from tasks.selectors import get_visible_tasks
from visitors.models import Visitor
from visitors.selectors import get_visible_visitors

from .charts import build_distribution, build_service_load

ACTIVE_TASK_STATUSES = [
    Task.Status.NOUVEAU,
    Task.Status.EN_ATTENTE,
    Task.Status.EN_COURS,
    Task.Status.TRAITE,
]

PERIODES = [
    ("7", "7 jours", 7),
    ("30", "30 jours", 30),
    ("90", "90 jours", 90),
]
PERIODE_DEFAUT = "30"


def _resolve_periode(request):
    demande = request.GET.get("periode", PERIODE_DEFAUT)
    for cle, libelle, jours in PERIODES:
        if cle == demande:
            return cle, libelle, jours
    return PERIODE_DEFAUT, "30 jours", 30


def _task_status_rows(queryset):
    totaux = {
        row["statut"]: row["total"]
        for row in queryset.values("statut").annotate(total=Count("id"))
    }
    return [
        {"key": statut, "label": label, "total": totaux.get(statut, 0)}
        for statut, label in Task.Status.choices
    ]


@login_required
def home(request):
    dispatch_due_meeting_reminders()

    today = timezone.localdate()
    periode_cle, periode_libelle, periode_jours = _resolve_periode(request)
    depuis = timezone.now() - timedelta(days=periode_jours)

    tasks_queryset = get_visible_tasks(request.user)
    documents_queryset = get_visible_documents(request.user)
    visitors_queryset = get_visible_visitors(request.user)
    meetings_queryset = get_visible_meetings(request.user)
    next_meeting = get_next_meeting_for_user(request.user)

    vue_globale = can_view_all_activity(request.user)
    voit_courriers = can_access_courriers(request.user)
    voit_diplomes = can_access_diplomas(request.user)

    # --- Files de decision : ce qui attend une action, sans filtre de periode
    courriers_a_viser = (
        get_courriers_awaiting_dg(request.user).order_by("date_transmission_dg")[:6]
        if voit_courriers
        else []
    )
    courriers_a_transmettre = (
        get_courriers_awaiting_secretariat(request.user).order_by("date_reception")[:6]
        if voit_courriers
        else []
    )
    lots_a_signer = (
        get_lots_awaiting_signature(request.user).order_by("date_transmission_dg")[:6]
        if voit_diplomes
        else []
    )
    taches_a_valider = tasks_queryset.filter(statut=Task.Status.TRAITE).order_by("-updated_at")[:6]

    # --- Services : une mesure par barre, les autres colonnes restent chiffrees
    services = Service.objects.filter(actif=True)
    profile = getattr(request.user, "profil", None)
    if not vue_globale and profile and profile.service_id:
        services = services.filter(id=profile.service_id)

    services = services.annotate(
        taches_ouvertes=Count("tasks", filter=Q(tasks__statut__in=ACTIVE_TASK_STATUSES), distinct=True),
        visiteurs_du_jour=Count("visitors", filter=Q(visitors__heure_entree__date=today), distinct=True),
        documents_total=Count("documents", distinct=True),
        courriers_periode=Count("courriers", filter=Q(courriers__created_at__gte=depuis), distinct=True),
    ).order_by("-taches_ouvertes", "nom")

    # --- Repartitions par etape, sur la periode choisie
    distributions = []
    if voit_courriers:
        distributions.append(
            {
                "titre": "Courriers par étape",
                "sous_titre": f"{periode_libelle} · circuit de visa",
                "barres": build_distribution(
                    get_courrier_status_counts(request.user),
                    reverse("courriers:list"),
                ),
            }
        )
    if voit_diplomes:
        distributions.append(
            {
                "titre": "Lots de diplômes par étape",
                "sous_titre": "état courant du registre",
                "barres": build_distribution(
                    get_lot_status_counts(request.user),
                    reverse("diplomas:lot_list"),
                ),
            }
        )
    distributions.append(
        {
            "titre": "Tâches par statut",
            "sous_titre": "toutes les tâches visibles",
            "barres": build_distribution(
                _task_status_rows(tasks_queryset),
                reverse("tasks:list"),
            ),
        }
    )

    recent_activities = ActivityLog.objects.select_related("utilisateur")
    if not vue_globale:
        recent_activities = recent_activities.filter(utilisateur=request.user)

    stats = {
        "visitors_today": visitors_queryset.filter(heure_entree__date=today).count(),
        "visitors_present": visitors_queryset.filter(statut=Visitor.Status.PRESENT).count(),
        "tasks_pending": tasks_queryset.filter(statut__in=ACTIVE_TASK_STATUSES).count(),
        "tasks_to_validate": tasks_queryset.filter(statut=Task.Status.TRAITE).count(),
        "tasks_late": tasks_queryset.filter(date_limite__lt=today)
        .exclude(statut__in=[Task.Status.VALIDE, Task.Status.ARCHIVE, Task.Status.REJETE])
        .count(),
        "urgent_tasks": tasks_queryset.filter(
            priorite=Task.Priority.URGENTE,
            statut__in=ACTIVE_TASK_STATUSES,
        ).count(),
        "documents_added_today": documents_queryset.filter(date_ajout__date=today).count(),
        "meetings_upcoming": meetings_queryset.filter(
            statut=Meeting.Status.VALIDEE,
            date_heure__gte=timezone.now(),
        ).count(),
        "active_users": UserProfile.objects.filter(actif=True, utilisateur__is_active=True).count(),
    }

    if voit_courriers:
        courriers_visibles = get_visible_courriers(request.user)
        stats["courriers_a_viser"] = get_courriers_awaiting_dg(request.user).count()
        stats["courriers_a_transmettre"] = get_courriers_awaiting_secretariat(request.user).count()
        stats["courriers_urgents"] = get_urgent_open_courriers(request.user).count()
        stats["courriers_periode"] = courriers_visibles.filter(created_at__gte=depuis).count()
        stats["courriers_classes_periode"] = courriers_visibles.filter(
            statut=Courrier.Status.CLASSE,
            date_classement__gte=depuis,
        ).count()

    if voit_diplomes:
        stats["lots_a_signer"] = get_lots_awaiting_signature(request.user).count()
        stats["lots_total"] = get_visible_lots(request.user).count()
        stats["diplomas_total"] = get_visible_diplomas(request.user).count()

    context = {
        "stats": stats,
        "periodes": PERIODES,
        "periode_active": periode_cle,
        "periode_libelle": periode_libelle,
        "distributions": distributions,
        "service_load": build_service_load(services),
        "decisions": {
            "courriers_a_viser": courriers_a_viser,
            "courriers_a_transmettre": courriers_a_transmettre,
            "lots_a_signer": lots_a_signer,
            "taches_a_valider": taches_a_valider,
        },
        "alerts": {
            "late_tasks": tasks_queryset.filter(date_limite__lt=today)
            .exclude(statut__in=[Task.Status.VALIDE, Task.Status.ARCHIVE, Task.Status.REJETE])
            .order_by("date_limite")[:5],
            "present_visitors": visitors_queryset.filter(statut=Visitor.Status.PRESENT).order_by(
                "-heure_entree"
            )[:5],
            "lots_with_anomalies": get_lots_with_anomalies(request.user)[:5] if voit_diplomes else [],
            "courriers_urgents": get_urgent_open_courriers(request.user)[:5] if voit_courriers else [],
        },
        "recent_tasks": tasks_queryset.order_by("-updated_at")[:6],
        "recent_documents": documents_queryset.order_by("-date_ajout")[:6],
        "recent_visitors": visitors_queryset.order_by("-heure_entree")[:6],
        "recent_activities": recent_activities[:10],
        "is_global_dashboard": vue_globale,
        "shows_courriers": voit_courriers,
        "shows_diplomas": voit_diplomes,
        "peut_viser": can_validate_as_dg(request.user),
        "peut_transmettre": can_transmit_to_dg(request.user),
        "next_meeting": next_meeting,
        "next_meeting_countdown": build_countdown_label(next_meeting),
        "meeting_notifications": Notification.objects.filter(
            utilisateur=request.user,
            type_notification=Notification.Type.MEETING,
        )[:5],
        "can_manage_meetings": can_manage_meetings(request.user),
    }
    return render(request, "dashboard/home.html", context)
