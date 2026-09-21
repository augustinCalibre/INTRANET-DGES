"""Filtres de gabarit du module de suivi des bordereaux."""

from django import template

register = template.Library()


@register.filter
def pluriel(valeur, suffixe="s"):
    """Accord francais : le pluriel commence a deux.

    Le filtre `pluralize` de Django suit l'usage anglais et accorde zero au
    pluriel. Le tableau de suivi affiche beaucoup de zeros — une boite
    trimestrielle vide en aligne quatre — et « 0 bordereaux » s'y verrait.
    """
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return ""
    return suffixe if nombre > 1 else ""
