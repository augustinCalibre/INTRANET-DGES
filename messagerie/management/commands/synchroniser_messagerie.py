"""Aligne la messagerie sur l'annuaire de l'intranet.

Deux usages :

- **a la mise en service**, pour creer d'un coup les comptes des agents deja
  enregistres dans l'intranet ;
- **apres une panne** de la messagerie, pour rattraper les creations et les
  desactivations qui n'ont pas pu passer sur le moment.

La commande est faite pour etre relancee sans crainte : elle ne fait que ce
qui manque, et deux executions de suite donnent le meme resultat.
"""

from django.core.management.base import BaseCommand, CommandError

from messagerie import services
from messagerie.client import MessagerieIndisponible


class Command(BaseCommand):
    help = "Synchronise les comptes de la messagerie avec ceux de l'intranet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--conversations",
            action="store_true",
            help="Crée aussi une conversation Talk par service et une conversation générale.",
        )

    def handle(self, *args, **options):
        if not services.synchronisation_active():
            raise CommandError(
                "La synchronisation est désactivée (MESSAGERIE_SYNC_ENABLED). "
                "Activez-la dans le fichier .env avant de relancer."
            )

        try:
            resultats = services.synchroniser_tous()
        except MessagerieIndisponible as erreur:
            raise CommandError(f"Messagerie injoignable : {erreur}") from erreur

        for cle, titre in (
            ("cree", "Comptes créés"),
            ("mis_a_jour", "Comptes mis à jour"),
            ("desactive", "Comptes désactivés"),
            ("ignore", "Comptes ignorés (inactifs, sans compte de messagerie)"),
        ):
            noms = resultats[cle]
            if noms:
                self.stdout.write(f"{titre} ({len(noms)}) : {', '.join(noms)}")

        for nom, message in resultats["echec"]:
            self.stderr.write(self.style.ERROR(f"Échec pour {nom} : {message}"))

        if options["conversations"]:
            try:
                creees = services.assurer_conversations()
            except MessagerieIndisponible as erreur:
                raise CommandError(f"Conversations non créées : {erreur}") from erreur
            if creees:
                self.stdout.write(f"Conversations créées : {', '.join(creees)}")
            else:
                self.stdout.write("Conversations : toutes existaient déjà.")

        if resultats["echec"]:
            raise CommandError(
                f"{len(resultats['echec'])} compte(s) n'ont pas pu être synchronisés."
            )

        self.stdout.write(self.style.SUCCESS("Messagerie synchronisée."))
