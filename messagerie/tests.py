"""Tests de la synchronisation vers la messagerie.

Aucun de ces tests ne joint Nextcloud : la couche réseau est remplacée par un
double. Ce qui est vérifié ici, c'est la décision — quel appel est fait, dans
quel ordre, et surtout lequel n'est pas fait.

Deux règles priment, et ce sont elles que les tests protègent :

- désactiver un compte dans l'intranet doit fermer la messagerie. Un accès qui
  survit au départ d'un agent est le défaut le plus grave du dispositif ;
- une messagerie arrêtée ne doit jamais empêcher de créer un compte agent.
"""

from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from accounts.annuaire_dges import AGENTS, RESPONSABLES, SERVICES
from accounts.constants import ROLE_AGENT, ROLE_CHOICES
from accounts.models import Service
from messagerie import services
from messagerie.client import MessagerieIndisponible


def make_user(username="agent", role=ROLE_AGENT, service=None, actif=True):
    utilisateur = User.objects.create_user(
        username=username, password="StrongPass123!", first_name="Ama", last_name="KOUADIO"
    )
    profil = utilisateur.profil
    profil.role = role
    profil.service = service
    profil.actif = actif
    profil.save()
    return utilisateur


class AnnuaireDgesTests(TestCase):
    """L'annuaire est saisi à la main : ces tests en gardent la cohérence."""

    def test_les_identifiants_sont_uniques(self):
        identifiants = [fiche["identifiant"] for fiche in AGENTS]
        self.assertEqual(len(identifiants), len(set(identifiants)))

    def test_les_identifiants_sont_utilisables(self):
        """Ni espace, ni accent, ni majuscule : Nextcloud les refuserait."""
        for fiche in AGENTS:
            identifiant = fiche["identifiant"]
            self.assertTrue(identifiant.isascii(), identifiant)
            self.assertEqual(identifiant, identifiant.lower(), identifiant)
            self.assertNotIn(" ", identifiant)

    def test_chaque_agent_est_rattache_a_un_service_declare(self):
        for fiche in AGENTS:
            self.assertIn(fiche["service"], SERVICES, fiche["identifiant"])

    def test_les_roles_existent(self):
        roles = {valeur for valeur, _ in ROLE_CHOICES}
        for fiche in AGENTS:
            self.assertIn(fiche["role"], roles, fiche["identifiant"])

    def test_les_responsables_figurent_dans_l_annuaire(self):
        identifiants = {fiche["identifiant"] for fiche in AGENTS}
        for service, identifiant in RESPONSABLES.items():
            self.assertIn(service, SERVICES, service)
            self.assertIn(identifiant, identifiants, identifiant)

    def test_les_adresses_sont_exploitables(self):
        """Une adresse enregistrée doit pouvoir recevoir un message."""
        for fiche in AGENTS:
            adresse = fiche["email"]
            if not adresse:
                continue
            self.assertNotIn(" ", adresse, fiche["identifiant"])
            self.assertTrue(adresse.isascii(), fiche["identifiant"])
            nom, _, domaine = adresse.partition("@")
            self.assertTrue(nom and "." in domaine, adresse)

    def test_les_fonctions_tiennent_dans_le_champ(self):
        for fiche in AGENTS:
            self.assertLessEqual(len(fiche["fonction"]), 120, fiche["identifiant"])


@override_settings(MESSAGERIE_SYNC_ENABLED=False)
class SynchronisationDesactiveeTests(TestCase):
    def test_aucun_appel_quand_la_synchronisation_est_coupee(self):
        utilisateur = make_user()
        with mock.patch.object(services, "client") as faux:
            self.assertIsNone(services.synchroniser_sans_bloquer(utilisateur))
            faux.compte.assert_not_called()

    def test_la_fermeture_d_acces_ne_tente_rien_non_plus(self):
        with mock.patch.object(services, "client") as faux:
            self.assertIsNone(services.desactiver_acces_messagerie("agent"))
            faux.compte.assert_not_called()


