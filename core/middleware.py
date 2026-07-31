"""Intergiciels de l'intranet DGES."""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Impose le changement de mot de passe apres une reinitialisation.

    L'administrateur distribue un mot de passe provisoire ; sans cette
    contrainte il resterait valable indefiniment, souvent note sur un papier.
    L'agent ne peut donc rien faire d'autre que le changer, a l'exception de
    la deconnexion et des fichiers statiques.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            profile = getattr(user, "profil", None)
            if profile is not None and profile.doit_changer_mot_de_passe:
                if not self._est_autorise(request.path):
                    return redirect("accounts:password_change")

        return self.get_response(request)

    def _est_autorise(self, chemin):
        autorises = {
            reverse("accounts:password_change"),
            reverse("accounts:logout"),
            reverse("accounts:login"),
        }
        if chemin in autorises:
            return True
        for prefixe in (settings.STATIC_URL, settings.MEDIA_URL):
            if prefixe and chemin.startswith(prefixe):
                return True
        return False
