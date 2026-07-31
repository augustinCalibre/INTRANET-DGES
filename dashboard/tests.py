"""Tests du tableau de bord.

Deux enjeux : la mise en forme des visualisations, et le fait que le tableau de
bord ne montre a chacun que ce que ses droits autorisent.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.constants import (
    ROLE_AGENT,
    ROLE_AGENT_ETUDE,
    ROLE_COURRIER,
    ROLE_DIRECTEUR_GENERAL,
    ROLE_SECRETARIAT,
)
from accounts.models import Service
from courriers.models import Courrier
from diplomas.models import Diplome, LotDiplomes
from tasks.models import Task

from .charts import build_distribution, build_service_load


def make_user(username, role=ROLE_AGENT, service=None):
    user = User.objects.create_user(username=username, password="StrongPass123!")
    profile = user.profil
    profile.role = role
    profile.service = service
    profile.actif = True
    profile.save()
    return user


class DistributionTests(TestCase):
    def test_les_largeurs_sont_relatives_au_maximum(self):
        barres = build_distribution(
            [
                {"key": "a", "label": "A", "total": 10},
                {"key": "b", "label": "B", "total": 5},
                {"key": "c", "label": "C", "total": 0},
            ],
            "/registre/",
        )

        self.assertEqual(barres[0]["largeur"], 100)
        self.assertEqual(barres[1]["largeur"], 50)
        self.assertEqual(barres[2]["largeur"], 0, "Un total nul ne dessine pas de barre.")

    def test_les_parts_sont_calculees_sur_le_total(self):
        barres = build_distribution(
            [
                {"key": "a", "label": "A", "total": 3},
                {"key": "b", "label": "B", "total": 1},
            ],
            "/registre/",
        )

        self.assertEqual(barres[0]["part"], 75)
        self.assertEqual(barres[1]["part"], 25)

    def test_la_rampe_suit_l_avancement_du_circuit(self):
        """Echelle ordonnee : le pas s'assombrit de la premiere a la derniere etape."""
        barres = build_distribution(
            [{"key": str(i), "label": str(i), "total": 1} for i in range(5)],
            "/registre/",
        )

        pas = [barre["step"] for barre in barres]
        self.assertEqual(pas, [0, 1, 2, 3, 4])
        self.assertEqual(pas, sorted(pas), "Le pas doit croitre avec l'etape.")

    def test_la_rampe_reste_dans_les_bornes_avec_beaucoup_d_etapes(self):
        barres = build_distribution(
            [{"key": str(i), "label": str(i), "total": 1} for i in range(8)],
            "/registre/",
        )

        for barre in barres:
            self.assertIn(barre["step"], range(5))

    def test_chaque_barre_porte_son_lien_de_filtrage(self):
        barres = build_distribution(
            [{"key": "transmis_dg", "label": "Transmis", "total": 2}],
            "/courriers/",
        )
        self.assertEqual(barres[0]["url"], "/courriers/?statut=transmis_dg")

    def test_une_liste_vide_ne_produit_aucune_barre(self):
        self.assertEqual(build_distribution([], "/registre/"), [])

    def test_des_totaux_tous_nuls_ne_divisent_pas_par_zero(self):
        barres = build_distribution(
            [
                {"key": "a", "label": "A", "total": 0},
                {"key": "b", "label": "B", "total": 0},
            ],
            "/registre/",
        )
        self.assertEqual([barre["part"] for barre in barres], [0, 0])
        self.assertEqual([barre["largeur"] for barre in barres], [0, 0])


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardVisibilityTests(TestCase):
    """Le tableau de bord respecte la matrice de droits."""

    def setUp(self):
        self.service = Service.objects.create(nom="Secrétariat Général", actif=True)
        self.dg = make_user("directeur", ROLE_DIRECTEUR_GENERAL, self.service)
        self.secretaire = make_user("secretaire", ROLE_SECRETARIAT, self.service)
        self.agent_courrier = make_user("agent_courrier", ROLE_COURRIER, self.service)
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE, self.service)
        self.agent = make_user("agent", ROLE_AGENT, self.service)

        self.courrier = Courrier.objects.create(
            objet="Demande d'équivalence",
            expediteur="Université de Kinshasa",
            destinataire_service=self.service,
            statut=Courrier.Status.TRANSMIS_DG,
        )
        self.lot = LotDiplomes.objects.create(
            etablissement="ISP Gombe",
            nombre_annonce=2,
            statut=LotDiplomes.Status.TRANSMIS_DG,
        )
        Diplome.objects.create(lot=self.lot, nom_beneficiaire="Awa Mbala", numero_diplome="D-001")
        Task.objects.create(
            titre="Préparer la note de synthèse",
            description="À valider",
            statut=Task.Status.TRAITE,
            service_concerne=self.service,
            cree_par=self.secretaire,
        )

    def test_le_dg_voit_les_deux_files_de_decision(self):
        self.client.force_login(self.dg)
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Courriers à viser")
        self.assertContains(response, "Lots de diplômes à signer")
        self.assertContains(response, self.courrier.reference)
        self.assertContains(response, self.lot.reference)

    def test_le_secretariat_voit_la_file_de_transmission_pas_celle_du_visa(self):
        self.client.force_login(self.secretaire)
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Courriers à transmettre au DG")
        self.assertNotContains(response, "Courriers à viser")

    def test_un_agent_ordinaire_ne_voit_ni_courriers_ni_diplomes(self):
        self.client.force_login(self.agent)
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Lots de diplômes à signer")
        self.assertNotContains(response, self.courrier.reference)

    def test_l_agent_d_etude_voit_les_lots_mais_pas_le_registre_courrier(self):
        self.client.force_login(self.agent_etude)
        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(response, "Lots de diplômes à signer")
        self.assertNotContains(response, self.courrier.reference)

    def test_le_selecteur_de_periode_est_pris_en_compte(self):
        self.client.force_login(self.dg)

        for cle, libelle in (("7", "7 jours"), ("90", "90 jours")):
            response = self.client.get(reverse("dashboard:home"), {"periode": cle})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, libelle)

    def test_une_periode_invalide_retombe_sur_la_valeur_par_defaut(self):
        self.client.force_login(self.dg)
        response = self.client.get(reverse("dashboard:home"), {"periode": "999"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "30 jours")

    def test_les_barres_sont_rendues_avec_leur_pas_de_rampe(self):
        self.client.force_login(self.dg)
        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(response, "viz-bar-fill step-")
        self.assertContains(response, "Répartition par étape")

    def test_aucun_commentaire_de_gabarit_n_est_visible(self):
        """La syntaxe {# … #} ne vaut que sur une seule ligne.

        Écrite sur deux lignes, elle n'est pas reconnue comme un commentaire et
        s'affiche telle quelle à l'écran. Le défaut est passé en production une
        fois ; ce test le rend impossible.
        """
        self.client.force_login(self.dg)
        corps = self.client.get(reverse("dashboard:home")).content.decode()

        for marqueur in ("{#", "#}", "{% comment %}", "{% endcomment %}"):
            self.assertNotIn(marqueur, corps, msg=f"Marqueur de gabarit visible : {marqueur}")

    def test_le_tableau_de_bord_exige_une_authentification(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])


class ServiceLoadTests(TestCase):
    def test_la_barre_de_charge_est_relative_au_service_le_plus_charge(self):
        class FauxService:
            def __init__(self, taches):
                self.taches_ouvertes = taches

        lignes = build_service_load([FauxService(8), FauxService(4), FauxService(0)])

        self.assertEqual(lignes[0]["largeur"], 100)
        self.assertEqual(lignes[1]["largeur"], 50)
        self.assertEqual(lignes[2]["largeur"], 0)

    def test_aucun_service_ne_produit_aucune_ligne(self):
        self.assertEqual(build_service_load([]), [])
