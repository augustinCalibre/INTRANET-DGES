"""Intergiciels de l'intranet DGES."""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse


class MaintenanceModeMiddleware:
    """Ferme l'application pendant une restauration.

    Il doit etre le premier de la liste, et il ne touche ni a la base ni a la
    session : pendant une restauration, la base de l'application est detruite
    puis rechargee. Tout ce qui lirait `request.user` echouerait, puisque les
    sessions y sont stockees. Le signal est donc un simple fichier, depose par
    le service de sauvegarde dans un volume partage.

    Les fichiers statiques restent servis : sans eux la page d'attente
    s'afficherait sans mise en forme, ce qui ressemble a une panne plutot qu'a
    une operation maitrisee.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.temoin = Path(settings.BACKUP_CONTROL_DIR) / "maintenance"

    def __call__(self, request):
        if self._maintenance_active() and not self._est_autorise(request.path):
            return self._page_attente(request)
        return self.get_response(request)

    def _maintenance_active(self):
        try:
            return self.temoin.exists()
        except OSError:
            # Volume de controle absent : l'application fonctionne
            # normalement, sans onglet de restauration.
            return False

    def _est_autorise(self, chemin):
        for prefixe in (settings.STATIC_URL, settings.MEDIA_URL):
            if prefixe and chemin.startswith(prefixe):
                return True
        return False

    def _page_attente(self, request):
        etape = ""
        message = ""
        try:
            contenu = (Path(settings.BACKUP_CONTROL_DIR) / "etat").read_text(
                encoding="utf-8"
            )
            for ligne in contenu.splitlines():
                cle, separateur, valeur = ligne.partition("=")
                if not separateur:
                    continue
                if cle.strip() == "etape":
                    etape = valeur.strip()
                elif cle.strip() == "message":
                    message = valeur.strip()
        except OSError:
            pass

        # Volontairement sans `request` : le passer ferait tourner les
        # processeurs de contexte, qui lisent `request.user` — inexistant a ce
        # stade, l'authentification venant plus loin dans la chaine — et
        # interrogent la base, precisement ce qu'on ne peut pas faire pendant
        # une restauration.
        contenu = render_to_string(
            "maintenance.html", {"etape": etape, "message": message}
        )
        reponse = HttpResponse(contenu, status=503)
        # Trois minutes : au-dela, les navigateurs et le proxy cesseraient de
        # patienter et afficheraient leur propre page d'erreur.
        reponse["Retry-After"] = "180"
        return reponse


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
