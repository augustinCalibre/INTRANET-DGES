"""Synchronisation de l'annuaire de l'intranet vers la messagerie.

Règle unique : **l'intranet fait autorité**. Un compte agent y est créé, s'y
modifie et s'y désactive ; la messagerie suit. Rien ne se crée à la main dans
Nextcloud, sans quoi les deux annuaires divergent et personne ne sait plus
lequel dit vrai.

Trois conséquences, qui sont l'essentiel de ce module :

- l'identifiant de messagerie est celui de l'intranet, jamais un autre ;
- le mot de passe est poussé au moment où l'intranet le connaît en clair —
  à la création, à la réinitialisation, au changement — de sorte qu'un agent
  n'ait qu'un seul secret à retenir ;
- désactiver un compte dans l'intranet ferme immédiatement la messagerie.
  C'est le point qui compte le jour où quelqu'un quitte la direction.

La messagerie peut être arrêtée sans que l'intranet cesse de fonctionner :
aucune de ces opérations ne doit faire échouer la création d'un compte. Les
échecs sont journalisés et rattrapables par `synchroniser_messagerie`.
"""

import logging
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.utils.text import slugify

from . import client
from .client import MessagerieIndisponible

logger = logging.getLogger("intranet.messagerie")

# Groupe rassemblant tous les agents actifs, support de la conversation
# générale de la direction.
GROUPE_TOUS = "dges-tous"
LIBELLE_GROUPE_TOUS = "DGES — Tous les agents"
LIBELLE_CONVERSATION_GENERALE = "Direction générale — Annonces"


def synchronisation_active():
    return bool(getattr(settings, "MESSAGERIE_SYNC_ENABLED", False))


def identifiant_groupe_service(service):
    """Identifiant Nextcloud d'un service.

    Il est dérivé du nom plutôt que de la clé primaire : un administrateur qui
    ouvre l'administration de Nextcloud doit reconnaître ses services sans
    table de correspondance.
    """
    return f"svc-{slugify(service.nom)}"


def nom_affiche(user):
    return user.get_full_name().strip() or user.username


def _compte_doit_etre_actif(user):
    profil = getattr(user, "profil", None)
    return bool(user.is_active and (profil is None or profil.actif))


def assurer_groupes_services():
    """Crée dans la messagerie un groupe par service, plus le groupe général."""
    client.creer_groupe(GROUPE_TOUS, LIBELLE_GROUPE_TOUS)

    from accounts.models import Service

    crees = []
    for service in Service.objects.filter(actif=True).order_by("nom"):
        identifiant = identifiant_groupe_service(service)
        if client.creer_groupe(identifiant, service.nom):
            crees.append(service.nom)
    return crees


def _groupes_attendus(user):
    profil = getattr(user, "profil", None)
    groupes = [GROUPE_TOUS]
    if profil is not None and profil.service_id:
        groupes.append(identifiant_groupe_service(profil.service))
    return groupes


def synchroniser_utilisateur(user, mot_de_passe=None):
    """Aligne le compte de messagerie sur le compte intranet.

    `mot_de_passe` n'est fourni qu'aux moments où l'intranet le connaît en
    clair. Le reste du temps, le mot de passe de la messagerie est laissé
    intact — on ne le devine pas, et le remplacer par un mot de passe
    aléatoire couperait l'agent de ses conversations.

    Retourne l'une des chaînes « cree », « mis_a_jour », « desactive ».
    """
    identifiant = user.username
    existant = client.compte(identifiant)
    actif_attendu = _compte_doit_etre_actif(user)

    if not existant:
        if not actif_attendu:
            # Inutile de créer un compte pour le désactiver aussitôt.
            return "ignore"
        client.creer_compte(
            identifiant,
            mot_de_passe or secrets.token_urlsafe(18),
            nom_affiche=nom_affiche(user),
            email=user.email or "",
            groupes=_groupes_attendus(user),
        )
        logger.info("messagerie : compte %s créé", identifiant)
        return "cree"

    if not actif_attendu:
        client.desactiver_compte(identifiant)
        logger.info("messagerie : compte %s désactivé", identifiant)
        return "desactive"

    # Le compte existe et doit servir : on réaligne ce qui a pu changer.
    if not existant.get("enabled", True):
        client.activer_compte(identifiant)

    if (existant.get("displayname") or "") != nom_affiche(user):
        client.modifier_compte(identifiant, "displayname", nom_affiche(user))

    if user.email and (existant.get("email") or "") != user.email:
        client.modifier_compte(identifiant, "email", user.email)

    _aligner_groupes(identifiant, _groupes_attendus(user))

    if mot_de_passe:
        client.definir_mot_de_passe(identifiant, mot_de_passe)

    return "mis_a_jour"


def _aligner_groupes(identifiant, attendus):
    """Fait correspondre les groupes du compte à ceux de l'intranet.

    Le retrait compte autant que l'ajout : un agent qui change de service ne
    doit plus voir passer les conversations de son ancien service.
    """
    actuels = set(client.groupes_du_compte(identifiant))
    attendus = set(attendus)

    for groupe in attendus - actuels:
        client.ajouter_au_groupe(identifiant, groupe)

    # On ne retire que les groupes que l'intranet gère. Un groupe créé à la
    # main dans Nextcloud pour un autre usage n'a pas à disparaître.
    for groupe in actuels - attendus:
        if groupe == GROUPE_TOUS or groupe.startswith("svc-"):
            client.retirer_du_groupe(identifiant, groupe)


