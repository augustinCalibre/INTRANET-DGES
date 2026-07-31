from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from accounts.models import Service


class Salle(models.Model):
    """Salle de reunion, reservable et dont on sait si elle est occupee."""

    nom = models.CharField(max_length=120, unique=True)
    localisation = models.CharField(max_length=180, blank=True)
    capacite = models.PositiveIntegerField(
        default=0,
        help_text="Nombre de places. 0 si l'information n'est pas connue.",
    )
    equipements = models.CharField(
        max_length=255,
        blank=True,
        help_text="Projecteur, visioconférence, tableau…",
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Salle"
        verbose_name_plural = "Salles"

    def __str__(self):
        return self.nom

    @property
    def capacite_label(self):
        return f"{self.capacite} places" if self.capacite else "capacité non précisée"


class Meeting(models.Model):
    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDEE = "validee", "Validee"
        REPORTEE = "reportee", "Reportee"
        ANNULEE = "annulee", "Annulee"
        TENUE = "tenue", "Tenue"

    # Statuts qui immobilisent la salle. Une reunion annulee ou deja tenue
    # ne bloque plus le creneau.
    OCCUPYING_STATUSES = {"brouillon", "validee", "reportee"}
    DUREE_MAX_MINUTES = 24 * 60

    titre = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    date_heure = models.DateTimeField()
    duree_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Durée prévue, en minutes.",
    )
    salle_reservee = models.ForeignKey(
        Salle,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reunions",
    )
    services_concernes = models.ManyToManyField(
        Service,
        blank=True,
        related_name="meetings",
    )
    membres_invites = models.ManyToManyField(
        User,
        blank=True,
        related_name="meetings_invites",
    )
    statut = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.BROUILLON,
    )
    organisee_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings_created",
    )
    validee_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings_validated",
    )
    date_validation = models.DateTimeField(null=True, blank=True)
    rappel_60_envoye_at = models.DateTimeField(null=True, blank=True)
    rappel_15_envoye_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_heure", "-created_at"]
        verbose_name = "Reunion"
        verbose_name_plural = "Reunions"

    def __str__(self):
        return self.titre

    @property
    def salle(self):
        """Libelle de la salle.

        Conserve le nom de l'ancien champ texte : les gabarits et les messages
        de notification qui affichent `meeting.salle` restent valides.
        """
        return self.salle_reservee.nom if self.salle_reservee_id else "non précisée"

    @property
    def date_fin(self):
        return self.date_heure + timedelta(minutes=self.duree_minutes or 60)

    @property
    def duree_label(self):
        heures, minutes = divmod(self.duree_minutes or 60, 60)
        if heures and minutes:
            return f"{heures} h {minutes:02d}"
        if heures:
            return f"{heures} h"
        return f"{minutes} min"

    @property
    def occupe_la_salle(self):
        return self.statut in self.OCCUPYING_STATUSES

    @property
    def is_upcoming(self):
        return self.statut == self.Status.VALIDEE and self.date_heure >= timezone.now()

    @property
    def is_past(self):
        return self.date_heure < timezone.now()

    @property
    def status_badge_class(self):
        return {
            self.Status.BROUILLON: "badge meeting-status-draft",
            self.Status.VALIDEE: "badge meeting-status-confirmed",
            self.Status.REPORTEE: "badge meeting-status-postponed",
            self.Status.ANNULEE: "badge meeting-status-cancelled",
            self.Status.TENUE: "badge meeting-status-held",
        }.get(self.statut, "badge text-bg-light")
