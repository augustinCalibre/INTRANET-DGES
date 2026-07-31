"""Tests de la matrice de droits.

C'est la couche qui porte la securite de l'application : une regression
silencieuse ici ouvrirait un acces non autorise sans qu'aucun autre test ne
le signale.
"""

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.access import sync_all_users
from accounts.constants import (
    ROLE_ADMINISTRATEUR,
    ROLE_AGENT,
    ROLE_AGENT_ETUDE,
    ROLE_CHOICES,
    ROLE_COURRIER,
    ROLE_DIRECTEUR_GENERAL,
    ROLE_GROUP_NAMES,
    ROLE_SECRETARIAT,
    ROLE_SECRETARIAT_ADJOINT,
)
from accounts.models import Service, UserProfile
from core.permissions import (
    can_access_courriers,
    can_access_diplomas,
    can_manage_accounts,
    can_manage_all_meetings,
    can_manage_courriers,
    can_manage_diplomas,
    can_manage_documents,
    can_manage_visitors,
    can_transmit_to_dg,
    can_validate_as_dg,
    can_view_accounts,
    can_view_all_activity,
)

TOUS_LES_ROLES = [valeur for valeur, _ in ROLE_CHOICES]


def make_user(username, role, service=None):
    user = User.objects.create_user(username=username, password="StrongPass123!")
    profile = user.profil
    profile.role = role
    profile.service = service
    profile.actif = True
    profile.save()
    return user


class RoleMatrixTests(TestCase):
    """Chaque capacite est verifiee pour les sept roles, sans exception."""

    # capacite -> roles qui doivent la detenir. Tout role absent doit se la
    # voir refuser : le test verifie les deux cotes.
    ATTENDU = {
        can_view_all_activity: {ROLE_DIRECTEUR_GENERAL, ROLE_ADMINISTRATEUR},
        can_manage_visitors: {ROLE_SECRETARIAT, ROLE_SECRETARIAT_ADJOINT, ROLE_ADMINISTRATEUR},
        # Le secretariat adjoint « declenche les courriers » : il enregistre.
        can_manage_courriers: {ROLE_COURRIER, ROLE_SECRETARIAT_ADJOINT, ROLE_ADMINISTRATEUR},
        can_access_courriers: {
            ROLE_COURRIER,
            ROLE_SECRETARIAT_ADJOINT,
            ROLE_SECRETARIAT,
            ROLE_DIRECTEUR_GENERAL,
            ROLE_ADMINISTRATEUR,
        },
        can_manage_documents: {
            ROLE_COURRIER,
            ROLE_SECRETARIAT,
            ROLE_SECRETARIAT_ADJOINT,
            ROLE_ADMINISTRATEUR,
        },
        can_transmit_to_dg: {ROLE_SECRETARIAT, ROLE_ADMINISTRATEUR},
        can_validate_as_dg: {ROLE_DIRECTEUR_GENERAL, ROLE_ADMINISTRATEUR},
        can_manage_diplomas: {ROLE_AGENT_ETUDE, ROLE_ADMINISTRATEUR},
        can_access_diplomas: {
            ROLE_AGENT_ETUDE,
            ROLE_SECRETARIAT,
            ROLE_DIRECTEUR_GENERAL,
            ROLE_ADMINISTRATEUR,
        },
        can_manage_all_meetings: {ROLE_SECRETARIAT, ROLE_SECRETARIAT_ADJOINT, ROLE_ADMINISTRATEUR},
        can_manage_accounts: {ROLE_ADMINISTRATEUR},
        can_view_accounts: {ROLE_ADMINISTRATEUR, ROLE_DIRECTEUR_GENERAL},
    }

    @classmethod
    def setUpTestData(cls):
        cls.comptes = {role: make_user(f"compte_{role}", role) for role in TOUS_LES_ROLES}

    def test_la_matrice_est_respectee_pour_chaque_role(self):
        for capacite, roles_autorises in self.ATTENDU.items():
            for role, user in self.comptes.items():
                attendu = role in roles_autorises
                obtenu = bool(capacite(user))
                self.assertEqual(
                    obtenu,
                    attendu,
                    msg=(
                        f"{capacite.__name__} pour le rôle « {role} » : "
                        f"obtenu {obtenu}, attendu {attendu}"
                    ),
                )

    def test_le_role_agent_ne_detient_aucune_capacite_sensible(self):
        agent = self.comptes[ROLE_AGENT]
        for capacite in self.ATTENDU:
            self.assertFalse(capacite(agent), msg=capacite.__name__)

    def test_un_visiteur_anonyme_ne_detient_rien(self):
        class Anonyme:
            is_authenticated = False
            is_superuser = False

        anonyme = Anonyme()
        for capacite in self.ATTENDU:
            self.assertFalse(capacite(anonyme), msg=capacite.__name__)

    def test_le_superutilisateur_detient_tout(self):
        root = User.objects.create_superuser(username="root", email="", password="StrongPass123!")
        for capacite in self.ATTENDU:
            self.assertTrue(capacite(root), msg=capacite.__name__)

    def test_le_courrier_ne_transmet_pas_lui_meme_au_dg(self):
        """Regle structurante : le visa du secretariat n'est pas contournable."""
        courrier = self.comptes[ROLE_COURRIER]
        self.assertTrue(can_manage_courriers(courrier))
        self.assertFalse(can_transmit_to_dg(courrier))
        self.assertFalse(can_validate_as_dg(courrier))

    def test_le_dg_ne_saisit_ni_visiteur_ni_diplome(self):
        dg = self.comptes[ROLE_DIRECTEUR_GENERAL]
        self.assertFalse(can_manage_visitors(dg))
        self.assertFalse(can_manage_diplomas(dg))
        self.assertTrue(can_validate_as_dg(dg))


