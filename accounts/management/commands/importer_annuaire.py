"""Cree les services et les comptes de la DGES a partir de l'annuaire reel.

La commande est faite pour etre relancee : elle ne cree que ce qui manque et
ne touche pas aux mots de passe deja changes par les agents. Deux executions
de suite donnent le meme resultat.

Elle ne supprime rien. Les services qui ne figurent plus dans l'organigramme
sont desactives, pas effaces : les courriers et documents deja rattaches
gardent leur historique, et un service reactive retrouve ses rattachements.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.annuaire_dges import AGENTS, RESPONSABLES, SERVICES
from accounts.models import Service, UserProfile
from messagerie import services as messagerie
from messagerie.client import MessagerieIndisponible

# Dix caracteres au minimum : c'est ce qu'exige la politique de mots de passe
# de Nextcloud, et le meme secret doit valoir pour l'intranet et la messagerie.
# Il ne survit pas a la premiere connexion, chaque agent devant le changer.
MOT_DE_PASSE_INITIAL = "DGES-2026!"


class Command(BaseCommand):
    help = "Importe l'annuaire de la DGES : services, comptes agents et accès messagerie."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mot-de-passe",
            default=MOT_DE_PASSE_INITIAL,
            help="Mot de passe initial commun, à changer à la première connexion.",
        )
        parser.add_argument(
            "--sans-messagerie",
            action="store_true",
            help="N'ouvre pas les accès à la messagerie (comptes intranet seuls).",
        )
        parser.add_argument(
            "--desactiver-comptes-demo",
            action="store_true",
            help="Désactive les comptes de démonstration absents de l'annuaire.",
        )
        parser.add_argument(
            "--reinitialiser-mots-de-passe",
            action="store_true",
            help=(
                "Remet le mot de passe initial sur les comptes existants. "
                "À n'utiliser qu'avant la première distribution des accès : "
                "après, cela effacerait le mot de passe choisi par chaque agent."
            ),
        )

    def handle(self, *args, **options):
        mot_de_passe = options["mot_de_passe"]

        with transaction.atomic():
            services_crees = self._importer_services()
            comptes = self._importer_agents(
                mot_de_passe, forcer=options["reinitialiser_mots_de_passe"]
            )
            self._designer_responsables()
            demo = self._comptes_hors_annuaire()
            if options["desactiver_comptes_demo"]:
                self._desactiver(demo)

        self._rendre_compte(services_crees, comptes, demo, options)

        if not options["sans_messagerie"]:
            self._ouvrir_messagerie(mot_de_passe)

    # ------------------------------------------------------------ services

    def _importer_services(self):
        crees = []
        for nom in SERVICES:
            service, cree = Service.objects.get_or_create(
                nom=nom,
                defaults={"actif": True, "est_service_courrier": nom == "Service Courrier"},
            )
            if cree:
                crees.append(nom)
            elif not service.actif:
                service.actif = True
                service.save(update_fields=["actif"])

        # Les services absents de l'organigramme sont mis de cote sans etre
        # supprimes : un courrier impute a un service disparu doit rester
        # lisible.
        obsoletes = Service.objects.filter(actif=True).exclude(nom__in=SERVICES)
        self.services_desactives = list(obsoletes.values_list("nom", flat=True))
        obsoletes.update(actif=False)

        return crees

    # -------------------------------------------------------------- agents

    def _importer_agents(self, mot_de_passe, forcer=False):
        resultats = {"crees": [], "mis_a_jour": []}

        for fiche in AGENTS:
            service = Service.objects.filter(nom=fiche["service"]).first()
            utilisateur, cree = User.objects.get_or_create(
                username=fiche["identifiant"],
                defaults={
                    "first_name": fiche["prenom"],
                    "last_name": fiche["nom"],
                    "email": fiche["email"],
                },
            )

            if cree:
                utilisateur.set_password(mot_de_passe)
                resultats["crees"].append(fiche["identifiant"])
            else:
                # Le mot de passe d'un compte existant n'est pas retabli sans
                # qu'on le demande : un agent qui a deja choisi le sien ne doit
                # pas le voir revenir au mot de passe commun a chaque execution.
                if forcer:
                    utilisateur.set_password(mot_de_passe)
                resultats["mis_a_jour"].append(fiche["identifiant"])

            utilisateur.first_name = fiche["prenom"]
            utilisateur.last_name = fiche["nom"]
            utilisateur.email = fiche["email"]
            utilisateur.is_active = True
            utilisateur.save()

            profil, _ = UserProfile.objects.get_or_create(utilisateur=utilisateur)
            profil.service = service
            profil.fonction = fiche["fonction"]
            profil.role = fiche["role"]
            profil.telephone = fiche.get("telephone", "")
            profil.actif = True
            if cree or forcer:
                # Le mot de passe commun ne doit pas survivre a la premiere
                # connexion : c'est la seule facon qu'il ne finisse pas note
                # sur un papier au dos d'un clavier.
                profil.doit_changer_mot_de_passe = True
            profil.save()

        return resultats

    def _designer_responsables(self):
        for nom_service, identifiant in RESPONSABLES.items():
            service = Service.objects.filter(nom=nom_service).first()
            responsable = User.objects.filter(username=identifiant).first()
            if service and responsable and service.responsable_id != responsable.pk:
                service.responsable = responsable
                service.save(update_fields=["responsable"])

    def _comptes_hors_annuaire(self):
        identifiants = {fiche["identifiant"] for fiche in AGENTS}
        return list(
            User.objects.filter(is_active=True)
            .exclude(username__in=identifiants)
            .exclude(is_superuser=True)
            .values_list("username", flat=True)
        )

    def _desactiver(self, identifiants):
        for identifiant in identifiants:
            utilisateur = User.objects.get(username=identifiant)
            utilisateur.is_active = False
            utilisateur.save(update_fields=["is_active"])
            profil = getattr(utilisateur, "profil", None)
            if profil:
                profil.actif = False
                profil.save(update_fields=["actif"])

    # ---------------------------------------------------------- messagerie

    def _ouvrir_messagerie(self, mot_de_passe):
        if not messagerie.synchronisation_active():
            self.stdout.write(
                self.style.WARNING("Messagerie : synchronisation désactivée, accès non ouverts.")
            )
            return

        self.stdout.write("")
        self.stdout.write("Ouverture des accès à la messagerie…")
        ouverts, echecs = [], []
        for fiche in AGENTS:
            utilisateur = User.objects.get(username=fiche["identifiant"])
            try:
                messagerie.assurer_groupes_services()
                messagerie.synchroniser_utilisateur(utilisateur, mot_de_passe=mot_de_passe)
                ouverts.append(fiche["identifiant"])
            except MessagerieIndisponible as erreur:
                echecs.append((fiche["identifiant"], str(erreur)))

        if ouverts:
            self.stdout.write(f"  accès ouverts ({len(ouverts)}) : {', '.join(ouverts)}")
        for identifiant, message in echecs:
            self.stderr.write(self.style.ERROR(f"  {identifiant} : {message}"))

        try:
            conversations = messagerie.assurer_conversations()
        except MessagerieIndisponible as erreur:
            self.stderr.write(self.style.ERROR(f"  conversations : {erreur}"))
        else:
            if conversations:
                self.stdout.write(f"  conversations créées : {', '.join(conversations)}")

    # ------------------------------------------------------------- rapport

    def _rendre_compte(self, services_crees, comptes, demo, options):
        if services_crees:
            self.stdout.write(f"Services créés ({len(services_crees)}) : {', '.join(services_crees)}")
        if self.services_desactives:
            self.stdout.write(
                f"Services désactivés ({len(self.services_desactives)}) : "
                f"{', '.join(self.services_desactives)}"
            )
        if comptes["crees"]:
            self.stdout.write(
                f"Comptes créés ({len(comptes['crees'])}) : {', '.join(comptes['crees'])}"
            )
        if comptes["mis_a_jour"]:
            self.stdout.write(
                f"Comptes mis à jour ({len(comptes['mis_a_jour'])}) : "
                f"{', '.join(comptes['mis_a_jour'])}"
            )
        if demo:
            etat = "désactivés" if options["desactiver_comptes_demo"] else "hors annuaire (conservés)"
            self.stdout.write(f"Comptes {etat} ({len(demo)}) : {', '.join(demo)}")

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Annuaire importé. Mot de passe initial commun : {options['mot_de_passe']} — "
                "chaque agent devra le changer à sa première connexion, et le nouveau "
                "vaudra aussi pour la messagerie."
            )
        )
