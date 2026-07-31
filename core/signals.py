"""Enregistrement des connexions.

On s'appuie sur les signaux d'authentification de Django plutot que sur la vue
de connexion : ainsi l'administration Django et toute autre voie d'entree sont
couvertes de la meme facon.
"""

import logging

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .models import ConnexionLog

logger = logging.getLogger("intranet.connexions")

# Longueur maximale du champ correspondant, pour ne pas provoquer d'erreur de
# base sur un en-tete anormalement long.
POSTE_MAX = 255


def _adresse_ip(request):
    if request is None:
        return None
    # Derriere Nginx, REMOTE_ADDR est l'adresse du proxy : on prend la premiere
    # adresse de la chaine transmise, qui est celle du poste d'origine.
    transmise = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if transmise:
        premiere = transmise.split(",")[0].strip()
        if premiere:
            return premiere
    return request.META.get("REMOTE_ADDR") or None


def _poste(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:POSTE_MAX]


def _enregistrer(resultat, request, user=None, identifiant=""):
    adresse = _adresse_ip(request)
    try:
        ConnexionLog.objects.create(
            utilisateur=user,
            identifiant_saisi=(identifiant or "")[:150],
            resultat=resultat,
            adresse_ip=adresse,
            poste=_poste(request),
        )
    except Exception:  # pragma: no cover - la journalisation ne doit rien casser
        logger.exception("Impossible d'enregistrer la connexion")

    qui = user.username if user is not None else (identifiant or "inconnu")
    if resultat == ConnexionLog.Resultat.ECHEC:
        logger.warning("Echec de connexion pour %s depuis %s", qui, adresse or "adresse inconnue")
    else:
        logger.info("%s : %s depuis %s", qui, resultat, adresse or "adresse inconnue")


@receiver(user_logged_in, dispatch_uid="core.connexion_reussie")
def connexion_reussie(sender, request, user, **kwargs):
    _enregistrer(ConnexionLog.Resultat.SUCCES, request, user=user, identifiant=user.username)


@receiver(user_logged_out, dispatch_uid="core.deconnexion")
def deconnexion(sender, request, user, **kwargs):
    if user is None:
        return
    _enregistrer(
        ConnexionLog.Resultat.DECONNEXION,
        request,
        user=user,
        identifiant=user.username,
    )


@receiver(user_login_failed, dispatch_uid="core.connexion_echouee")
def connexion_echouee(sender, credentials, request=None, **kwargs):
    # `credentials` est deja expurge des mots de passe par Django.
    identifiant = credentials.get("username") or credentials.get("email") or ""
    _enregistrer(ConnexionLog.Resultat.ECHEC, request, identifiant=identifiant)
