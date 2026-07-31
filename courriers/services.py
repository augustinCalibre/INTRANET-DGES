"""Historique et notifications du circuit du courrier."""

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.urls import reverse

from accounts.constants import (
    ROLE_ADMINISTRATEUR,
    ROLE_DIRECTEUR_GENERAL,
    ROLE_SECRETARIAT,
)
from accounts.models import Service
from core.models import Notification

from .models import Courrier, CourrierHistory


def register_history(courrier, user, action, previous_status="", current_status="", commentaire=""):
    return CourrierHistory.objects.create(
        courrier=courrier,
        action=action,
        ancien_statut=previous_status,
        nouveau_statut=current_status,
        commentaire=commentaire,
        utilisateur=user if getattr(user, "is_authenticated", False) else None,
    )


def _actifs(roles):
    return User.objects.filter(
        is_active=True,
        profil__actif=True,
        profil__role__in=roles,
    ).distinct()


def get_secretariat_recipients():
    return _actifs([ROLE_SECRETARIAT, ROLE_ADMINISTRATEUR])


def get_dg_recipients():
    return _actifs([ROLE_DIRECTEUR_GENERAL, ROLE_ADMINISTRATEUR])


def get_courrier_followers(courrier):
    """Agents a prevenir du sort d'un courrier qu'ils ont enregistre."""
    ids = {courrier.receptionne_par_id, courrier.cree_par_id, courrier.transmis_par_id}
    ids.discard(None)
    if not ids:
        return User.objects.none()
    return User.objects.filter(id__in=ids, is_active=True).distinct()


def build_imputation_grid():
    """Grille d'imputation, construite a partir de l'organisation reelle.

    Une colonne par service actif, avec le service lui-meme puis ses agents.
    Rien a maintenir en parallele : un nouvel agent apparait sur la fiche des
    que son compte est cree.
    """
    grille = []
    for service in Service.objects.filter(actif=True).order_by("nom"):
        agents = (
            User.objects.filter(
                profil__service=service,
                is_active=True,
                profil__actif=True,
            )
            .order_by("last_name", "first_name", "username")
        )
        grille.append({"service": service, "agents": list(agents)})
    return grille


def get_imputation_recipients(courrier):
    """Agents vises par les imputations : nommement, ou via leur service."""
    service_ids = list(courrier.services_imputes.values_list("id", flat=True))
    agent_ids = list(courrier.agents_imputes.values_list("id", flat=True))

    if not service_ids and not agent_ids:
        return User.objects.none()

    return (
        User.objects.filter(
            Q(id__in=agent_ids) | Q(profil__service_id__in=service_ids),
            is_active=True,
            profil__actif=True,
        )
        .select_related("profil")
        .distinct()
    )


def _message_imputation(courrier):
    instructions = ", ".join(courrier.instructions.values_list("libelle", flat=True))
    message = f"{courrier.objet} — de {courrier.expediteur}."
    if instructions:
        message += f" Instructions : {instructions}."
    if courrier.instruction_dg:
        message += f" {courrier.instruction_dg}"
    return message


def notify_imputations(courrier):
    """Previent les destinataires d'une imputation, avec l'instruction du DG.

    La notification porte le lien du courrier : l'agent impute l'ouvre et le
    traite directement, sans attendre la circulation du papier.
    """
    destinataires = get_imputation_recipients(courrier)
    if not destinataires:
        return 0

    return notify(
        destinataires,
        f"Courrier imputé : {courrier.reference}",
        _message_imputation(courrier),
        courrier,
    )


