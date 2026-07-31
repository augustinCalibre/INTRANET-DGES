"""Circuit de traitement d'un courrier.

Chaine imposee, conforme a la regle « transmettre au DG par le secretariat » :

    Service courrier   receptionne, traite, transmet au Secretariat
    Secretariat        vise et transmet au DG, ou renvoie au service
    DG                 vise avec instruction, ou retourne au Secretariat
    Secretariat        redescend le courrier vise pour suite a donner
    Service courrier   classe le courrier

Aucune etape ne peut etre sautee : le DG ne recoit que ce que le Secretariat
lui a transmis, et le Secretariat que ce que le service courrier a traite.
"""

from django.utils import timezone

from core.permissions import (
    can_access_courriers,
    can_close_courrier,
    can_manage_courriers,
    can_record_dg_decision,
    can_transmit_to_dg,
    can_validate_as_dg,
)

from .models import Courrier
from .services import (
    get_courrier_followers,
    get_dg_recipients,
    get_secretariat_recipients,
    notify,
    notify_imputations,
    register_history,
)

Status = Courrier.Status

TRANSITIONS = {
    (Status.RECU, Status.EN_TRAITEMENT): {
        "label": "Prendre en traitement",
        "help": "Le service courrier enregistre les pièces et prépare la transmission.",
        "icon": "search",
        "tone": "primary",
        "capability": can_manage_courriers,
        "refus": "Seul le service courrier prend un courrier en traitement.",
        "require_comment": False,
        "confirm": "Prendre ce courrier en traitement ?",
    },
    (Status.EN_TRAITEMENT, Status.TRANSMIS_SECRETARIAT): {
        "label": "Transmettre au secrétariat",
        "help": "Le courrier traité part au secrétariat pour visa.",
        "icon": "send",
        "tone": "primary",
        "capability": can_manage_courriers,
        "refus": "Seul le service courrier transmet un courrier au secrétariat.",
        "require_comment": False,
        "confirm": "Transmettre ce courrier au secrétariat ?",
    },
    (Status.TRANSMIS_SECRETARIAT, Status.TRANSMIS_DG): {
        "label": "Viser et transmettre au DG",
        "help": "Visa du Secrétariat, puis transmission au Directeur Général.",
        "icon": "sign",
        "tone": "primary",
        "capability": can_transmit_to_dg,
        "refus": "Seul le Secrétariat transmet un courrier au Directeur Général.",
        "require_comment": False,
        "confirm": "Viser ce courrier et le transmettre au Directeur Général ?",
    },
    (Status.TRANSMIS_SECRETARIAT, Status.EN_TRAITEMENT): {
        "label": "Renvoyer au service courrier",
        "help": "Pièce manquante ou enregistrement à corriger. Motif obligatoire.",
        "icon": "return",
        "tone": "danger",
        "capability": can_transmit_to_dg,
        "refus": "Seul le Secrétariat renvoie un courrier au service.",
        "require_comment": True,
        "confirm": "Renvoyer ce courrier au service courrier ?",
    },
    (Status.TRANSMIS_DG, Status.VISE_DG): {
        "label": "Viser le courrier",
        "help": (
            "Décision du Directeur Général. Le secrétariat peut la reporter "
            "lorsqu'elle a été portée sur la fiche papier."
        ),
        "icon": "done",
        "tone": "success",
        "capability": can_record_dg_decision,
        "refus": "Seuls le Directeur Général et le secrétariat enregistrent le visa.",
        "require_comment": False,
        "confirm": "Enregistrer le visa du Directeur Général sur ce courrier ?",
    },
    (Status.TRANSMIS_DG, Status.TRANSMIS_SECRETARIAT): {
        "label": "Retourner au secrétariat",
        "help": "Réservé au Directeur Général. Un motif est obligatoire.",
        "icon": "return",
        "tone": "danger",
        "capability": can_validate_as_dg,
        "refus": "Seul le Directeur Général retourne un courrier au secrétariat.",
        "require_comment": True,
        "confirm": "Retourner ce courrier au secrétariat ?",
    },
    (Status.VISE_DG, Status.RETOURNE): {
        "label": "Diffuser pour suite à donner",
        "help": "Le Secrétariat redescend le courrier visé au service concerné.",
        "icon": "checkout",
        "tone": "primary",
        "capability": can_transmit_to_dg,
        "refus": "Seul le Secrétariat diffuse un courrier visé.",
        "require_comment": False,
        "confirm": "Diffuser ce courrier visé pour suite à donner ?",
    },
    (Status.RETOURNE, Status.CLASSE): {
        "label": "Classer le courrier",
        "help": "Clôture l'affaire, une fois la suite donnée. L'historique reste consultable.",
        "icon": "archive",
        "tone": "neutral",
        "capability": can_close_courrier,
        "refus": "Le classement revient au service courrier, au secrétariat ou au Directeur Général.",
        "require_comment": False,
        "confirm": "Classer ce courrier ? L'historique reste consultable.",
    },
}


