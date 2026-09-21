from django.db.models import Q

from core.permissions import can_manage_courriers, can_view_all_activity

from .models import Document


def get_visible_documents(user):
    # Les destinataires sont prechargees : la liste affiche la portee de
    # chaque document, ce qui sans cela couterait une requete par ligne.
    queryset = Document.objects.select_related("service_concerne", "auteur").prefetch_related(
        "destinataires"
    )
    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    if can_view_all_activity(user):
        return queryset

    profile = getattr(user, "profil", None)
    # Un document parvient a un agent par quatre chemins : il en est l'auteur,
    # il appartient au service vise, il est nomme parmi les destinataires, ou
    # le document s'adresse a toute la direction.
    filters = Q(auteur=user) | Q(destinataires=user) | Q(pour_tous=True)
    if profile and profile.service_id:
        filters |= Q(service_concerne=profile.service)
    # Le service courrier suit l'ensemble des courriers, quel que soit le
    # service destinataire : c'est lui qui les receptionne.
    if can_manage_courriers(user):
        filters |= Q(type_document=Document.Type.COURRIER)
    return queryset.filter(filters).distinct()
