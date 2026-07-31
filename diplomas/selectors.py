from django.db.models import Count, Q

from core.permissions import can_access_diplomas

from .models import Diplome, LotDiplomes


def _scope_filters(user, prefix=""):
    """Perimetre d'un utilisateur non gestionnaire, sur le lot ou via `lot__`."""

    def field(name):
        return f"{prefix}{name}"

    filters = Q(**{field("agent_receptionnaire"): user}) | Q(**{field("cree_par"): user})
    profile = getattr(user, "profil", None)
    if profile and profile.service_id:
        filters |= Q(**{field("service_concerne"): profile.service})
    return filters


def get_lot_scope(user):
    """Lots accessibles, sans annotation : sert aux comptages agreges."""
    queryset = LotDiplomes.objects.all()
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if can_access_diplomas(user):
        return queryset
    return queryset.filter(_scope_filters(user)).distinct()


def get_visible_lots(user):
    """Lots accessibles, avec les compteurs de diplomes et d'anomalies."""
    return (
        get_lot_scope(user)
        .select_related("agent_receptionnaire", "service_concerne", "transmis_par", "signe_par")
        .annotate(
            nb_diplomes=Count("diplomes", distinct=True),
            nb_anomalies=Count(
                "diplomes",
                filter=Q(diplomes__statut=Diplome.Status.NON_CONFORME),
                distinct=True,
            ),
        )
        # L'agregation pose un GROUP BY : Django considere alors le queryset
        # comme non ordonne. On reprend l'ordre du modele explicitement pour
        # que la pagination reste stable d'une page a l'autre.
        .order_by("-date_arrivee", "-created_at")
    )


def get_visible_diplomas(user):
    queryset = Diplome.objects.select_related("lot")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if can_access_diplomas(user):
        return queryset
    return queryset.filter(_scope_filters(user, prefix="lot__")).distinct()


def get_lot_status_counts(user):
    """Nombre de lots par statut, dans l'ordre du circuit de traitement."""
    totals = {
        row["statut"]: row["total"]
        for row in get_lot_scope(user).values("statut").annotate(total=Count("id"))
    }
    return [
        {
            "key": status,
            "label": LotDiplomes.Status(status).label,
            "total": totals.get(status, 0),
        }
        for status in LotDiplomes.STATUS_FLOW
    ]


def get_diploma_status_counts(user):
    totals = {
        row["statut"]: row["total"]
        for row in get_visible_diplomas(user).values("statut").annotate(total=Count("id"))
    }
    return [
        {
            "key": status,
            "label": label,
            "total": totals.get(status, 0),
        }
        for status, label in Diplome.Status.choices
    ]


def get_lots_awaiting_signature(user):
    return get_visible_lots(user).filter(statut=LotDiplomes.Status.TRANSMIS_DG).order_by("date_transmission_dg")


def get_lots_with_anomalies(user):
    return (
        get_visible_lots(user)
        .filter(nb_anomalies__gt=0)
        .exclude(statut__in=LotDiplomes.CLOSED_STATUSES)
        .order_by("-date_arrivee")
    )
