from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from accounts.models import Service


class Task(models.Model):
    CLOSED_STATUSES = {
        "valide",
        "rejete",
        "archive",
    }

    class Priority(models.TextChoices):
        FAIBLE = "faible", "Faible"
        NORMALE = "normale", "Normale"
        URGENTE = "urgente", "Urgente"

    class Status(models.TextChoices):
        NOUVEAU = "nouveau", "Nouveau"
        EN_ATTENTE = "en_attente", "En attente"
        EN_COURS = "en_cours", "En cours"
        TRAITE = "traite", "Traité"
        VALIDE = "valide", "Validé"
        REJETE = "rejete", "Rejeté"
        ARCHIVE = "archive", "Archivé"

    titre = models.CharField(max_length=180)
    description = models.TextField()
    service_concerne = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    assigne_a = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    partage_avec = models.ManyToManyField(
        User,
        blank=True,
        related_name="tasks_partagees",
        verbose_name="Partagée avec",
        help_text="Agents qui peuvent consulter et faire avancer cette tâche.",
    )
    priorite = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMALE,
    )
    statut = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOUVEAU,
    )
    date_limite = models.DateField(null=True, blank=True)
    cree_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name = "Tâche"
        verbose_name_plural = "Tâches"

    def __str__(self):
        return self.titre

    @property
    def is_closed(self):
        return self.statut in self.CLOSED_STATUSES

    @property
    def is_overdue(self):
        return bool(
            self.date_limite
            and not self.is_closed
            and self.date_limite < timezone.localdate()
        )

    @property
    def days_overdue(self):
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.date_limite).days

    @property
    def overdue_label(self):
        if not self.is_overdue:
            return ""
        if self.days_overdue == 1:
            return "Retard de 1 jour"
        return f"Retard de {self.days_overdue} jours"

    @property
    def partage_label(self):
        noms = [
            agent.get_full_name().strip() or agent.username
            for agent in self.partage_avec.all()
        ]
        return ", ".join(noms)

    @property
    def display_status_label(self):
        if self.is_overdue:
            return "En retard"
        return self.get_statut_display()


class TaskHistory(models.Model):
    tache = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="historiques",
    )
    action = models.CharField(max_length=180)
    ancien_statut = models.CharField(max_length=20, blank=True)
    nouveau_statut = models.CharField(max_length=20, blank=True)
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_histories",
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Historique de tâche"
        verbose_name_plural = "Historiques de tâche"

    def __str__(self):
        return f"{self.tache} - {self.action}"

# Create your models here.
