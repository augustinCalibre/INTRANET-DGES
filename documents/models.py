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

    def save(self, *args, **kwargs):
        if self.est_archive:
            self.statut = self.Status.ARCHIVE
        elif self.statut == self.Status.ARCHIVE:
            self.est_archive = True
        super().save(*args, **kwargs)

# Create your models here.
