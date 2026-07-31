"""Ancienne commande de chargement des donnees de demonstration.

Le jeu de demonstration a ete retire : comptes de test, services fictifs,
visiteurs, taches, courriers et lots de diplomes inventes n'ont pas leur
place dans une application destinee a la production. Un compte `dg` au mot
de passe connu sur un intranet reel est une porte ouverte.

Ce fichier ne subsiste que pour signaler explicitement le retrait aux
scripts et procedures qui l'appelaient encore. Il peut etre supprime.

Pour demarrer une installation :

    python manage.py migrate
    python manage.py createsuperuser

puis creez les services et les comptes des agents depuis le panneau
d'administration des acces.

Pour nettoyer une base qui contient encore des donnees de demonstration :

    python manage.py purge_demo                # inventaire
    python manage.py purge_demo --confirmer    # suppression
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Retiree : le jeu de donnees de demonstration n'existe plus."

    def handle(self, *args, **options):
        raise CommandError(
            "La commande seed_demo a ete retiree.\n"
            "Utilisez `createsuperuser` pour creer votre compte administrateur, "
            "puis le panneau d'administration des acces pour les services et les "
            "comptes des agents.\n"
            "Pour nettoyer une base existante : `python manage.py purge_demo`."
        )
