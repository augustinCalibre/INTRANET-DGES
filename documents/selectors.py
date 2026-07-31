from django.db.models import Q

from core.permissions import can_manage_courriers, can_view_all_activity

from .models import Document


def get_visible_documents(user):
    queryset = Document.objects.select_related("service_concerne", "auteur")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    if can_view_all_activity(user):
        return queryset

    profile = getattr(user, "profil", None)
    filters = Q(auteur=user)
    if profile and profile.service_id:
        filters |= Q(service_concerne=profile.service)
    # Le service courrier suit l'ensemble des courriers, quel que soit le
    # service destinataire : c'est lui qui les receptionne.
    if can_manage_courriers(user):
        filters |= Q(type_document=Document.Type.COURRIER)
    return queryset.filter(filters).distinct()
