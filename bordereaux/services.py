"""Ecritures du suivi des bordereaux : signatures et historique.

Les vues ne decident pas si une signature est recevable : elles appellent
`signer_engagement` ou `signer_liquidation`, qui retournent un couple
(succes, message). Les regles de chronologie tiennent donc dans un seul
fichier, et l'historique est ecrit au meme endroit que la signature — il ne
peut pas etre oublie.
"""

from django.utils import timezone

from .models import Bordereau, BordereauHistory


def register_bordereau_history(
    bordereau,
    user,
    action,
    ancien_etat="",
    nouvel_etat="",
    commentaire="",
):
    return BordereauHistory.objects.create(
        bordereau=bordereau,
        action=action,
        ancien_etat=ancien_etat,
        nouvel_etat=nouvel_etat,
        commentaire=commentaire,
        utilisateur=user if getattr(user, "is_authenticated", False) else None,
    )


def _controler_date(date_signature, libelle):
    """Refus communs a toute signature : date manquante ou posterieure a ce jour."""
    if not date_signature:
        return f"Indiquez la date de signature {libelle}."
    if date_signature > timezone.localdate():
        return (
            f"La signature {libelle} ne peut pas être datée du futur "
            f"({date_signature:%d/%m/%Y})."
        )
    return None


def signer_engagement(bordereau, user, date_signature, commentaire=""):
    """Enregistre la signature initiale : le bordereau entre dans le circuit."""
    if bordereau.engagement_signe:
        return False, (
            f"L'engagement de ce bordereau est déjà signé "
            f"({bordereau.date_engagement:%d/%m/%Y})."
        )

    refus = _controler_date(date_signature, "de l'engagement")
    if refus:
        return False, refus

    if bordereau.date_reception and date_signature < bordereau.date_reception:
        return False, (
            "L'engagement ne peut pas être signé avant la réception du bordereau "
            f"({bordereau.date_reception:%d/%m/%Y})."
        )

    ancien_etat = bordereau.etat
    bordereau.date_engagement = date_signature
    bordereau.save(update_fields=["date_engagement", "updated_at"])
    register_bordereau_history(
        bordereau,
        user,
        "Signature de l'engagement",
        ancien_etat,
        bordereau.etat,
        commentaire=commentaire,
    )
    return True, (
        f"Engagement du bordereau {bordereau.libelle} signé le "
        f"{date_signature:%d/%m/%Y}."
    )


def signer_liquidation(bordereau, user, date_signature, commentaire=""):
    """Enregistre la derniere signature du circuit.

    Elle vaut aussi validation du mandat : le Controleur financier n'a pas pu
    laisser passer une liquidation sans l'avoir vise. Rien n'est donc a saisir
    pour le mandat, qui devient « validé par déduction ».
    """
    if bordereau.liquidation_signee:
        return False, (
            f"La liquidation de ce bordereau est déjà signée "
            f"({bordereau.date_liquidation:%d/%m/%Y})."
        )

    if not bordereau.engagement_signe:
        return False, (
            "L'engagement doit être signé avant la liquidation : c'est lui qui "
            "fait entrer le bordereau dans le circuit."
        )

    refus = _controler_date(date_signature, "de la liquidation")
    if refus:
        return False, refus

    if date_signature < bordereau.date_engagement:
        return False, (
            "La liquidation ne peut pas être signée avant l'engagement "
            f"({bordereau.date_engagement:%d/%m/%Y})."
        )

    ancien_etat = bordereau.etat
    bordereau.date_liquidation = date_signature
    bordereau.save(update_fields=["date_liquidation", "updated_at"])
    register_bordereau_history(
        bordereau,
        user,
        "Signature de la liquidation",
        ancien_etat,
        bordereau.etat,
        commentaire=commentaire or "Mandat validé par déduction.",
    )
    return True, (
        f"Liquidation du bordereau {bordereau.libelle} signée le "
        f"{date_signature:%d/%m/%Y}. Le dossier est terminé."
    )


def decrire_changement(ancien, nouveau):
    """Phrase d'historique lorsqu'une modification de fiche change l'etat."""
    if ancien == nouveau:
        return "Mise à jour de la fiche"
    return (
        f"Mise à jour de la fiche : {Bordereau.Etat(ancien).label} "
        f"→ {Bordereau.Etat(nouveau).label}"
    )
