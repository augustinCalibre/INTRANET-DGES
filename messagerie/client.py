"""Client de l'API de provisionnement Nextcloud.

L'intranet tient l'annuaire ; la messagerie le suit. Ce module est la seule
porte par laquelle l'application parle a Nextcloud, ce qui laisse un endroit
unique ou regarder quand la synchronisation deraille.

Il s'appuie sur la bibliotheque standard plutot que sur `requests` : les
besoins tiennent en quelques appels HTTP, et une dependance de moins est une
dependance de moins a suivre pour un serveur qui doit tourner des annees sans
maintenance lourde.

L'appel se fait de conteneur a conteneur, en HTTP sur le reseau Docker interne.
Passer par HTTPS et le nom public ferait sortir puis rentrer le trafic par
nginx avec un certificat auto-signe, pour rien.

Documentation : https://docs.nextcloud.com/server/latest/admin_manual/
configuration_user/instruction_set_for_users.html
"""

import base64
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("intranet.messagerie")

# Codes que l'API OCS renvoie dans `meta.statuscode`. Ils ne suivent pas les
# codes HTTP : une requete rejetee revient en HTTP 200 avec un code metier.
#
# 100 vient de l'API historique, 200 de sa version 2, et 201 est renvoye par
# Talk a la creation d'une conversation. Les trois disent la meme chose.
OCS_SUCCES = {100, 200, 201}
OCS_COMPTE_EXISTANT = 102
OCS_GROUPE_EXISTANT = 102
OCS_INTROUVABLE = 404
OCS_NON_AUTORISE = 997


class MessagerieIndisponible(Exception):
    """La messagerie n'a pas pu être jointe, ou a refusé l'opération.

    Une seule exception pour les deux cas : du point de vue de l'appelant, la
    conduite à tenir est la même — ne pas bloquer l'opération en cours dans
    l'intranet, et signaler que la messagerie devra être resynchronisée.
    """

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class ReponseOCS:
    """Réponse de l'API, décortiquée."""

    def __init__(self, code, message, donnees):
        self.code = code
        self.message = message
        self.donnees = donnees

    @property
    def reussie(self):
        return self.code in OCS_SUCCES


def _configuration_complete():
    return bool(
        getattr(settings, "MESSAGERIE_API_URL", "")
        and getattr(settings, "MESSAGERIE_ADMIN_USER", "")
        and getattr(settings, "MESSAGERIE_ADMIN_PASSWORD", "")
    )


def _entetes():
    identifiants = f"{settings.MESSAGERIE_ADMIN_USER}:{settings.MESSAGERIE_ADMIN_PASSWORD}"
    autorisation = base64.b64encode(identifiants.encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {autorisation}",
        # Sans cet en-tete, Nextcloud renvoie une page de connexion au lieu
        # d'executer l'appel : c'est lui qui distingue une requete d'API d'une
        # visite de navigateur.
        "OCS-APIRequest": "true",
        "Accept": "application/json",
    }


def appeler(methode, chemin, donnees=None, tolerer=()):
    """Appelle l'API OCS et retourne une `ReponseOCS`.

    `tolerer` liste les codes metier qui ne doivent pas lever d'exception —
    « le compte existe deja », typiquement, qui n'est pas un echec quand on
    cherche justement a s'assurer qu'il existe.
    """
    if not _configuration_complete():
        raise MessagerieIndisponible(
            "La messagerie n'est pas configurée : MESSAGERIE_API_URL et les "
            "identifiants d'administration sont requis."
        )

    url = f"{settings.MESSAGERIE_API_URL.rstrip('/')}/{chemin.lstrip('/')}?format=json"
    corps = None
    entetes = _entetes()
    if donnees:
        corps = urllib.parse.urlencode(donnees, doseq=True).encode("utf-8")
        entetes["Content-Type"] = "application/x-www-form-urlencoded"

    requete = urllib.request.Request(url, data=corps, method=methode, headers=entetes)

    try:
        with urllib.request.urlopen(
            requete, timeout=getattr(settings, "MESSAGERIE_TIMEOUT", 10)
        ) as reponse:
            charge = reponse.read().decode("utf-8")
    except urllib.error.HTTPError as erreur:
        # Nextcloud renvoie parfois un vrai code HTTP d'erreur, notamment 401
        # quand les identifiants d'administration ne conviennent plus.
        charge = erreur.read().decode("utf-8", "replace")
        if erreur.code == 401:
            raise MessagerieIndisponible(
                "Identifiants d'administration de la messagerie refusés.",
                code=401,
            ) from erreur
    except (urllib.error.URLError, socket.timeout, OSError) as erreur:
        raise MessagerieIndisponible(
            f"Messagerie injoignable : {erreur}"
        ) from erreur

    try:
        contenu = json.loads(charge)["ocs"]
        meta = contenu["meta"]
    except (ValueError, KeyError) as erreur:
        raise MessagerieIndisponible(
            "Réponse inattendue de la messagerie : ce n'est pas une réponse OCS."
        ) from erreur

    reponse = ReponseOCS(
        code=int(meta.get("statuscode", 0)),
        message=meta.get("message") or "",
        donnees=contenu.get("data"),
    )

    if reponse.reussie or reponse.code in tolerer:
        return reponse

    raise MessagerieIndisponible(
        f"La messagerie a refusé l'opération ({reponse.code}) : "
        f"{reponse.message or 'sans explication'}",
        code=reponse.code,
    )


