from django.contrib.auth.models import User
from django.db import models


class ActivityLog(models.Model):
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=180)
    module = models.CharField(max_length=80)
    objet = models.CharField(max_length=180)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Journal d'activité"
        verbose_name_plural = "Journal d'activité"

    def __str__(self):
        return f"{self.module} - {self.action}"


class ConnexionLog(models.Model):
    """Historique des connexions : qui, quand, depuis quel poste.

    Les echecs sont conserves autant que les reussites : une serie de
    tentatives infructueuses sur un meme compte est le premier signe d'une
    attaque par essais successifs.
    """

    class Resultat(models.TextChoices):
        SUCCES = "succes", "Connexion réussie"
        ECHEC = "echec", "Échec de connexion"
        DECONNEXION = "deconnexion", "Déconnexion"

    utilisateur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connexions",
    )
    identifiant_saisi = models.CharField(
        max_length=150,
        blank=True,
        help_text="Identifiant tapé, conservé même quand le compte n'existe pas.",
    )
    resultat = models.CharField(
        max_length=20,
        choices=Resultat.choices,
        default=Resultat.SUCCES,
    )
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    poste = models.CharField(
        max_length=255,
        blank=True,
        help_text="Navigateur et système déclarés par le poste.",
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Connexion"
        verbose_name_plural = "Historique des connexions"
        indexes = [
            models.Index(fields=["-date"], name="conn_date_idx"),
            models.Index(fields=["resultat"], name="conn_resultat_idx"),
        ]

    def __str__(self):
        qui = self.utilisateur.username if self.utilisateur_id else self.identifiant_saisi
        return f"{qui} - {self.get_resultat_display()}"

    @property
    def libelle_compte(self):
        if self.utilisateur_id:
            return self.utilisateur.get_full_name().strip() or self.utilisateur.username
        return self.identifiant_saisi or "compte inconnu"

    @property
    def est_echec(self):
        return self.resultat == self.Resultat.ECHEC


class Notification(models.Model):
    class Type(models.TextChoices):
        INFO = "info", "Information"
        MEETING = "meeting", "Reunion"
        DIPLOME = "diplome", "Lot de diplomes"
        COURRIER = "courrier", "Courrier"
        DOCUMENT = "document", "Document"

    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type_notification = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.INFO,
    )
    titre = models.CharField(max_length=180)
    message = models.TextField()
    url = models.CharField(max_length=255, blank=True)
    lu = models.BooleanField(default=False)
    date_lecture = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return self.titre
