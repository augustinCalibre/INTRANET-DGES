from django.db.models import Q

from core.permissions import can_assign_to_anyone, can_view_all_activity

from .models import Task


def get_visible_tasks(user):
    queryset = Task.objects.select_related("service_concerne", "assigne_a", "cree_par")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    if can_view_all_activity(user):
        return queryset

    profile = getattr(user, "profil", None)
    # Ses propres taches, celles qu'on lui a confiees, celles qu'on lui a
    # partagees, et celles de son service.
    filters = Q(assigne_a=user) | Q(cree_par=user) | Q(partage_avec=user)
    if profile and profile.service_id:
        filters |= Q(service_concerne=profile.service)
    return queryset.filter(filters).distinct()


def can_modify_task(task, user):
    """Le createur, la personne assignee et les agents partages font avancer
    la tache. Le secretariat et la direction gardent la main sur toutes."""
    if can_assign_to_anyone(user):
        return True

    user_id = getattr(user, "id", None)
    if task.cree_par_id == user_id or task.assigne_a_id == user_id:
        return True
    return task.partage_avec.filter(pk=user_id).exists()
