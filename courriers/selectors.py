from django.db.models import Count, Q

from core.permissions import can_access_courriers, can_view_all_activity

from .models import Courrier


def get_visible_courriers(user):
    """Registre accessible a cet utilisateur.

    Le circuit du courrier est centralise : qui y participe voit l'ensemble
    du registre, sinon le suivi d'un courrier d'un service a l'autre serait
    impossible. Les autres agents ne voient que ce qui concerne leur service.
    """
    queryset = Courrier.objects.select_related(
        "destinataire_service",
        "receptionne_par",
        "transmis_par",
        "vise_par",
    )
    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    if can_access_courriers(user) or can_view_all_activity(user):
        return queryset

    profile = getattr(user, "profil", None)
    # Un agent imputé doit pouvoir ouvrir le courrier : sans cela le lien de sa
    # notification mène à une page qui lui est refusée, et il ne peut pas
    # donner suite.
    filters = Q(receptionne_par=user) | Q(cree_par=user) | Q(agents_imputes=user)
    if profile and profile.service_id:
        filters |= Q(destinataire_service=profile.service) | Q(
            services_imputes=profile.service
        )
    return queryset.filter(filters).distinct()


def get_status_counts(user):
    """Nombre de courriers par statut, dans l'ordre du circuit."""
    totals = {
        row["statut"]: row["total"]
        for row in get_visible_courriers(user).values("statut").annotate(total=Count("id"))
    }
    return [
        {
            "key": statut,
            "label": Courrier.Status(statut).label,
            "total": totals.get(statut, 0),
        }
        for statut in Courrier.STATUS_FLOW
    ]


def get_courriers_awaiting_dg(user):
    return get_visible_courriers(user).filter(statut=Courrier.Status.TRANSMIS_DG)


def get_courriers_awaiting_secretariat(user):
    return get_visible_courriers(user).filter(statut=Courrier.Status.TRANSMIS_SECRETARIAT)


def get_urgent_open_courriers(user):
    return (
        get_visible_courriers(user)
        .filter(priorite=Courrier.Priorite.URGENTE)
        .exclude(statut__in=Courrier.CLOSED_STATUSES)
        .order_by("date_reception")
    )
