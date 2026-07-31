from django.contrib.auth.models import User
from django.db import models

from .constants import ROLE_AGENT, ROLE_CHOICES


class Service(models.Model):
    nom = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    est_service_courrier = models.BooleanField(default=False)
    responsable = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services_responsables",
    )
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.nom


class UserProfile(models.Model):
    utilisateur = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profil",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="membres",
    )
    fonction = models.CharField(max_length=120, blank=True)
    role = models.CharField(
        max_length=32,
        choices=ROLE_CHOICES,
        default=ROLE_AGENT,
    )
    telephone = models.CharField(max_length=30, blank=True)
    actif = models.BooleanField(default=True)
    doit_changer_mot_de_passe = models.BooleanField(
        default=False,
        verbose_name="Doit changer son mot de passe",
        help_text=(
            "Actif après une réinitialisation par l'administrateur : l'agent est "
            "contraint de choisir un nouveau mot de passe à sa prochaine connexion."
        ),
    )

    class Meta:
        ordering = ["utilisateur__last_name", "utilisateur__first_name", "utilisateur__username"]
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self):
        full_name = self.utilisateur.get_full_name().strip()
        return full_name or self.utilisateur.username
