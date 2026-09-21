"""Diffusion d'un document : qui le recoit, et qui en est averti.

Un seul endroit repond a la question « a qui ce document s'adresse-t-il ? ».
Les vues ne recomposent pas la liste : elles appellent `notifier_diffusion`
apres l'enregistrement, en lui passant l'etat des destinataires d'avant.
"""

from django.contrib.auth.models import User
from django.db.models import Q
from django.urls import reverse

from core.models import Notification


def get_destinataires(document):
    """Comptes actifs qui recoivent ce document.

    Les trois destinations se cumulent — le service vise, les agents nommes,
    et la diffusion generale — mais « tous les agents » les absorbe : inutile
    d'additionner des ensembles dont l'un contient deja les autres.
    """
    actifs = User.objects.filter(is_active=True, profil__actif=True)
    if document.pour_tous:
        return actifs.distinct()

    conditions = Q(pk__in=document.destinataires.values_list("pk", flat=True))
    if document.service_concerne_id:
        conditions |= Q(profil__service_id=document.service_concerne_id)
    return actifs.filter(conditions).distinct()


def notifier_diffusion(document, auteur, deja_avertis=()):
    """Previent les destinataires qui ne l'avaient pas encore ete.

    `deja_avertis` porte les identifiants des destinataires d'avant
    l'enregistrement. Sans lui, corriger le titre d'un document renverrait
    une notification a tout le monde — le genre de bruit qui apprend aux
    agents a ne plus les lire.

    L'auteur n'est jamais averti de sa propre diffusion.
    """
    deja_avertis = set(deja_avertis)
    auteur_id = getattr(auteur, "id", None)

    nouveaux = [
        utilisateur
        for utilisateur in get_destinataires(document)
        if utilisateur.pk not in deja_avertis and utilisateur.pk != auteur_id
    ]
    if not nouveaux:
        return 0

    # La notification mene au telechargement : la liste des documents n'a pas
    # de fiche par piece, et renvoyer l'agent chercher un titre dans un
    # tableau reviendrait a ne rien lui indiquer du tout.
    url = reverse("documents:download", args=[document.pk])
    emetteur = ""
    if auteur is not None:
        emetteur = auteur.get_full_name().strip() or auteur.username

    Notification.objects.bulk_create(
        [
            Notification(
                utilisateur=utilisateur,
                type_notification=Notification.Type.DOCUMENT,
                titre=f"Nouveau document : {document.titre}",
                message=(
                    f"{document.get_type_document_display()} "
                    f"{'partagé par ' + emetteur if emetteur else 'déposé'}."
                ),
                url=url,
            )
            for utilisateur in nouveaux
        ]
    )
    return len(nouveaux)


def marquer_notifications_lues(user):
    """Solde le compteur du menu quand l'agent ouvre la liste des documents."""
    from django.utils import timezone

    return Notification.objects.filter(
        utilisateur=user,
        type_notification=Notification.Type.DOCUMENT,
        lu=False,
    ).update(lu=True, date_lecture=timezone.now())


def get_documents_non_lus(user):
    """Documents diffuses a cet agent qu'il n'a pas encore consultes."""
    if not getattr(user, "is_authenticated", False):
        return Notification.objects.none()
    return Notification.objects.filter(
        utilisateur=user,
        type_notification=Notification.Type.DOCUMENT,
        lu=False,
    )