@override_settings(MESSAGERIE_SYNC_ENABLED=True)
class SynchronisationTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Service Courrier", actif=True)
        self.patch = mock.patch.object(services, "client")
        self.client_messagerie = self.patch.start()
        self.addCleanup(self.patch.stop)
        self.client_messagerie.groupes_du_compte.return_value = []

    def test_un_compte_absent_est_cree_avec_ses_groupes(self):
        self.client_messagerie.compte.return_value = None
        utilisateur = make_user("kkoakou", service=self.service)

        issue = services.synchroniser_utilisateur(utilisateur, mot_de_passe="DGES-2026!")

        self.assertEqual(issue, "cree")
        appel = self.client_messagerie.creer_compte.call_args
        self.assertEqual(appel.args[0], "kkoakou")
        self.assertEqual(appel.args[1], "DGES-2026!")
        self.assertEqual(appel.kwargs["nom_affiche"], "Ama KOUADIO")
        self.assertIn(services.GROUPE_TOUS, appel.kwargs["groupes"])
        self.assertIn("svc-service-courrier", appel.kwargs["groupes"])

    def test_un_compte_desactive_ferme_la_messagerie(self):
        """La règle qui compte le jour où quelqu'un quitte la direction."""
        self.client_messagerie.compte.return_value = {"enabled": True}
        utilisateur = make_user("partant", service=self.service, actif=False)

        issue = services.synchroniser_utilisateur(utilisateur)

        self.assertEqual(issue, "desactive")
        self.client_messagerie.desactiver_compte.assert_called_once_with("partant")

    def test_un_compte_django_inactif_ferme_aussi_la_messagerie(self):
        self.client_messagerie.compte.return_value = {"enabled": True}
        utilisateur = make_user("suspendu", service=self.service)
        utilisateur.is_active = False
        utilisateur.save()

        self.assertEqual(services.synchroniser_utilisateur(utilisateur), "desactive")
        self.client_messagerie.desactiver_compte.assert_called_once_with("suspendu")

    def test_aucun_compte_n_est_cree_pour_un_agent_inactif(self):
        self.client_messagerie.compte.return_value = None
        utilisateur = make_user("jamais_venu", actif=False)

        self.assertEqual(services.synchroniser_utilisateur(utilisateur), "ignore")
        self.client_messagerie.creer_compte.assert_not_called()

    def test_le_mot_de_passe_n_est_pousse_que_s_il_est_fourni(self):
        """Sans mot de passe en clair, on ne touche pas à celui de l'agent."""
        self.client_messagerie.compte.return_value = {
            "enabled": True,
            "displayname": "Ama KOUADIO",
            "email": "",
        }
        utilisateur = make_user("kkoakou", service=self.service)

        services.synchroniser_utilisateur(utilisateur)
        self.client_messagerie.definir_mot_de_passe.assert_not_called()

        services.synchroniser_utilisateur(utilisateur, mot_de_passe="NouveauSecret1!")
        self.client_messagerie.definir_mot_de_passe.assert_called_once_with(
            "kkoakou", "NouveauSecret1!"
        )

    def test_un_agent_mute_quitte_les_conversations_de_son_ancien_service(self):
        autre = Service.objects.create(nom="Service Communication", actif=True)
        self.client_messagerie.compte.return_value = {
            "enabled": True,
            "displayname": "Ama KOUADIO",
            "email": "",
        }
        self.client_messagerie.groupes_du_compte.return_value = [
            services.GROUPE_TOUS,
            "svc-service-courrier",
        ]
        utilisateur = make_user("mute", service=autre)

        services.synchroniser_utilisateur(utilisateur)

        self.client_messagerie.retirer_du_groupe.assert_called_once_with(
            "mute", "svc-service-courrier"
        )
        self.client_messagerie.ajouter_au_groupe.assert_called_once_with(
            "mute", "svc-service-communication"
        )

    def test_un_groupe_hors_intranet_n_est_pas_retire(self):
        """Un groupe créé à la main dans Nextcloud pour un autre usage."""
        self.client_messagerie.compte.return_value = {
            "enabled": True,
            "displayname": "Ama KOUADIO",
            "email": "",
        }
        self.client_messagerie.groupes_du_compte.return_value = [
            services.GROUPE_TOUS,
            "comite-de-direction",
        ]
        utilisateur = make_user("kkoakou")

        services.synchroniser_utilisateur(utilisateur)
        self.client_messagerie.retirer_du_groupe.assert_not_called()

    def test_une_messagerie_arretee_ne_bloque_pas_la_creation_d_un_compte(self):
        self.client_messagerie.compte.side_effect = MessagerieIndisponible("arrêtée")
        self.client_messagerie.creer_groupe.side_effect = MessagerieIndisponible("arrêtée")
        utilisateur = make_user("nouvel_agent")

        avertissement = services.synchroniser_sans_bloquer(utilisateur, mot_de_passe="x")

        self.assertIsNotNone(avertissement)
        self.assertIn("messagerie", avertissement.lower())
        # Le compte intranet, lui, existe bel et bien.
        self.assertTrue(User.objects.filter(username="nouvel_agent").exists())

    def test_la_fermeture_d_acces_avertit_sans_lever(self):
        self.client_messagerie.compte.side_effect = MessagerieIndisponible("arrêtée")
        avertissement = services.desactiver_acces_messagerie("partant")
        self.assertIsNotNone(avertissement)
        self.assertIn("partant", avertissement)


@override_settings(MESSAGERIE_SYNC_ENABLED=True)
class IdentifiantsGroupesTests(TestCase):
    def test_le_groupe_derive_du_nom_du_service(self):
        service = Service.objects.create(nom="Service Validation Diplôme", actif=True)
        self.assertEqual(
            services.identifiant_groupe_service(service), "svc-service-validation-diplome"
        )

    def test_le_nom_affiche_retombe_sur_l_identifiant(self):
        utilisateur = User.objects.create_user(username="sansnom", password="StrongPass123!")
        self.assertEqual(services.nom_affiche(utilisateur), "sansnom")
