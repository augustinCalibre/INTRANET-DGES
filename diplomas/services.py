import csv
import io
import unicodedata
from pathlib import Path

from django.contrib.auth.models import User
from django.urls import reverse

from accounts.constants import ROLE_ADMINISTRATEUR, ROLE_DIRECTEUR_GENERAL
from core.models import Notification

from .models import Diplome, DiplomeHistory, LotHistory

MAX_IMPORT_ROWS = 2000

COLUMN_ALIASES = {
    "nom_beneficiaire": (
        "nom",
        "noms",
        "nom beneficiaire",
        "nom du beneficiaire",
        "beneficiaire",
        "nom et prenom",
        "nom et prenoms",
        "nom complet",
    ),
    "numero_diplome": (
        "numero",
        "numero diplome",
        "numero du diplome",
        "numero de diplome",
        "no diplome",
        "n diplome",
        "reference",
        "reference diplome",
    ),
    "filiere": ("filiere", "option", "section", "domaine", "faculte"),
    "etablissement": ("etablissement", "universite", "ecole", "institution", "provenance"),
    "annee_academique": (
        "annee",
        "annee academique",
        "annee scolaire",
        "promotion",
        "exercice",
    ),
    "observations": ("observation", "observations", "remarque", "remarques", "commentaire"),
}

REQUIRED_COLUMNS = ("nom_beneficiaire", "numero_diplome")

FIELD_MAX_LENGTHS = {
    "nom_beneficiaire": 180,
    "numero_diplome": 80,
    "filiere": 150,
    "etablissement": 180,
    "annee_academique": 20,
}


# ---------------------------------------------------------------- historique


def register_lot_history(lot, user, action, previous_status="", current_status="", commentaire=""):
    return LotHistory.objects.create(
        lot=lot,
        action=action,
        ancien_statut=previous_status,
        nouveau_statut=current_status,
        commentaire=commentaire,
        utilisateur=user if getattr(user, "is_authenticated", False) else None,
    )


def register_diploma_history(diplome, user, action, previous_status="", current_status="", commentaire=""):
    return DiplomeHistory.objects.create(
        diplome=diplome,
        action=action,
        ancien_statut=previous_status,
        nouveau_statut=current_status,
        commentaire=commentaire,
        utilisateur=user if getattr(user, "is_authenticated", False) else None,
    )


# ------------------------------------------------------------ notifications


def get_signature_recipients():
    """Utilisateurs a prevenir lorsqu'un lot part a la signature."""
    return User.objects.filter(
        is_active=True,
        profil__actif=True,
        profil__role__in=[ROLE_DIRECTEUR_GENERAL, ROLE_ADMINISTRATEUR],
    ).distinct()


def get_lot_followers(lot):
    """Agents a prevenir du retour d'un lot : receptionnaire, transmetteur, createur."""
    user_ids = {
        lot.agent_receptionnaire_id,
        lot.transmis_par_id,
        lot.cree_par_id,
    }
    user_ids.discard(None)
    if not user_ids:
        return User.objects.none()
    return User.objects.filter(id__in=user_ids, is_active=True).distinct()


def notify_lot(recipients, titre, message, lot):
    recipients = list(recipients)
    if not recipients:
        return 0

    lot_url = reverse("diplomas:lot_detail", args=[lot.pk])
    Notification.objects.bulk_create(
        [
            Notification(
                utilisateur=user,
                type_notification=Notification.Type.DIPLOME,
                titre=titre,
                message=message,
                url=lot_url,
            )
            for user in recipients
        ]
    )
    return len(recipients)


# -------------------------------------------------------------- import fichier
