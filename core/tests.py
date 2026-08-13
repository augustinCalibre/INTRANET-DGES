from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.constants import ROLE_ADMINISTRATEUR, ROLE_AGENT
from core.models import ConnexionLog


def make_user(username, role=ROLE_AGENT, password="StrongPass123!"):
    user = get_user_model().objects.create_user(username=username, password=password)
    profile = user.profil
    profile.role = role
    profile.actif = True
    profile.save()
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class ConnexionLogTests(TestCase):
    """Historique des connexions : reussites, echecs, provenance."""

    def setUp(self):
        self.agent = make_user("agent_journal")
        ConnexionLog.objects.all().delete()

    def test_une_connexion_reussie_est_enregistree(self):
        self.client.login(username="agent_journal", password="StrongPass123!")

        entree = ConnexionLog.objects.get()
        self.assertEqual(entree.resultat, ConnexionLog.Resultat.SUCCES)
        self.assertEqual(entree.utilisateur, self.agent)
        self.assertEqual(entree.identifiant_saisi, "agent_journal")

    def test_un_echec_est_enregistre_avec_l_identifiant_saisi(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": "agent_journal", "password": "MauvaisMotDePasse"},
        )

        entree = ConnexionLog.objects.get(resultat=ConnexionLog.Resultat.ECHEC)
        self.assertIsNone(entree.utilisateur)
        self.assertEqual(entree.identifiant_saisi, "agent_journal")
        self.assertTrue(entree.est_echec)

    def test_un_echec_sur_un_compte_inexistant_est_conserve(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": "intrus", "password": "peu importe"},
        )

        entree = ConnexionLog.objects.get(resultat=ConnexionLog.Resultat.ECHEC)
        self.assertEqual(entree.identifiant_saisi, "intrus")
        self.assertEqual(entree.libelle_compte, "intrus")

    def test_la_deconnexion_est_enregistree(self):
        self.client.login(username="agent_journal", password="StrongPass123!")
        self.client.post(reverse("accounts:logout"))

        self.assertTrue(
            ConnexionLog.objects.filter(resultat=ConnexionLog.Resultat.DECONNEXION).exists()
        )

    def test_l_adresse_transmise_par_le_proxy_est_retenue(self):
        """Derriere Nginx, REMOTE_ADDR est le proxy : on garde l'adresse d'origine."""
        self.client.post(
            reverse("accounts:login"),
            {"username": "agent_journal", "password": "StrongPass123!"},
            HTTP_X_FORWARDED_FOR="192.168.100.42, 10.0.0.1",
        )

        entree = ConnexionLog.objects.filter(resultat=ConnexionLog.Resultat.SUCCES).first()
        self.assertEqual(entree.adresse_ip, "192.168.100.42")

    def test_le_poste_est_tronque_a_la_longueur_du_champ(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": "agent_journal", "password": "StrongPass123!"},
            HTTP_USER_AGENT="N" * 400,
        )

        entree = ConnexionLog.objects.filter(resultat=ConnexionLog.Resultat.SUCCES).first()
        self.assertEqual(len(entree.poste), 255)


@override_settings(SECURE_SSL_REDIRECT=False)
class ConnexionHistoryViewTests(TestCase):
    def setUp(self):
        self.admin = make_user("ingenieur", ROLE_ADMINISTRATEUR)
        self.agent = make_user("agent_simple_journal")
        ConnexionLog.objects.create(
            utilisateur=self.agent,
            identifiant_saisi="agent_simple_journal",
            resultat=ConnexionLog.Resultat.SUCCES,
            adresse_ip="192.168.100.7",
        )
        ConnexionLog.objects.create(
            identifiant_saisi="intrus",
            resultat=ConnexionLog.Resultat.ECHEC,
            adresse_ip="10.10.10.10",
        )

    def test_l_historique_est_reserve_a_l_administration(self):
        self.client.force_login(self.agent)
        self.assertEqual(
            self.client.get(reverse("accounts:connexion_history")).status_code, 403
        )

    def test_l_administrateur_consulte_l_historique(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:connexion_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "192.168.100.7")
        self.assertContains(response, "intrus")

    def test_le_filtre_par_resultat_fonctionne(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("accounts:connexion_history"),
            {"resultat": ConnexionLog.Resultat.ECHEC},
        )

        self.assertContains(response, "intrus")
        self.assertNotContains(response, "192.168.100.7")

    def test_la_recherche_par_adresse_fonctionne(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:connexion_history"), {"q": "10.10.10.10"})

        self.assertContains(response, "intrus")
        self.assertNotContains(response, "192.168.100.7")


@override_settings(SECURE_SSL_REDIRECT=False)
class MessagingRedirectTests(TestCase):
    def test_messaging_redirect_requires_authentication(self):
        response = self.client.get(reverse("core:messaging"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('core:messaging')}",
            fetch_redirect_response=False,
        )

    @override_settings(MESSAGING_URL="https://messagerie.dges.local")
    def test_messaging_redirect_uses_configured_url(self):
        user = get_user_model().objects.create_user(
            username="test_agent",
            password="Dges2026!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("core:messaging"))

        self.assertRedirects(
            response,
            "https://messagerie.dges.local",
            fetch_redirect_response=False,
        )

    @override_settings(
        MESSAGING_URL="https://messagerie.dges.local:8443",
        # Declare explicitement l'absence d'URL de repli : sans cela le test
        # dependrait du .env de la machine, et changerait de resultat selon
        # l'installation.
        MESSAGING_FALLBACK_URL="",
        ALLOWED_HOSTS=["testserver", "192.168.100.5"],
    )
    def test_messaging_redirect_uses_request_ip_when_intranet_opened_by_ip(self):
        user = get_user_model().objects.create_user(
            username="agent_ip",
            password="Dges2026!",
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("core:messaging"),
            HTTP_HOST="192.168.100.5",
        )

        self.assertRedirects(
            response,
            "https://192.168.100.5:8443",
            fetch_redirect_response=False,
        )

    @override_settings(
        MESSAGING_URL="https://messagerie.dges.local:8443",
        MESSAGING_FALLBACK_URL="https://192.168.100.5:8443",
        ALLOWED_HOSTS=["testserver", "192.168.100.5"],
    )
    def test_messaging_redirect_uses_configured_fallback_url(self):
        user = get_user_model().objects.create_user(
            username="agent_fallback",
            password="Dges2026!",
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("core:messaging"),
            HTTP_HOST="192.168.100.5",
        )

        self.assertRedirects(
            response,
            "https://192.168.100.5:8443",
            fetch_redirect_response=False,
        )