class GroupSynchronisationTests(TestCase):
    def test_un_compte_est_place_dans_le_groupe_de_son_role(self):
        user = make_user("agent_groupe", ROLE_AGENT_ETUDE)
        noms = set(user.groups.values_list("name", flat=True))
        self.assertEqual(noms, {ROLE_GROUP_NAMES[ROLE_AGENT_ETUDE]})

    def test_le_changement_de_role_deplace_le_compte_de_groupe(self):
        user = make_user("agent_mutation", ROLE_AGENT)
        profile = user.profil
        profile.role = ROLE_SECRETARIAT
        profile.save()

        noms = set(user.groups.values_list("name", flat=True))
        self.assertEqual(noms, {ROLE_GROUP_NAMES[ROLE_SECRETARIAT]})

    def test_seul_l_administrateur_accede_a_l_administration_django(self):
        admin = make_user("admin_dges_test", ROLE_ADMINISTRATEUR)
        secretaire = make_user("secretaire_test", ROLE_SECRETARIAT)

        admin.refresh_from_db()
        secretaire.refresh_from_db()
        self.assertTrue(admin.is_staff)
        self.assertFalse(secretaire.is_staff)

    def test_un_profil_desactive_desactive_le_compte(self):
        user = make_user("agent_sortant", ROLE_AGENT)
        profile = user.profil
        profile.actif = False
        profile.save()

        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_les_groupes_de_l_ancien_modele_ont_disparu(self):
        obsoletes = Group.objects.filter(
            name__in=[
                "DGES - Agent simple",
                "DGES - Responsable service",
                "DGES - Service Courrier",
            ]
        )
        self.assertFalse(obsoletes.exists())

    def test_sync_all_users_cree_les_profils_manquants(self):
        user = User.objects.create_user(username="sans_profil", password="StrongPass123!")
        UserProfile.objects.filter(utilisateur=user).delete()

        total = sync_all_users()

        self.assertGreaterEqual(total, 1)
        self.assertTrue(UserProfile.objects.filter(utilisateur=user).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class AccountPanelAccessTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Informatique", actif=True)
        self.admin = make_user("ingenieur", ROLE_ADMINISTRATEUR, self.service)
        self.dg = make_user("directeur", ROLE_DIRECTEUR_GENERAL, self.service)
        self.secretaire = make_user("secretaire", ROLE_SECRETARIAT, self.service)
        self.agent = make_user("agent", ROLE_AGENT, self.service)

    def test_l_annuaire_est_ouvert_a_l_admin_et_au_dg(self):
        for user in (self.admin, self.dg):
            self.client.force_login(user)
            response = self.client.get(reverse("accounts:user_list"))
            self.assertEqual(response.status_code, 200, msg=user.username)

    def test_l_annuaire_est_refuse_aux_autres(self):
        for user in (self.secretaire, self.agent):
            self.client.force_login(user)
            response = self.client.get(reverse("accounts:user_list"))
            self.assertEqual(response.status_code, 403, msg=user.username)

    def test_seul_l_admin_cree_un_compte(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("accounts:user_create")).status_code, 200)

        for user in (self.dg, self.secretaire, self.agent):
            self.client.force_login(user)
            response = self.client.get(reverse("accounts:user_create"))
            self.assertEqual(response.status_code, 403, msg=user.username)

    def test_le_dg_ne_modifie_pas_un_compte(self):
        self.client.force_login(self.dg)
        response = self.client.get(reverse("accounts:user_edit", args=[self.agent.pk]))
        self.assertEqual(response.status_code, 403)

    def test_un_administrateur_ne_supprime_pas_son_propre_compte(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:user_delete", args=[self.admin.pk]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_le_panneau_d_acces_est_ouvert_a_l_admin_et_au_dg(self):
        for user in (self.admin, self.dg):
            self.client.force_login(user)
            response = self.client.get(reverse("accounts:access_panel"))
            self.assertEqual(response.status_code, 200, msg=user.username)
            self.assertContains(response, "Comptes, rôles et services")

    def test_le_panneau_d_acces_est_refuse_aux_autres(self):
        for user in (self.secretaire, self.agent):
            self.client.force_login(user)
            response = self.client.get(reverse("accounts:access_panel"))
            self.assertEqual(response.status_code, 403, msg=user.username)

    def test_l_annuaire_se_filtre_par_role_et_par_etat(self):
        self.client.force_login(self.admin)

        # On cible la colonne du tableau : le nom de l'administrateur connecte
        # figure aussi dans l'en-tete de page, ce qui rendrait une recherche
        # sur le corps entier inexploitable.
        def identifiants(response):
            import re

            return set(
                re.findall(r'data-label="Identifiant">([^<]+)<', response.content.decode())
            )

        response = self.client.get(reverse("accounts:user_list"), {"role": ROLE_SECRETARIAT})
        self.assertEqual(identifiants(response), {"secretaire"})

        self.secretaire.profil.actif = False
        self.secretaire.profil.save()
        response = self.client.get(reverse("accounts:user_list"), {"etat": "inactif"})
        self.assertEqual(identifiants(response), {"secretaire"})

        response = self.client.get(reverse("accounts:user_list"), {"etat": "actif"})
        self.assertNotIn("secretaire", identifiants(response))


@override_settings(SECURE_SSL_REDIRECT=False)
class ServiceManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("ingenieur", ROLE_ADMINISTRATEUR)
        self.dg = make_user("directeur", ROLE_DIRECTEUR_GENERAL)
        self.service = Service.objects.create(nom="Planification", actif=True)

    def test_seul_l_admin_gere_les_services(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("accounts:service_list")).status_code, 200)

        self.client.force_login(self.dg)
        self.assertEqual(self.client.get(reverse("accounts:service_list")).status_code, 403)

    def test_creation_d_un_service(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:service_create"),
            {"nom": "Documentation", "description": "", "actif": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Service.objects.filter(nom="Documentation").exists())

    def test_un_nom_de_service_en_doublon_est_refuse(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:service_create"),
            {"nom": "planification", "description": "", "actif": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "porte déjà ce nom")

    def test_un_service_avec_des_agents_ne_peut_pas_etre_supprime(self):
        make_user("agent_du_service", ROLE_AGENT, self.service)
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("accounts:service_delete", args=[self.service.pk]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Service.objects.filter(pk=self.service.pk).exists())
        self.assertContains(response, "désactivez-le plutôt")

    def test_un_service_vide_peut_etre_supprime(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:service_delete", args=[self.service.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Service.objects.filter(pk=self.service.pk).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class PasswordDistributionTests(TestCase):
    """Distribution des acces : mot de passe provisoire puis changement impose."""

    def setUp(self):
        self.admin = make_user("ingenieur", ROLE_ADMINISTRATEUR)
        self.agent = make_user("agent", ROLE_AGENT)

    def test_la_reinitialisation_impose_un_changement(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:user_password_reset", args=[self.agent.pk]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        self.agent.profil.refresh_from_db()
        self.assertTrue(self.agent.profil.doit_changer_mot_de_passe)
        self.assertContains(response, "Mot de passe provisoire")

    def test_seul_l_admin_reinitialise_un_mot_de_passe(self):
        self.client.force_login(self.agent)
        response = self.client.post(reverse("accounts:user_password_reset", args=[self.agent.pk]))
        self.assertEqual(response.status_code, 403)

    def test_le_compte_est_redirige_vers_le_changement_de_mot_de_passe(self):
        profile = self.agent.profil
        profile.doit_changer_mot_de_passe = True
        profile.save()

        self.client.force_login(self.agent)
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(response, reverse("accounts:password_change"))

    def test_la_page_de_changement_reste_accessible(self):
        profile = self.agent.profil
        profile.doit_changer_mot_de_passe = True
        profile.save()

        self.client.force_login(self.agent)
        response = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Changement obligatoire")

    def test_le_changement_leve_la_contrainte_et_garde_la_session(self):
        self.agent.set_password("AncienMotDePasse123!")
        self.agent.save()
        profile = self.agent.profil
        profile.doit_changer_mot_de_passe = True
        profile.save()

        self.client.login(username="agent", password="AncienMotDePasse123!")
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "AncienMotDePasse123!",
                "new_password1": "NouveauMotDePasse456!",
                "new_password2": "NouveauMotDePasse456!",
            },
        )
        self.assertRedirects(response, reverse("dashboard:home"))

        profile.refresh_from_db()
        self.assertFalse(profile.doit_changer_mot_de_passe)

        # La session reste valide : l'agent n'est pas deconnecte par son propre
        # changement de mot de passe.
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)

    def test_un_compte_sans_contrainte_navigue_normalement(self):
        self.client.force_login(self.agent)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)

    def test_l_activation_peut_etre_basculee(self):
        self.client.force_login(self.admin)

        self.client.post(reverse("accounts:user_toggle_active", args=[self.agent.pk]))
        self.agent.profil.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.profil.actif)
        self.assertFalse(self.agent.is_active, "Le compte Django doit suivre le profil.")

        self.client.post(reverse("accounts:user_toggle_active", args=[self.agent.pk]))
        self.agent.profil.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.profil.actif)
        self.assertTrue(self.agent.is_active)

    def test_un_admin_ne_desactive_pas_son_propre_compte(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:user_toggle_active", args=[self.admin.pk]))

        self.admin.profil.refresh_from_db()
        self.assertTrue(self.admin.profil.actif)