def create_tasks_from_imputations(courrier, user):
    """Ouvre les taches de suivi manquantes pour chaque imputation.

    L'operation est idempotente : reenregistrer la fiche ne doit ni dupliquer
    des taches, ni lier une ancienne tache juste parce qu'elle partage le meme
    prefixe de titre.
    """
    from tasks.models import Task, TaskHistory

    urgente = (
        courrier.priorite == Courrier.Priorite.URGENTE
        or courrier.instructions.filter(libelle__icontains="urgence").exists()
    )
    priorite = Task.Priority.URGENTE if urgente else Task.Priority.NORMALE
    titre = f"Courrier {courrier.reference} : {courrier.objet}"[:180]
    description = (
        f"Courrier {courrier.reference} — {courrier.expediteur}.\n"
        f"{_message_imputation(courrier)}"
    )
    created_count = 0

    existing_tasks = list(courrier.taches.select_related("assigne_a", "service_concerne"))
    existing_by_agent = {
        task.assigne_a_id: task
        for task in existing_tasks
        if task.assigne_a_id is not None
    }
    existing_by_service = {
        task.service_concerne_id: task
        for task in existing_tasks
        if task.assigne_a_id is None and task.service_concerne_id is not None
    }

    def sync_existing_task(task, *, service_concerne, assigne_a=None):
        updated_fields = []
        if task.titre != titre:
            task.titre = titre
            updated_fields.append("titre")
        if task.description != description:
            task.description = description
            updated_fields.append("description")
        if task.priorite != priorite:
            task.priorite = priorite
            updated_fields.append("priorite")
        if task.service_concerne_id != getattr(service_concerne, "pk", None):
            task.service_concerne = service_concerne
            updated_fields.append("service_concerne")
        if task.assigne_a_id != getattr(assigne_a, "pk", None):
            task.assigne_a = assigne_a
            updated_fields.append("assigne_a")
        if updated_fields:
            task.save(update_fields=updated_fields + ["updated_at"])

    with transaction.atomic():
        for agent in courrier.agents_imputes.select_related("profil__service"):
            service_concerne = getattr(getattr(agent, "profil", None), "service", None)
            task = existing_by_agent.get(agent.pk)
            if task is not None:
                sync_existing_task(
                    task,
                    service_concerne=service_concerne,
                    assigne_a=agent,
                )
                continue

            task = Task.objects.create(
                titre=titre,
                description=description,
                service_concerne=service_concerne,
                assigne_a=agent,
                priorite=priorite,
                cree_par=user if getattr(user, "is_authenticated", False) else None,
            )
            courrier.taches.add(task)
            TaskHistory.objects.create(
                tache=task,
                action=f"Ouverte par imputation du courrier {courrier.reference}",
                nouveau_statut=task.statut,
                utilisateur=user if getattr(user, "is_authenticated", False) else None,
            )
            existing_by_agent[agent.pk] = task
            created_count += 1

        for service in courrier.services_imputes.all():
            task = existing_by_service.get(service.pk)
            if task is not None:
                sync_existing_task(task, service_concerne=service)
                continue

            task = Task.objects.create(
                titre=titre,
                description=description,
                service_concerne=service,
                priorite=priorite,
                cree_par=user if getattr(user, "is_authenticated", False) else None,
            )
            courrier.taches.add(task)
            TaskHistory.objects.create(
                tache=task,
                action=f"Ouverte par imputation du courrier {courrier.reference}",
                nouveau_statut=task.statut,
                utilisateur=user if getattr(user, "is_authenticated", False) else None,
            )
            existing_by_service[service.pk] = task
            created_count += 1

    return created_count


def record_task_progress(task, user, previous_status=""):
    """Fait remonter l'avancement d'une tache dans l'historique du courrier.

    Appele depuis la vue des taches : l'agent impute ne touche pas au courrier,
    il fait avancer sa tache, et c'est cet avancement qui informe le
    secretariat et le Directeur General que la suite a ete donnee.
    """
    courriers = list(task.courriers_origine.all())
    if not courriers:
        return 0

    qui = ""
    if getattr(user, "is_authenticated", False):
        qui = user.get_full_name().strip() or user.username

    for courrier in courriers:
        register_history(
            courrier,
            user,
            f'Suite donnée — tâche « {task.titre[:80]} » : {task.get_statut_display()}',
            previous_status,
            task.statut,
            commentaire=f"Traitée par {qui}." if qui else "",
        )
        if courrier.suite_donnee:
            register_history(
                courrier,
                user,
                "Toutes les tâches de suivi sont closes : le courrier peut être classé",
                courrier.statut,
                courrier.statut,
            )
            notify(
                list(get_secretariat_recipients()) + list(get_courrier_followers(courrier)),
                f"Suite donnée : {courrier.reference}",
                f'Toutes les tâches ouvertes sur « {courrier.objet} » sont closes. '
                "Le courrier peut être classé.",
                courrier,
            )

    return len(courriers)


def notify(recipients, titre, message, courrier):
    # Les listes de destinataires se recoupent : on dedoublonne pour n'envoyer
    # qu'une notification par personne.
    uniques = {}
    for user in recipients:
        uniques[user.pk] = user
    recipients = list(uniques.values())
    if not recipients:
        return 0

    url = reverse("courriers:detail", args=[courrier.pk])
    Notification.objects.bulk_create(
        [
            Notification(
                utilisateur=user,
                type_notification=Notification.Type.COURRIER,
                titre=titre,
                message=message,
                url=url,
            )
            for user in recipients
        ]
    )
    return len(recipients)