def synchroniser_sans_bloquer(user, mot_de_passe=None):
    """Variante pour les vues : ne lève jamais.

    Créer un compte agent doit réussir même si la messagerie est arrêtée. La
    vue reçoit un message d'avertissement à afficher, ou None si tout s'est
    bien passé.
    """
    if not synchronisation_active():
        return None
    try:
        assurer_groupes_services()
        synchroniser_utilisateur(user, mot_de_passe=mot_de_passe)
    except MessagerieIndisponible as erreur:
        logger.warning("messagerie : synchronisation de %s impossible — %s", user.username, erreur)
        return (
            f"Le compte a bien été enregistré, mais la messagerie n'a pas pu être "
            f"mise à jour ({erreur}). Relancez la synchronisation depuis "
            f"« Messagerie » quand elle sera de nouveau joignable."
        )
    return None


def assurer_conversations():
    """Crée une conversation par service, plus la conversation générale.

    Elles sont adossées aux groupes plutôt qu'à une liste de participants :
    Talk y inscrit les membres du groupe et suit ses évolutions. Un agent
    nouvellement affecté à un service rejoint sa conversation sans que
    personne ait à l'y inviter, et un agent muté la quitte.

    La conversation n'est créée qu'une fois : on reconnaît celles qui existent
    à leur nom. Relancer la fonction ne crée pas de doublon.
    """
    from accounts.models import Service

    assurer_groupes_services()

    existantes = {
        (conversation.get("displayName") or conversation.get("name") or "")
        for conversation in client.lister_conversations()
    }

    attendues = [(LIBELLE_CONVERSATION_GENERALE, GROUPE_TOUS)]
    for service in Service.objects.filter(actif=True).order_by("nom"):
        attendues.append((service.nom, identifiant_groupe_service(service)))

    creees = []
    for nom, groupe in attendues:
        if nom in existantes:
            continue
        client.creer_conversation_de_groupe(nom, groupe)
        logger.info("messagerie : conversation « %s » créée", nom)
        creees.append(nom)
    return creees


def desactiver_acces_messagerie(identifiant):
    """Ferme l'accès d'un compte supprimé de l'intranet.

    Le compte de messagerie est désactivé et non supprimé : effacer un compte
    Nextcloud emporte ses fichiers et laisse ses messages orphelins. Une
    conversation doit rester lisible et attribuable des mois après le départ
    de celui qui l'a écrite.
    """
    if not synchronisation_active():
        return None
    try:
        if client.compte(identifiant):
            client.desactiver_compte(identifiant)
            logger.info("messagerie : accès de %s fermé", identifiant)
    except MessagerieIndisponible as erreur:
        logger.warning("messagerie : accès de %s non fermé — %s", identifiant, erreur)
        return (
            f"Attention : l'accès de {identifiant} à la messagerie n'a pas pu être "
            f"fermé ({erreur}). Fermez-le depuis « Messagerie » dès que possible."
        )
    return None


def synchroniser_tous():
    """Rattrape l'ensemble de l'annuaire.

    Utilisée à la mise en service et après toute panne de la messagerie.
    Retourne le détail par compte, pour que l'administrateur voie ce qui a
    réellement changé.
    """
    assurer_groupes_services()

    resultats = {"cree": [], "mis_a_jour": [], "desactive": [], "ignore": [], "echec": []}
    for user in User.objects.select_related("profil", "profil__service").order_by("username"):
        try:
            issue = synchroniser_utilisateur(user)
        except MessagerieIndisponible as erreur:
            logger.warning("messagerie : %s non synchronisé — %s", user.username, erreur)
            resultats["echec"].append((user.username, str(erreur)))
            continue
        resultats[issue].append(user.username)
    return resultats


def etat_synchronisation():
    """Compare les deux annuaires, pour la page d'état.

    Ne lève pas : c'est une page de diagnostic, elle doit s'afficher même — et
    surtout — quand la messagerie ne répond plus.
    """
    if not synchronisation_active():
        return {"etat": "desactivee", "message": "La synchronisation est désactivée."}

    diagnostic = client.diagnostic()
    if diagnostic["etat"] != "ok":
        return diagnostic

    comptes_messagerie = {nom.lower() for nom in diagnostic["comptes"]}
    attendus = []
    manquants = []
    for user in User.objects.select_related("profil").order_by("username"):
        if not _compte_doit_etre_actif(user):
            continue
        attendus.append(user.username)
        if user.username.lower() not in comptes_messagerie:
            manquants.append(user.username)

    # Comptes présents dans la messagerie sans correspondant actif dans
    # l'intranet : anciens agents, ou comptes créés à la main.
    orphelins = sorted(
        nom
        for nom in diagnostic["comptes"]
        if nom.lower() not in {u.lower() for u in attendus}
        and nom != settings.MESSAGERIE_ADMIN_USER
    )

    return {
        "etat": "ok" if not manquants else "incomplete",
        "message": "",
        "total_intranet": len(attendus),
        "total_messagerie": len(diagnostic["comptes"]),
        "manquants": manquants,
        "orphelins": orphelins,
    }
