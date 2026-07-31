from django.db.models import Q

from core.permissions import can_manage_visitors, can_view_all_activity

from .models import Visitor


def get_visible_visitors(user):
    queryset = Visitor.objects.select_related("service_visite", "agent_visite", "cree_par")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    # Le registre d'entree est tenu par le secretariat : qui l'alimente le
    # consulte en entier, sinon la recherche d'une visite passee serait vaine.
    if can_view_all_activity(user) or can_manage_visitors(user):
        return queryset

    profile = getattr(user, "profil", None)
    filters = Q(agent_visite=user) | Q(cree_par=user)
    if profile and profile.service_id:
        filters |= Q(service_visite=profile.service)
    return queryset.filter(filters).distinct()
