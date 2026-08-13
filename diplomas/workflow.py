"""Circuit de traitement d'un lot de diplomes.

Un seul endroit decrit les passages de statut autorises, qui peut les
declencher, les conditions metier a respecter et les effets associes.
Les vues ne decident rien : elles appellent `apply_transition`.

Repartition des responsabilites, conforme a la regle « rien n'atteint le DG
sans le visa du Secretariat » :

    Agent d'etude   receptionne le lot, insere les diplomes, verifie, valide
    Secretariat     vise le lot conforme et le transmet au DG
    DG              signe, ou retourne pour correction
    Secretariat     enregistre le retour du lot signe au service
    Agent d'etude   acte la remise puis archive
"""

from django.utils import timezone

from core.permissions import (
    can_access_diplomas,
    can_manage_diplomas,
    can_transmit_to_dg,
    can_validate_as_dg,
)

from .models import Diplome, LotDiplomes
from .services import (
    get_lot_followers,
    get_signature_recipients,
    notify_lot,
    register_lot_history,
)

Status = LotDiplomes.Status

# (statut actuel, statut cible) -> description de l'action.
# `capability` designe la capacite exigee et `refus` le message affiche a qui
# ne la detient pas : chaque etape sait donc a qui elle appartient.
TRANSITIONS = {
    (Status.RECU, Status.EN_VERIFICATION): {
        "label": "Démarrer la vérification",
        "help": "Le lot passe en cours de contrôle des pièces.",
        "icon": "search",
        "tone": "primary",
        "capability": can_manage_diplomas,
        "refus": "Seul un agent d'étude peut vérifier un lot.",
        "require_comment": False,
        "confirm": "Démarrer la vérification de ce lot ?",
    },
    (Status.EN_VERIFICATION, Status.CONFORME): {
        "label": "Déclarer conforme",
        "help": "Toutes les pièces sont vérifiées et aucune anomalie ne subsiste.",
        "icon": "done",
        "tone": "success",
        "capability": can_manage_diplomas,
        "refus": "Seul un agent d'étude peut valider la conformité d'un lot.",
        "require_comment": False,
        "confirm": "Déclarer ce lot conforme ?",
    },
    (Status.CONFORME, Status.TRANSMIS_DG): {
        "label": "Transmettre au DG",
        "help": "Visa du Secrétariat, puis envoi à la signature du Directeur Général.",
        "icon": "send",
        "tone": "primary",
        "capability": can_transmit_to_dg,
        "refus": "Seul le Secrétariat transmet un lot au Directeur Général.",
        "require_comment": False,
        "confirm": "Viser ce lot et le transmettre à la signature du Directeur Général ?",
    },
    (Status.CONFORME, Status.EN_VERIFICATION): {
        "label": "Rouvrir la vérification",
        "help": "Une anomalie a été constatée après la déclaration de conformité.",
        "icon": "return",
        "tone": "neutral",
        "capability": can_manage_diplomas,
        "refus": "Seul un agent d'étude peut rouvrir la vérification.",
        "require_comment": True,
        "confirm": "Rouvrir la vérification de ce lot ?",
    },
    (Status.TRANSMIS_DG, Status.SIGNE): {
        "label": "Enregistrer la signature",
        "help": "Réservé au Directeur Général.",
        "icon": "sign",
        "tone": "success",
        "capability": can_validate_as_dg,
        "refus": "Seul le Directeur Général peut signer un lot.",
        "require_comment": False,
        "confirm": "Confirmer la signature de ce lot ?",
    },
    (Status.TRANSMIS_DG, Status.EN_VERIFICATION): {
        "label": "Retourner pour correction",
        "help": "Réservé au Directeur Général. Un motif est obligatoire.",
        "icon": "return",
        "tone": "danger",
        "capability": can_validate_as_dg,
        "refus": "Seul le Directeur Général peut retourner un lot pour correction.",
        "require_comment": True,
        "confirm": "Retourner ce lot au service pour correction ?",
    },
    (Status.SIGNE, Status.RETOURNE): {
        "label": "Enregistrer le retour au service",
        "help": "Le Secrétariat restitue le lot signé au service.",
        "icon": "checkout",
        "tone": "primary",
        "capability": can_transmit_to_dg,
        "refus": "Seul le Secrétariat enregistre le retour d'un lot signé.",
        "require_comment": False,
        "confirm": "Enregistrer le retour de ce lot au service ?",
    },
    (Status.RETOURNE, Status.REMIS): {
        "label": "Marquer comme remis",
        "help": "Les diplômes ont été remis aux bénéficiaires ou à l'établissement.",
        "icon": "done",
        "tone": "success",
        "capability": can_manage_diplomas,
        "refus": "Seul un agent d'étude peut acter la remise des diplômes.",
        "require_comment": False,
        "confirm": "Marquer ce lot comme remis ?",
    },
    (Status.REMIS, Status.ARCHIVE): {
        "label": "Archiver le lot",
        "help": "Clôture le traitement en conservant l'historique.",
        "icon": "archive",
        "tone": "neutral",
        "capability": can_manage_diplomas,
        "refus": "Seul un agent d'étude peut archiver un lot.",
        "require_comment": False,
        "confirm": "Archiver ce lot ? L'historique reste consultable.",
    },
}