def get_available_transitions(courrier, user):
    """Actions proposables : on n'affiche que ce que l'utilisateur peut faire."""
    if not can_access_courriers(user):
        return []

    available = []
    for (source, target), transition in TRANSITIONS.items():
        if source != courrier.statut or not transition["capability"](user):
            continue
        available.append(
            {
                **transition,
                "target": target,
                "target_label": Status(target).label,
            }
        )
    return available


def _apply_side_effects(courrier, target, user, now):
    champs = ["statut", "updated_at"]

    if target == Status.TRANSMIS_SECRETARIAT:
        courrier.date_transmission_secretariat = now
        champs.append("date_transmission_secretariat")
    elif target == Status.TRANSMIS_DG:
        courrier.date_transmission_dg = now
        courrier.transmis_par = user
        champs += ["date_transmission_dg", "transmis_par"]
    elif target == Status.VISE_DG:
        courrier.date_visa = now
        # `vise_par` designe l'auteur de la decision, pas forcement celui qui a
        # tape : quand le secretariat reporte une fiche papier, la decision
        # reste celle du Directeur General.
        courrier.vise_par = user
        champs += ["date_visa", "vise_par"]
    elif target == Status.RETOURNE:
        courrier.date_retour = now
        champs.append("date_retour")
    elif target == Status.CLASSE:
        courrier.date_classement = now
        champs.append("date_classement")
    elif target == Status.EN_TRAITEMENT:
        # Renvoi au service : la transmission precedente n'a plus cours.
        courrier.date_transmission_secretariat = None
        champs.append("date_transmission_secretariat")

    return champs


def _notify(courrier, previous_status, target, commentaire):
    if target == Status.TRANSMIS_SECRETARIAT and previous_status == Status.EN_TRAITEMENT:
        notify(
            get_secretariat_recipients(),
            f"Courrier à viser : {courrier.reference}",
            f"{courrier.objet} — de {courrier.expediteur}. En attente du visa du secrétariat.",
            courrier,
        )
    elif target == Status.TRANSMIS_DG:
        notify(
            get_dg_recipients(),
            f"Courrier à viser : {courrier.reference}",
            f"{courrier.objet} — de {courrier.expediteur}. Transmis par le secrétariat.",
            courrier,
        )
    elif target == Status.VISE_DG:
        notify(
            list(get_secretariat_recipients()) + list(get_courrier_followers(courrier)),
            f"Courrier visé : {courrier.reference}",
            courrier.instruction_dg or f"Le Directeur Général a visé « {courrier.objet} ».",
            courrier,
        )
        # Le visa met les imputations en circulation : c'est ce qui remplace la
        # remise du courrier de bureau en bureau.
        notify_imputations(courrier)
    elif target == Status.TRANSMIS_SECRETARIAT and previous_status == Status.TRANSMIS_DG:
        notify(
            get_secretariat_recipients(),
            f"Courrier retourné par le DG : {courrier.reference}",
            commentaire or f"Le Directeur Général a retourné « {courrier.objet} ».",
            courrier,
        )
    elif target == Status.EN_TRAITEMENT and previous_status == Status.TRANSMIS_SECRETARIAT:
        notify(
            get_courrier_followers(courrier),
            f"Courrier renvoyé au service : {courrier.reference}",
            commentaire or f"Le secrétariat a renvoyé « {courrier.objet} » pour correction.",
            courrier,
        )
    elif target == Status.RETOURNE:
        notify(
            get_courrier_followers(courrier),
            f"Courrier visé à traiter : {courrier.reference}",
            courrier.instruction_dg or f"Suite à donner sur « {courrier.objet} ».",
            courrier,
        )


def apply_transition(courrier, target, user, commentaire="", instruction=""):
    """Applique un changement de statut. Retourne (succes, message)."""
    transition = TRANSITIONS.get((courrier.statut, target))
    if transition is None:
        return False, "Ce changement de statut n'est pas prévu par le circuit du courrier."

    if not transition["capability"](user):
        return False, transition["refus"]

    commentaire = (commentaire or "").strip()
    if transition["require_comment"] and not commentaire:
        return False, "Un motif est obligatoire pour cette action."

    previous_status = courrier.statut
    now = timezone.now()
    courrier.statut = target
    champs = _apply_side_effects(courrier, target, user, now)

    instruction = (instruction or "").strip()
    if target == Status.VISE_DG and instruction:
        courrier.instruction_dg = instruction
        champs.append("instruction_dg")

    courrier.save(update_fields=champs)
    register_history(
        courrier,
        user,
        transition["label"],
        previous_status,
        target,
        commentaire=commentaire or instruction,
    )
    _notify(courrier, previous_status, target, commentaire)

    return True, f"{transition['label']} : opération enregistrée."
