from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import Service


class Visitor(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Présent"
        SORTI = "sorti", "Sorti"
        ANNULE = "annule", "Annulé"

    nom_complet = models.CharField(max_length=150)
    contact = models.CharField(max_length=80)
    provenance = models.CharField(max_length=150, blank=True)
    motif = models.TextField()
    service_visite = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitors",
    )
    agent_visite = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitors_received",
    )
    heure_entree = models.DateTimeField(default=timezone.now)
    heure_sortie = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PRESENT,
    )
    cree_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitors_created",
    )

    class Meta:
        ordering = ["-heure_entree"]
        verbose_name = "Visiteur"
        verbose_name_plural = "Visiteurs"

    def __str__(self):
        return self.nom_complet

    def clean(self):
        if self.heure_sortie and self.heure_sortie < self.heure_entree:
            raise ValidationError("L'heure de sortie ne peut pas être antérieure à l'heure d'entrée.")

    def marquer_sortie(self):
        self.heure_sortie = timezone.now()
        self.statut = self.Status.SORTI
        self.save(update_fields=["heure_sortie", "statut"])

# Create your models here.