def _blocking_reason(lot, target):
    """Condition metier empechant le passage au statut cible, sinon None.

    La verification ne consiste plus a saisir chaque diplome, mais a relever
    ceux qui ne sont pas conformes. Exiger des diplomes enregistres bloquerait
    donc exactement le cas normal : un lot sans anomalie.

    Ce qu'on exige a la place : que le lot annonce un nombre, sans quoi rien
    n'est verifiable, et qu'aucune anomalie ne reste ouverte.
    """
    if target in {Status.CONFORME, Status.TRANSMIS_DG}:
        if not lot.nombre_annonce:
            return (
                "Le nombre de diplômes annoncé par l'établissement n'est pas "
                "renseigné : sans lui, rien ne dit ce qui a été vérifié."
            )
        if lot.has_anomalies:
            return (
                f"{lot.nombre_anomalies} diplôme(s) sont marqués non conformes. "
                "Traitez les anomalies avant de poursuivre."
            )
    return None


def user_can_apply(lot, target, user):
    transition = TRANSITIONS.get((lot.statut, target))
    if transition is None:
        return False
    return bool(transition["capability"](user))


def get_available_transitions(lot, user):
    """Actions proposables a cet utilisateur, avec leur eventuel blocage.

    On ne presente que les etapes dont l'utilisateur detient la capacite :
    le service courrier ne voit pas le bouton de signature, et l'agent
    d'etude ne voit pas celui de transmission.
    """
    if not can_access_diplomas(user):
        return []

    available = []
    for (source, target), transition in TRANSITIONS.items():
        if source != lot.statut:
            continue
        if not transition["capability"](user):
            continue
        available.append(
            {
                **transition,
                "target": target,
                "target_label": Status(target).label,
                "blocked_reason": _blocking_reason(lot, target),
            }
        )
    return available


def _cascade_diplomas(lot, target, user):
    """Aligne le statut des diplomes sur celui du lot."""
    if target == Status.TRANSMIS_DG:
        return lot.diplomes.filter(statut=Diplome.Status.CONFORME).update(
            statut=Diplome.Status.TRANSMIS_DG
        )
    if target == Status.SIGNE:
        return lot.diplomes.filter(statut=Diplome.Status.TRANSMIS_DG).update(
            statut=Diplome.Status.SIGNE
        )
    if target == Status.EN_VERIFICATION:
        return lot.diplomes.filter(statut=Diplome.Status.TRANSMIS_DG).update(
            statut=Diplome.Status.A_VERIFIER
        )
    if target == Status.ARCHIVE:
        return lot.diplomes.exclude(
            statut__in=[Diplome.Status.RETIRE, Diplome.Status.ARCHIVE]
        ).update(statut=Diplome.Status.ARCHIVE)
    return 0


def _apply_side_effects(lot, target, user, now):
    """Renseigne les dates de tracabilite et retourne les champs modifies."""
    updated_fields = ["statut", "updated_at"]

    if target == Status.TRANSMIS_DG:
        lot.date_transmission_dg = now
        lot.transmis_par = user
        updated_fields += ["date_transmission_dg", "transmis_par"]
    elif target == Status.SIGNE:
        lot.date_signature = now
        lot.signe_par = user
        updated_fields += ["date_signature", "signe_par"]
    elif target == Status.RETOURNE:
        lot.date_retour = now
        updated_fields.append("date_retour")
    elif target == Status.REMIS:
        lot.date_remise = now
        updated_fields.append("date_remise")
    elif target == Status.EN_VERIFICATION:
        # Retour en arriere : la transmission precedente n'a plus lieu d'etre.
        lot.date_transmission_dg = None
        lot.transmis_par = None
        updated_fields += ["date_transmission_dg", "transmis_par"]

    return updated_fields


def _notify(lot, previous_status, target, commentaire):
    if target == Status.TRANSMIS_DG:
        notify_lot(
            get_signature_recipients(),
            f"Lot à signer : {lot.reference}",
            f"Le lot {lot.reference} ({lot.etablissement}) contient "
            f"{lot.nombre_enregistre} diplôme(s) et attend votre signature.",
            lot,
        )
    elif target == Status.SIGNE:
        notify_lot(
            get_lot_followers(lot),
            f"Lot signé : {lot.reference}",
            f"Le lot {lot.reference} a été signé par le Directeur Général.",
            lot,
        )
    elif target == Status.EN_VERIFICATION and previous_status == Status.TRANSMIS_DG:
        notify_lot(
            get_lot_followers(lot),
            f"Lot retourné pour correction : {lot.reference}",
            commentaire or f"Le lot {lot.reference} doit être corrigé avant nouvelle transmission.",
            lot,
        )
    elif target == Status.RETOURNE:
        notify_lot(
            get_lot_followers(lot),
            f"Lot revenu au service : {lot.reference}",
            f"Le lot signé {lot.reference} est revenu au service pour remise.",
            lot,
        )


def apply_transition(lot, target, user, commentaire=""):
    """Applique un changement de statut. Retourne (succes, message)."""
    transition = TRANSITIONS.get((lot.statut, target))
    if transition is None:
        return False, "Ce changement de statut n'est pas prévu par le circuit de traitement."

    if not transition["capability"](user):
        return False, transition["refus"]

    commentaire = (commentaire or "").strip()
    if transition["require_comment"] and not commentaire:
        return False, "Un motif est obligatoire pour cette action."

    blocking_reason = _blocking_reason(lot, target)
    if blocking_reason:
        return False, blocking_reason

    previous_status = lot.statut
    now = timezone.now()
    lot.statut = target
    updated_fields = _apply_side_effects(lot, target, user, now)
    lot.save(update_fields=updated_fields)

    _cascade_diplomas(lot, target, user)
    register_lot_history(
        lot,
        user,
        transition["label"],
        previous_status,
        target,
        commentaire=commentaire,
    )
    _notify(lot, previous_status, target, commentaire)

    return True, f"{transition['label']} : opération enregistrée."