# ------------------------------------------------------------------ comptes


def compte(identifiant):
    """Retourne le compte de messagerie, ou None s'il n'existe pas."""
    reponse = appeler("GET", f"ocs/v2.php/cloud/users/{identifiant}", tolerer=(OCS_INTROUVABLE, 998))
    return reponse.donnees if reponse.reussie else None


def lister_comptes():
    reponse = appeler("GET", "ocs/v2.php/cloud/users")
    return list((reponse.donnees or {}).get("users", []))


def creer_compte(identifiant, mot_de_passe, nom_affiche="", email="", groupes=()):
    """Crée le compte. Ne lève rien s'il existe déjà."""
    donnees = {"userid": identifiant, "password": mot_de_passe}
    if nom_affiche:
        donnees["displayName"] = nom_affiche
    if email:
        donnees["email"] = email
    if groupes:
        donnees["groups[]"] = list(groupes)

    reponse = appeler(
        "POST", "ocs/v2.php/cloud/users", donnees, tolerer=(OCS_COMPTE_EXISTANT,)
    )
    return reponse.reussie


def modifier_compte(identifiant, cle, valeur):
    """Modifie un attribut : displayname, email, password…"""
    appeler(
        "PUT",
        f"ocs/v2.php/cloud/users/{identifiant}",
        {"key": cle, "value": valeur},
    )


def definir_mot_de_passe(identifiant, mot_de_passe):
    modifier_compte(identifiant, "password", mot_de_passe)


def activer_compte(identifiant):
    appeler("PUT", f"ocs/v2.php/cloud/users/{identifiant}/enable")


def desactiver_compte(identifiant):
    appeler("PUT", f"ocs/v2.php/cloud/users/{identifiant}/disable")


# ------------------------------------------------------------------ groupes


def lister_groupes():
    reponse = appeler("GET", "ocs/v2.php/cloud/groups")
    return list((reponse.donnees or {}).get("groups", []))


def creer_groupe(identifiant, libelle=""):
    """Crée le groupe. Ne lève rien s'il existe déjà."""
    donnees = {"groupid": identifiant}
    if libelle:
        donnees["displayname"] = libelle
    reponse = appeler(
        "POST", "ocs/v2.php/cloud/groups", donnees, tolerer=(OCS_GROUPE_EXISTANT,)
    )
    return reponse.reussie


def groupes_du_compte(identifiant):
    reponse = appeler("GET", f"ocs/v2.php/cloud/users/{identifiant}/groups")
    return list((reponse.donnees or {}).get("groups", []))


def ajouter_au_groupe(identifiant, groupe):
    appeler(
        "POST",
        f"ocs/v2.php/cloud/users/{identifiant}/groups",
        {"groupid": groupe},
        # 102 : deja membre. L'operation visant a garantir l'appartenance,
        # la trouver deja acquise n'est pas un echec.
        tolerer=(102,),
    )


def retirer_du_groupe(identifiant, groupe):
    appeler(
        "DELETE",
        f"ocs/v2.php/cloud/users/{identifiant}/groups",
        {"groupid": groupe},
        tolerer=(102, OCS_INTROUVABLE),
    )


# ----------------------------------------------------------- conversations


def lister_conversations():
    """Conversations Talk visibles par le compte d'administration."""
    reponse = appeler("GET", "ocs/v2.php/apps/spreed/api/v4/room")
    return list(reponse.donnees or [])


def creer_conversation_de_groupe(nom, groupe):
    """Crée une conversation Talk réunissant tous les membres d'un groupe.

    `roomType=2` désigne une conversation de groupe. En passant `source=groups`,
    Talk y inscrit les membres du groupe et suit ses évolutions : un agent
    ajouté au groupe rejoint la conversation sans intervention.
    """
    reponse = appeler(
        "POST",
        "ocs/v2.php/apps/spreed/api/v4/room",
        {"roomType": 2, "roomName": nom, "source": "groups", "invite": groupe},
    )
    return reponse.donnees or {}


def diagnostic():
    """Vérifie que la messagerie répond et que les droits sont suffisants.

    Retourne un dictionnaire lisible par la page d'état plutôt que de lever :
    l'administrateur consulte cette page précisément quand quelque chose ne
    va pas.
    """
    if not _configuration_complete():
        return {
            "etat": "non_configuree",
            "message": "La messagerie n'est pas configurée dans le fichier .env.",
        }
    try:
        comptes = lister_comptes()
    except MessagerieIndisponible as erreur:
        return {"etat": "injoignable", "message": str(erreur)}
    return {"etat": "ok", "message": "", "comptes": comptes}
