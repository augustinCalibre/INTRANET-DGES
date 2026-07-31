"""Suppression des donnees de demonstration.

Par defaut la commande ne fait qu'un inventaire : rien n'est supprime sans
`--confirmer`. Un intranet destine a la production ne doit conserver ni
comptes de test, ni services fictifs, ni lots de diplomes inventes.

    python manage.py purge_demo                  # inventaire seul
    python manage.py purge_demo --confirmer      # suppression effective
    python manage.py purge_demo --confirmer --garder-services
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Service, UserProfile
from core.models import ActivityLog, Notification
from diplomas.models import Diplome, LotDiplomes
from documents.models import Document
from meetings.models import Meeting
from tasks.models import Task, TaskHistory
from visitors.models import Visitor

# Comptes crees par l'ancienne commande seed_demo.
DEMO_USERNAMES = [
    "admin_dges",
    "dg",
    "secretariat",
    "resp_planif",
    "resp_docs",
    "agent_pedago",
    "agent_it",
    "courrier",
    "charge_personnel",
]

# Services du jeu de demonstration.
DEMO_SERVICES = [
    "Cabinet du Directeur Général",
    "Secrétariat Général",
    "Planification et Suivi",
    "Documentation et Archives",
    "Informatique et Support",
    "Service Courrier",
]


class Command(BaseCommand):
    help = "Supprime les donnees de demonstration. Inventaire seul sans --confirmer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmer",
            action="store_true",
            help="Procede reellement a la suppression.",
        )
        parser.add_argument(
            "--garder-services",
            action="store_true",
            help="Conserve la table des services.",
        )
        parser.add_argument(
            "--garder-comptes",
            action="store_true",
            help="Conserve les comptes de demonstration.",
        )

    def handle(self, *args, **options):
        confirmer = options["confirmer"]
        garder_services = options["garder_services"]
        garder_comptes = options["garder_comptes"]

        demo_users = User.objects.filter(username__in=DEMO_USERNAMES)
        demo_services = Service.objects.filter(nom__in=DEMO_SERVICES)

        inventaire = [
            ("Lots de diplomes", LotDiplomes.objects.count()),
            ("Diplomes", Diplome.objects.count()),
            ("Visiteurs", Visitor.objects.count()),
            ("Taches", Task.objects.count()),
            ("Historiques de tache", TaskHistory.objects.count()),
            ("Documents", Document.objects.count()),
            ("Reunions", Meeting.objects.count()),
            ("Notifications", Notification.objects.count()),
            ("Entrees du journal d'activite", ActivityLog.objects.count()),
        ]
        if not garder_comptes:
            inventaire.append(("Comptes de demonstration", demo_users.count()))
        if not garder_services:
            inventaire.append(("Services de demonstration", demo_services.count()))

        self.stdout.write("Donnees concernees :")
        for libelle, total in inventaire:
            self.stdout.write(f"  {total:>6}  {libelle}")

        superusers_restants = User.objects.filter(is_superuser=True).exclude(
            username__in=[] if garder_comptes else DEMO_USERNAMES
        )

        if not confirmer:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Inventaire seul : rien n'a ete supprime. "
                    "Relancez avec --confirmer pour proceder."
                )
            )
            if not superusers_restants.exists():
                self.stdout.write(
                    self.style.ERROR(
                        "Attention : aucun superutilisateur ne subsisterait apres la purge. "
                        "Creez d'abord votre compte avec `python manage.py createsuperuser`."
                    )
                )
            return

        if not superusers_restants.exists():
            self.stderr.write(
                self.style.ERROR(
                    "Purge interrompue : aucun superutilisateur ne subsisterait. "
                    "Creez d'abord votre compte avec `python manage.py createsuperuser`."
                )
            )
            return

        with transaction.atomic():
            # Les historiques et diplomes partent en cascade avec leur parent.
            LotDiplomes.objects.all().delete()
            Visitor.objects.all().delete()
            Task.objects.all().delete()
            for document in Document.objects.all():
                if document.fichier:
                    document.fichier.delete(save=False)
            Document.objects.all().delete()
            Meeting.objects.all().delete()
            Notification.objects.all().delete()
            ActivityLog.objects.all().delete()

            if not garder_comptes:
                UserProfile.objects.filter(utilisateur__in=demo_users).delete()
                demo_users.delete()

            if not garder_services:
                demo_services.delete()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Donnees de demonstration supprimees."))
        self.stdout.write(
            "Etapes suivantes : creez les services reels puis les comptes des agents "
            "depuis le panneau d'administration des acces."
        )
