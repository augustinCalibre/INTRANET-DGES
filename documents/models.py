from pathlib import Path
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import models
from django.utils.text import slugify

from accounts.models import Service


def document_upload_path(instance, filename):
    service_name = slugify(instance.service_concerne.nom) if instance.service_concerne else "general"
    original_path = Path(filename)
    base_name = slugify(original_path.stem) or "document"
    extension = original_path.suffix.lower()
    unique_suffix = uuid4().hex[:12]
    return f"documents/{service_name}/{base_name}-{unique_suffix}{extension}"


class Document(models.Model):
    class Type(models.TextChoices):
        RAPPORT = "rapport", "Rapport"
        NOTE = "note", "Note"
        COURRIER = "courrier", "Courrier"
        PROCEDURE = "procedure", "Procédure"
        ADMINISTRATIF = "administratif", "Fichier administratif"

    class Status(models.TextChoices):
        ACTIF = "actif", "Actif"
        ARCHIVE = "archive", "Archivé"

    titre = models.CharField(max_length=180)
    type_document = models.CharField(max_length=20, choices=Type.choices)
    fichier = models.FileField(upload_to=document_upload_path)
    service_concerne = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    # Un document ne s'adresse pas qu'a un service : il vise parfois des
    # agents nommement, quel que soit leur rattachement, ou toute la
    # direction. Les trois destinations se cumulent — un document peut partir
    # a un service et a deux agents d'un autre.
    destinataires = models.ManyToManyField(
        User,
        blank=True,
        related_name="documents_recus",
        verbose_name="Agents destinataires",
    )
    pour_tous = models.BooleanField(
        default=False,
        verbose_name="Tous les agents de la DGES",
        help_text="Le document devient consultable par tous les comptes actifs.",
    )
    auteur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_created",
    )
    statut = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIF,
    )
    est_archive = models.BooleanField(default=False)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_ajout"]
        verbose_name = "Document"
        verbose_name_plural = "Documents"

    def __str__(self):
        return self.titre

    @property
    def nom_fichier(self):
        return Path(self.fichier.name).name

    # -- Portee du document -------------------------------------------

    @property
    def noms_destinataires(self):
        return [
            agent.get_full_name().strip() or agent.username
            for agent in self.destinataires.all()
        ]

    @property
    def portee_labels(self):
        """A qui ce document s'adresse, tel qu'on l'affiche dans la liste.

        « Tous les agents » se suffit a lui-meme : detailler en plus un
        service ou des noms laisserait croire a une diffusion restreinte.
        """
        if self.pour_tous:
            return ["Tous les agents"]

        labels = []
        if self.service_concerne_id:
            labels.append(self.service_concerne.nom)
        labels.extend(self.noms_destinataires)
        return labels

    @property
    def est_sans_destinataire(self):
        """Document que son auteur est seul a voir, faute de destination."""
        return not self.pour_tous and not self.service_concerne_id and not self.destinataires.exists()

    def save(self, *args, **kwargs):
        if self.est_archive:
            self.statut = self.Status.ARCHIVE
        elif self.statut == self.Status.ARCHIVE:
            self.est_archive = True
        super().save(*args, **kwargs)

# Create your models here.
