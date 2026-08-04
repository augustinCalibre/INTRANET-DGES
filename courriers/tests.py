"""Tests du circuit du courrier.

Le point verifie en priorite : aucune etape ne peut etre sautee, et le visa du
secretariat n'est pas contournable.
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
    ROLE_SECRETARIAT_ADJOINT,
)
from accounts.models import Service
from core.models import Notification

from tasks.models import Task

from .models import (
    CorrespondantExterne,
    Courrier,
    InstructionCourrier,
    generate_courrier_reference,
    normaliser_nom,
)
from .services import build_imputation_grid
from .workflow import apply_transition, get_available_transitions

Statut = Courrier.Status


def make_user(username, role, service=None):
    user = User.objects.create_user(username=username, password="StrongPass123!")
    profile = user.profil
    profile.role = role
    profile.service = service
    profile.actif = True
    profile.save()
    return user


class ReferenceTests(TestCase):
    def test_les_references_s_incrementent(self):
        premier = Courrier.objects.create(objet="Demande d'équivalence", expediteur="Université de Kinshasa")
        second = Courrier.objects.create(objet="Rapport annuel", expediteur="ISP Gombe")

        annee = premier.date_reception.year
        self.assertEqual(premier.reference, f"COUR-{annee}-001")
        self.assertEqual(second.reference, f"COUR-{annee}-002")

    def test_une_reference_explicite_est_conservee(self):
        courrier = Courrier.objects.create(
            reference="COUR-2026-100",
            objet="Note de service",
            expediteur="Ministère",
        )
        self.assertEqual(courrier.reference, "COUR-2026-100")

    def test_une_reference_mal_formee_ne_bloque_pas(self):
        annee = generate_courrier_reference().split("-")[1]
        Courrier.objects.create(reference=f"COUR-{annee}-XYZ", objet="Test", expediteur="Test")
        self.assertTrue(generate_courrier_reference().startswith(f"COUR-{annee}-"))


@override_settings(SECURE_SSL_REDIRECT=False)
class CircuitTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Secrétariat Général", actif=True)
        self.courrier_agent = make_user("agent_courrier", ROLE_COURRIER, self.service)
        self.adjoint = make_user("adjoint", ROLE_SECRETARIAT_ADJOINT, self.service)
        self.secretaire = make_user("secretaire", ROLE_SECRETARIAT, self.service)
        self.dg = make_user("directeur", ROLE_DIRECTEUR_GENERAL, self.service)
        self.agent = make_user("agent", ROLE_AGENT, self.service)

        self.courrier = Courrier.objects.create(
            objet="Demande d'équivalence de diplôme",
            expediteur="Université de Lubumbashi",
            destinataire_service=self.service,
            receptionne_par=self.courrier_agent,
            cree_par=self.courrier_agent,
        )

    def _traiter(self):
        for cible in (Statut.EN_TRAITEMENT, Statut.TRANSMIS_SECRETARIAT):
            ok, message = apply_transition(self.courrier, cible, self.courrier_agent)
            self.assertTrue(ok, message)

    def _transmettre_au_dg(self):
        ok, message = apply_transition(self.courrier, Statut.TRANSMIS_DG, self.secretaire)
        self.assertTrue(ok, message)

    def test_le_service_courrier_traite_et_transmet_au_secretariat(self):
        self._traiter()
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, Statut.TRANSMIS_SECRETARIAT)
        self.assertIsNotNone(self.courrier.date_transmission_secretariat)

    def test_le_secretariat_adjoint_peut_aussi_traiter(self):
        ok, message = apply_transition(self.courrier, Statut.EN_TRAITEMENT, self.adjoint)
        self.assertTrue(ok, message)

    def test_un_agent_ordinaire_ne_traite_rien(self):
        ok, message = apply_transition(self.courrier, Statut.EN_TRAITEMENT, self.agent)
        self.assertFalse(ok)
        self.assertIn("service courrier", message)

    def test_le_service_courrier_ne_saisit_pas_le_dg_directement(self):
        """Le cœur de la règle : pas de raccourci vers le bureau du DG."""
        self._traiter()
        ok, message = apply_transition(self.courrier, Statut.TRANSMIS_DG, self.courrier_agent)
        self.assertFalse(ok)
        self.assertIn("Secrétariat", message)
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, Statut.TRANSMIS_SECRETARIAT)

    def test_un_courrier_non_traite_ne_peut_pas_etre_transmis_au_dg(self):
        ok, message = apply_transition(self.courrier, Statut.TRANSMIS_DG, self.secretaire)
        self.assertFalse(ok)
        self.assertIn("circuit", message)

    def test_le_secretariat_vise_et_transmet(self):
        self._traiter()
        self._transmettre_au_dg()
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, Statut.TRANSMIS_DG)
        self.assertEqual(self.courrier.transmis_par, self.secretaire)

    def test_le_service_courrier_ne_vise_pas(self):
        """Le visa appartient au DG ; le secrétariat peut le reporter."""
        self._traiter()
        self._transmettre_au_dg()

        ok, message = apply_transition(self.courrier, Statut.VISE_DG, self.courrier_agent)
        self.assertFalse(ok)
        self.assertIn("secrétariat", message)

        # Le secrétariat reporte la décision annotée sur la fiche papier.
        ok, message = apply_transition(self.courrier, Statut.VISE_DG, self.secretaire)
        self.assertTrue(ok, message)

    def test_le_dg_vise_lui_meme(self):
        self._traiter()
        self._transmettre_au_dg()

        ok, message = apply_transition(
            self.courrier,
            Statut.VISE_DG,
            self.dg,
            instruction="À traiter par le service des équivalences sous huit jours.",
        )
        self.assertTrue(ok, message)
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, Statut.VISE_DG)
        self.assertEqual(self.courrier.vise_par, self.dg)
        self.assertIn("équivalences", self.courrier.instruction_dg)

    def test_le_renvoi_au_service_exige_un_motif(self):
        self._traiter()

        ok, message = apply_transition(self.courrier, Statut.EN_TRAITEMENT, self.secretaire)
        self.assertFalse(ok)
        self.assertIn("motif", message)

        ok, message = apply_transition(
            self.courrier,
            Statut.EN_TRAITEMENT,
            self.secretaire,
            commentaire="Pièce jointe manquante.",
        )
        self.assertTrue(ok, message)
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, Statut.EN_TRAITEMENT)
        self.assertIsNone(self.courrier.date_transmission_secretariat)

    def test_le_dg_retourne_au_secretariat_avec_motif(self):
        self._traiter()
        self._transmettre_au_dg()

        ok, message = apply_transition(self.courrier, Statut.TRANSMIS_SECRETARIAT, self.dg)
        self.assertFalse(ok)
        self.assertIn("motif", message)

        ok, message = apply_transition(
            self.courrier,
            Statut.TRANSMIS_SECRETARIAT,
            self.dg,
            commentaire="Joindre l'avis du service juridique.",
        )
        self.assertTrue(ok, message)

    def test_le_circuit_complet_jusqu_au_classement(self):
        self._traiter()
        self._transmettre_au_dg()
        apply_transition(self.courrier, Statut.VISE_DG, self.dg)

        ok, message = apply_transition(self.courrier, Statut.RETOURNE, self.secretaire)
        self.assertTrue(ok, message)

        ok, message = apply_transition(self.courrier, Statut.CLASSE, self.courrier_agent)
        self.assertTrue(ok, message)

        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, Statut.CLASSE)
        self.assertTrue(self.courrier.is_closed)
        self.assertIsNotNone(self.courrier.date_classement)

    def test_la_transmission_notifie_le_secretariat_puis_le_dg(self):
        self._traiter()
        self.assertTrue(
            Notification.objects.filter(
                utilisateur=self.secretaire,
                type_notification=Notification.Type.COURRIER,
            ).exists()
        )

        self._transmettre_au_dg()
        self.assertTrue(
            Notification.objects.filter(
                utilisateur=self.dg,
                type_notification=Notification.Type.COURRIER,
            ).exists()
        )

    def test_le_visa_ne_notifie_qu_une_fois_chaque_personne(self):
        self._traiter()
        self._transmettre_au_dg()
        Notification.objects.all().delete()

        apply_transition(self.courrier, Statut.VISE_DG, self.dg)

        for user in (self.secretaire, self.courrier_agent):
            self.assertEqual(
                Notification.objects.filter(utilisateur=user).count(),
                1,
                msg=user.username,
            )

    def test_les_actions_proposees_dependent_du_role(self):
        self._traiter()

        cibles_courrier = {item["target"] for item in get_available_transitions(self.courrier, self.courrier_agent)}
        cibles_secretaire = {item["target"] for item in get_available_transitions(self.courrier, self.secretaire)}
        cibles_dg = {item["target"] for item in get_available_transitions(self.courrier, self.dg)}

        self.assertEqual(cibles_courrier, set())
        self.assertIn(Statut.TRANSMIS_DG, cibles_secretaire)
        self.assertEqual(cibles_dg, set())

    def test_un_agent_ordinaire_ne_voit_aucune_action(self):
        self.assertEqual(get_available_transitions(self.courrier, self.agent), [])


@override_settings(SECURE_SSL_REDIRECT=False)
class CourrierAccessTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Secrétariat Général", actif=True)
        self.autre_service = Service.objects.create(nom="Planification", actif=True)
        self.courrier_agent = make_user("agent_courrier", ROLE_COURRIER, self.service)
        self.secretaire = make_user("secretaire", ROLE_SECRETARIAT, self.service)
        self.dg = make_user("directeur", ROLE_DIRECTEUR_GENERAL, self.service)
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE, self.autre_service)
        self.agent = make_user("agent", ROLE_AGENT, self.autre_service)
        self.courrier = Courrier.objects.create(
            objet="Note de service",
            expediteur="Ministère",
            destinataire_service=self.service,
        )

    def test_le_registre_exige_une_authentification(self):
        response = self.client.get(reverse("courriers:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_les_acteurs_du_circuit_voient_le_registre(self):
        for user in (self.courrier_agent, self.secretaire, self.dg):
            self.client.force_login(user)
            response = self.client.get(reverse("courriers:list"))
            self.assertContains(response, self.courrier.reference, msg_prefix=user.username)

    def test_un_agent_d_un_autre_service_ne_voit_pas_le_courrier(self):
        for user in (self.agent_etude, self.agent):
            self.client.force_login(user)
            response = self.client.get(reverse("courriers:list"))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.courrier.reference, msg_prefix=user.username)

    def test_seuls_courrier_et_adjoint_enregistrent(self):
        self.client.force_login(self.courrier_agent)
        self.assertEqual(self.client.get(reverse("courriers:create")).status_code, 200)

        for user in (self.secretaire, self.dg, self.agent_etude, self.agent):
            self.client.force_login(user)
            response = self.client.get(reverse("courriers:create"))
            self.assertEqual(response.status_code, 403, msg=user.username)

    def test_la_fiche_n_est_plus_modifiable_apres_transmission(self):
        self.courrier.statut = Statut.TRANSMIS_DG
        self.courrier.save(update_fields=["statut"])
        self.client.force_login(self.courrier_agent)

        response = self.client.get(reverse("courriers:edit", args=[self.courrier.pk]))
        self.assertRedirects(response, reverse("courriers:detail", args=[self.courrier.pk]))

    def test_l_export_est_ouvert_aux_acteurs_du_circuit(self):
        for user in (self.courrier_agent, self.secretaire, self.dg):
            self.client.force_login(user)
            response = self.client.get(reverse("courriers:export"))
            self.assertEqual(response.status_code, 200, msg=user.username)
            self.assertIn("text/csv", response["Content-Type"])

    def test_l_export_est_refuse_a_un_agent_ordinaire(self):
        self.client.force_login(self.agent)
        response = self.client.get(reverse("courriers:export"))
        self.assertEqual(response.status_code, 403)

    def test_la_vue_de_transmission_respecte_les_roles(self):
        apply_transition(self.courrier, Statut.EN_TRAITEMENT, self.courrier_agent)
        apply_transition(self.courrier, Statut.TRANSMIS_SECRETARIAT, self.courrier_agent)

        self.client.force_login(self.courrier_agent)
        self.client.post(reverse("courriers:status", args=[self.courrier.pk, Statut.TRANSMIS_DG]))
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, Statut.TRANSMIS_SECRETARIAT)

        self.client.force_login(self.secretaire)
        self.client.post(reverse("courriers:status", args=[self.courrier.pk, Statut.TRANSMIS_DG]))
        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.statut, Statut.TRANSMIS_DG)


@override_settings(SECURE_SSL_REDIRECT=False)
class FicheAnalyseTests(TestCase):
    """Fiche d'analyse : imputations, instructions, impression, report."""

    def setUp(self):
        self.service_diplome = Service.objects.create(nom="Service Diplôme", actif=True)
        self.service_admin = Service.objects.create(nom="Service Administratif", actif=True)

        self.courrier_agent = make_user("agent_courrier", ROLE_COURRIER, self.service_admin)
        self.secretaire = make_user("secretaire", ROLE_SECRETARIAT, self.service_admin)
        self.dg = make_user("directeur", ROLE_DIRECTEUR_GENERAL, self.service_admin)
        self.agent_diplome = make_user("konan", ROLE_AGENT_ETUDE, self.service_diplome)
        self.agent_isole = make_user("isole", ROLE_AGENT)

        self.instruction = InstructionCourrier.objects.get(libelle="Pour Suite à Donner")

        self.courrier = Courrier.objects.create(
            objet="Demande d'équivalence",
            expediteur="Université Félix Houphouët-Boigny",
            numero_arrivee="A-2026-114",
            receptionne_par=self.courrier_agent,
            cree_par=self.courrier_agent,
            statut=Statut.TRANSMIS_DG,
        )

    def test_les_instructions_de_l_imprime_sont_amorcees(self):
        self.assertTrue(InstructionCourrier.objects.filter(libelle="Urgence").exists())
        self.assertTrue(InstructionCourrier.objects.filter(libelle="A classer").exists())
        self.assertEqual(InstructionCourrier.objects.count(), 12)

    def test_la_grille_suit_les_services_et_le_personnel_reels(self):
        """Aucune liste à maintenir : la grille vient de l'organisation."""
        grille = build_imputation_grid()
        services = {colonne["service"].nom for colonne in grille}
        self.assertIn("Service Diplôme", services)

        colonne_diplome = next(c for c in grille if c["service"] == self.service_diplome)
        self.assertIn(self.agent_diplome, colonne_diplome["agents"])

        # Un nouvel agent apparaît sans intervention.
        nouveau = make_user("nouvelle_recrue", ROLE_AGENT, self.service_diplome)
        colonne_diplome = next(
            c for c in build_imputation_grid() if c["service"] == self.service_diplome
        )
        self.assertIn(nouveau, colonne_diplome["agents"])

    def test_un_service_inactif_disparait_de_la_grille(self):
        self.service_diplome.actif = False
        self.service_diplome.save()

        services = {colonne["service"].nom for colonne in build_imputation_grid()}
        self.assertNotIn("Service Diplôme", services)

    def test_le_dg_renseigne_la_fiche(self):
        self.client.force_login(self.dg)
        response = self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {
                "agents_imputes": [self.agent_diplome.pk],
                "instructions": [self.instruction.pk],
                "autres_instructions": "Voir avec le service juridique.",
                "instruction_dg": "À traiter sous huit jours.",
            },
        )
        self.assertRedirects(response, reverse("courriers:detail", args=[self.courrier.pk]))

        self.courrier.refresh_from_db()
        self.assertEqual(list(self.courrier.agents_imputes.all()), [self.agent_diplome])
        self.assertEqual(self.courrier.instruction_dg, "À traiter sous huit jours.")
        self.assertEqual(self.courrier.fiche_saisie_par, self.dg)
        self.assertFalse(self.courrier.fiche_pour_le_compte_du_dg)

    def test_le_secretariat_reporte_la_fiche_pour_le_compte_du_dg(self):
        self.client.force_login(self.secretaire)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {"services_imputes": [self.service_diplome.pk], "instructions": [], "autres_instructions": "", "instruction_dg": ""},
        )

        self.courrier.refresh_from_db()
        self.assertEqual(self.courrier.fiche_saisie_par, self.secretaire)
        self.assertTrue(
            self.courrier.fiche_pour_le_compte_du_dg,
            "Une saisie par le secrétariat doit être marquée comme reportée.",
        )
        self.assertTrue(
            self.courrier.historiques.filter(action__icontains="reportée").exists()
        )

    def test_le_service_courrier_ne_renseigne_pas_la_fiche(self):
        self.client.force_login(self.courrier_agent)
        response = self.client.get(reverse("courriers:fiche", args=[self.courrier.pk]))
        self.assertEqual(response.status_code, 403)

    def test_la_fiche_est_bloquee_tant_que_le_courrier_n_est_pas_transmis_au_dg(self):
        self.courrier.statut = Statut.EN_TRAITEMENT
        self.courrier.save(update_fields=["statut"])

        self.client.force_login(self.secretaire)
        response = self.client.get(reverse("courriers:fiche", args=[self.courrier.pk]))

        self.assertRedirects(response, reverse("courriers:detail", args=[self.courrier.pk]))

    def test_le_visa_previent_les_imputes(self):
        self.courrier.agents_imputes.add(self.agent_diplome)
        self.courrier.services_imputes.add(self.service_diplome)
        self.courrier.instructions.add(self.instruction)
        Notification.objects.all().delete()

        ok, message = apply_transition(self.courrier, Statut.VISE_DG, self.dg)
        self.assertTrue(ok, message)

        # L'agent imputé nommément et les membres du service imputé sont prévenus.
        self.assertTrue(
            Notification.objects.filter(
                utilisateur=self.agent_diplome,
                titre__icontains="imputé",
            ).exists()
        )
        # Un agent hors imputation ne reçoit rien à ce titre.
        self.assertFalse(
            Notification.objects.filter(
                utilisateur=self.agent_isole,
                titre__icontains="imputé",
            ).exists()
        )

    def test_l_instruction_accompagne_la_notification_d_imputation(self):
        self.courrier.agents_imputes.add(self.agent_diplome)
        self.courrier.instructions.add(self.instruction)
        self.courrier.instruction_dg = "Réponse attendue avant vendredi."
        self.courrier.save(update_fields=["instruction_dg"])
        Notification.objects.all().delete()

        apply_transition(self.courrier, Statut.VISE_DG, self.dg)

        notification = Notification.objects.get(
            utilisateur=self.agent_diplome, titre__icontains="imputé"
        )
        self.assertIn("Pour Suite à Donner", notification.message)
        self.assertIn("vendredi", notification.message)

    def test_la_fiche_imprimable_reprend_les_donnees_du_service_courrier(self):
        self.client.force_login(self.secretaire)
        response = self.client.get(reverse("courriers:fiche_print", args=[self.courrier.pk]))

        self.assertEqual(response.status_code, 200)
        corps = response.content.decode()
        self.assertIn("FICHE D'ANALYSE DU COURRIER", corps)
        self.assertIn("RÉPUBLIQUE DE CÔTE D'IVOIRE", corps)
        self.assertIn(self.courrier.reference, corps)
        self.assertIn("A-2026-114", corps)
        self.assertIn("Université Félix Houphouët-Boigny", corps)
        # La grille imprime les services réels et leurs agents, vierge tant
        # que le Directeur Général n'a rien coché.
        self.assertIn("Service Diplôme", corps)
        self.assertIn("konan", corps)
        self.assertNotIn("est-cochee", corps)

    def test_la_fiche_imprimable_montre_les_cases_cochees(self):
        self.courrier.agents_imputes.add(self.agent_diplome)
        self.courrier.instructions.add(self.instruction)

        self.client.force_login(self.dg)
        response = self.client.get(reverse("courriers:fiche_print", args=[self.courrier.pk]))
        self.assertIn("est-cochee", response.content.decode())

    def test_la_fiche_imprimable_est_refusee_hors_du_circuit(self):
        self.client.force_login(self.agent_isole)
        response = self.client.get(reverse("courriers:fiche_print", args=[self.courrier.pk]))
        self.assertEqual(response.status_code, 403)

    # --- Ouverture de tâches depuis les imputations

    def test_aucune_tache_n_est_ouverte_sans_demande(self):
        self.client.force_login(self.dg)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {"agents_imputes": [self.agent_diplome.pk], "instructions": [], "autres_instructions": "", "instruction_dg": ""},
        )
        self.assertEqual(Task.objects.count(), 0)

    def test_une_tache_est_ouverte_par_imputation_a_la_demande(self):
        self.client.force_login(self.dg)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {
                "agents_imputes": [self.agent_diplome.pk],
                "services_imputes": [self.service_admin.pk],
                "instructions": [self.instruction.pk],
                "autres_instructions": "",
                "instruction_dg": "Réponse attendue avant vendredi.",
                "ouvrir_des_taches": "on",
            },
        )

        self.assertEqual(Task.objects.count(), 2)

        tache_agent = Task.objects.get(assigne_a=self.agent_diplome)
        self.assertIn(self.courrier.reference, tache_agent.titre)
        self.assertIn("vendredi", tache_agent.description)
        self.assertIn("Pour Suite à Donner", tache_agent.description)

        tache_service = Task.objects.get(assigne_a__isnull=True)
        self.assertEqual(tache_service.service_concerne, self.service_admin)

    def test_reenregistrer_la_fiche_ne_duplique_pas_les_taches(self):
        bruit = Task.objects.create(
            titre=f"Courrier {self.courrier.reference} : Ancienne preparation",
            description="Tache sans lien avec ce courrier.",
            cree_par=self.dg,
        )
        payload = {
            "agents_imputes": [self.agent_diplome.pk],
            "services_imputes": [self.service_admin.pk],
            "instructions": [self.instruction.pk],
            "autres_instructions": "",
            "instruction_dg": "Reponse attendue avant vendredi.",
            "ouvrir_des_taches": "on",
        }

        self.client.force_login(self.dg)
        url = reverse("courriers:fiche", args=[self.courrier.pk])
        self.client.post(url, payload)
        self.client.post(url, payload)

        self.courrier.refresh_from_db()
        self.assertEqual(Task.objects.count(), 3)
        self.assertEqual(self.courrier.taches.count(), 2)
        self.assertEqual(
            Task.objects.filter(courriers_origine=self.courrier, assigne_a=self.agent_diplome).count(),
            1,
        )
        self.assertEqual(
            Task.objects.filter(
                courriers_origine=self.courrier,
                assigne_a__isnull=True,
                service_concerne=self.service_admin,
            ).count(),
            1,
        )
        self.assertFalse(self.courrier.taches.filter(pk=bruit.pk).exists())

    def test_un_courrier_urgent_donne_une_tache_urgente(self):
        self.courrier.priorite = Courrier.Priorite.URGENTE
        self.courrier.save(update_fields=["priorite"])

        self.client.force_login(self.dg)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {
                "agents_imputes": [self.agent_diplome.pk],
                "instructions": [],
                "autres_instructions": "",
                "instruction_dg": "",
                "ouvrir_des_taches": "on",
            },
        )

        self.assertEqual(Task.objects.get().priorite, Task.Priority.URGENTE)

    def test_l_instruction_urgence_donne_une_tache_urgente(self):
        urgence = InstructionCourrier.objects.get(libelle="Urgence")
        self.client.force_login(self.dg)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {
                "agents_imputes": [self.agent_diplome.pk],
                "instructions": [urgence.pk],
                "autres_instructions": "",
                "instruction_dg": "",
                "ouvrir_des_taches": "on",
            },
        )

        self.assertEqual(Task.objects.get().priorite, Task.Priority.URGENTE)

    def test_l_ouverture_des_taches_est_tracee(self):
        self.client.force_login(self.dg)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {
                "agents_imputes": [self.agent_diplome.pk],
                "instructions": [],
                "autres_instructions": "",
                "instruction_dg": "",
                "ouvrir_des_taches": "on",
            },
        )

        self.assertTrue(
            self.courrier.historiques.filter(action__icontains="tâche").exists()
        )
        self.assertTrue(
            Task.objects.get().historiques.filter(action__icontains="imputation").exists()
        )

    def test_l_agent_impute_peut_ouvrir_le_courrier(self):
        """Sans cela, le lien de sa notification mène à une page refusée."""
        etranger = make_user("etranger", ROLE_AGENT)

        self.client.force_login(self.agent_diplome)
        self.assertEqual(
            self.client.get(reverse("courriers:detail", args=[self.courrier.pk])).status_code,
            404,
            "Avant imputation, l'agent d'un autre service ne voit pas le courrier.",
        )

        self.courrier.agents_imputes.add(self.agent_diplome)
        self.assertEqual(
            self.client.get(reverse("courriers:detail", args=[self.courrier.pk])).status_code,
            200,
        )

        # Un agent non imputé reste dehors.
        self.client.force_login(etranger)
        self.assertEqual(
            self.client.get(reverse("courriers:detail", args=[self.courrier.pk])).status_code,
            404,
        )

    def test_un_service_impute_ouvre_le_courrier_a_ses_agents(self):
        self.client.force_login(self.agent_diplome)
        self.courrier.services_imputes.add(self.service_diplome)

        self.assertEqual(
            self.client.get(reverse("courriers:detail", args=[self.courrier.pk])).status_code,
            200,
        )

    def test_l_avancement_de_la_tache_remonte_dans_l_historique_du_courrier(self):
        self.client.force_login(self.dg)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {
                "agents_imputes": [self.agent_diplome.pk],
                "instructions": [],
                "autres_instructions": "",
                "instruction_dg": "",
                "ouvrir_des_taches": "on",
            },
        )
        tache = Task.objects.get()
        self.assertIn(tache, self.courrier.taches.all())

        # L'agent imputé fait avancer sa tâche.
        self.client.force_login(self.agent_diplome)
        self.client.post(
            reverse("tasks:edit", args=[tache.pk]),
            {
                "titre": tache.titre,
                "description": tache.description,
                "service_concerne": self.service_diplome.pk,
                "assigne_a": self.agent_diplome.pk,
                "priorite": tache.priorite,
                "statut": Task.Status.VALIDE,
                "date_limite": "",
            },
        )

        tache.refresh_from_db()
        self.assertEqual(tache.statut, Task.Status.VALIDE)
        self.assertTrue(
            self.courrier.historiques.filter(action__icontains="Suite donnée").exists(),
            "L'avancement de la tâche doit remonter dans l'historique du courrier.",
        )
        self.assertTrue(
            self.courrier.historiques.filter(action__icontains="peuvent être classé").exists()
            or self.courrier.historiques.filter(action__icontains="peut être classé").exists()
        )
        self.courrier.refresh_from_db()
        self.assertTrue(self.courrier.suite_donnee)

    def test_le_courrier_reste_ouvert_tant_qu_une_tache_traine(self):
        self.client.force_login(self.dg)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {
                "agents_imputes": [self.agent_diplome.pk],
                "services_imputes": [self.service_admin.pk],
                "instructions": [],
                "autres_instructions": "",
                "instruction_dg": "",
                "ouvrir_des_taches": "on",
            },
        )
        self.assertEqual(self.courrier.taches.count(), 2)

        tache = self.courrier.taches.filter(assigne_a=self.agent_diplome).get()
        tache.statut = Task.Status.VALIDE
        tache.save()

        self.courrier.refresh_from_db()
        self.assertFalse(
            self.courrier.suite_donnee,
            "Une tâche encore ouverte empêche de considérer la suite comme donnée.",
        )

    def test_le_secretariat_et_le_dg_classent_le_courrier(self):
        self.courrier.statut = Statut.RETOURNE
        self.courrier.save(update_fields=["statut"])

        # Le service courrier classe toujours.
        ok, _ = apply_transition(self.courrier, Statut.CLASSE, self.courrier_agent)
        self.assertTrue(ok)

        # Le secrétariat aussi.
        self.courrier.statut = Statut.RETOURNE
        self.courrier.save(update_fields=["statut"])
        ok, _ = apply_transition(self.courrier, Statut.CLASSE, self.secretaire)
        self.assertTrue(ok)

        # Et le Directeur Général.
        self.courrier.statut = Statut.RETOURNE
        self.courrier.save(update_fields=["statut"])
        ok, _ = apply_transition(self.courrier, Statut.CLASSE, self.dg)
        self.assertTrue(ok)

    def test_un_agent_ordinaire_ne_classe_pas(self):
        self.courrier.statut = Statut.RETOURNE
        self.courrier.save(update_fields=["statut"])

        ok, message = apply_transition(self.courrier, Statut.CLASSE, self.agent_isole)
        self.assertFalse(ok)
        self.assertIn("classement", message.lower())

    def test_l_agent_impute_voit_et_peut_traiter_sa_tache(self):
        self.client.force_login(self.dg)
        self.client.post(
            reverse("courriers:fiche", args=[self.courrier.pk]),
            {
                "agents_imputes": [self.agent_diplome.pk],
                "instructions": [],
                "autres_instructions": "",
                "instruction_dg": "",
                "ouvrir_des_taches": "on",
            },
        )

        tache = Task.objects.get()
        self.client.force_login(self.agent_diplome)
        response = self.client.get(reverse("tasks:edit", args=[tache.pk]))
        self.assertEqual(response.status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False)
class NatureDocumentTests(TestCase):
    """La nature du document, distincte du sens.

    Le sens dit s'il entre ou s'il sort et fonde les registres arrivee et
    depart ; la nature dit de quel document il s'agit. Melanger les deux dans
    un seul champ aurait fait perdre l'un des deux renseignements.
    """

    def setUp(self):
        self.agent_courrier = make_user("courrier", ROLE_COURRIER)
        self.client.force_login(self.agent_courrier)

    def test_les_courriers_existants_sont_des_courriers_simples(self):
        courrier = Courrier.objects.create(
            objet="Demande de stage",
            expediteur="Université de Bouaké",
            cree_par=self.agent_courrier,
        )
        self.assertEqual(courrier.nature, Courrier.Nature.COURRIER)

    def test_les_quatre_natures_sont_disponibles(self):
        self.assertEqual(
            [valeur for valeur, _ in Courrier.Nature.choices],
            ["courrier", "autorisation", "note", "ordre_mission"],
        )

    def test_nature_et_sens_sont_independants(self):
        """Un ordre de mission peut entrer comme sortir."""
        entrant = Courrier.objects.create(
            objet="Ordre de mission reçu",
            expediteur="Cabinet du Ministre",
            sens=Courrier.Sens.ENTRANT,
            nature=Courrier.Nature.ORDRE_MISSION,
            cree_par=self.agent_courrier,
        )
        sortant = Courrier.objects.create(
            objet="Ordre de mission émis",
            expediteur="DGES",
            sens=Courrier.Sens.SORTANT,
            nature=Courrier.Nature.ORDRE_MISSION,
            cree_par=self.agent_courrier,
        )
        self.assertEqual(
            Courrier.objects.filter(nature=Courrier.Nature.ORDRE_MISSION).count(), 2
        )
        self.assertEqual(Courrier.objects.filter(sens=Courrier.Sens.ENTRANT).count(), 1)
        self.assertNotEqual(entrant.sens, sortant.sens)

    def test_le_registre_se_filtre_par_nature(self):
        Courrier.objects.create(
            objet="Autorisation d'absence",
            expediteur="Service Administratif",
            nature=Courrier.Nature.AUTORISATION,
            cree_par=self.agent_courrier,
        )
        Courrier.objects.create(
            objet="Courrier ordinaire",
            expediteur="Université de Korhogo",
            cree_par=self.agent_courrier,
        )

        reponse = self.client.get(reverse("courriers:list"), {"nature": "autorisation"})
        self.assertEqual(reponse.status_code, 200)
        # L'apostrophe est échappée dans la page rendue.
        self.assertContains(reponse, "Autorisation d&#x27;absence")
        self.assertNotContains(reponse, "Courrier ordinaire")

    def test_la_nature_figure_dans_l_export(self):
        Courrier.objects.create(
            objet="Note de service",
            expediteur="DGES",
            nature=Courrier.Nature.NOTE,
            cree_par=self.agent_courrier,
        )
        reponse = self.client.get(reverse("courriers:export"))
        contenu = reponse.content.decode("utf-8")
        self.assertIn("Nature", contenu)
        self.assertIn("Note", contenu)


class RepertoireCorrespondantsTests(TestCase):
    """Le répertoire se remplit à l'usage, sans doublon.

    C'est le point qui décide de sa valeur : si « Universite FHB » et
    « Université F.H.B. » créent deux fiches, aucun regroupement par organisme
    n'est possible et le répertoire ne vaut pas mieux qu'une zone de texte.
    """

    def test_un_nom_inedit_cree_sa_fiche(self):
        correspondant = CorrespondantExterne.obtenir_ou_creer("Université de Korhogo")
        self.assertEqual(correspondant.nom, "Université de Korhogo")
        self.assertEqual(CorrespondantExterne.objects.count(), 1)

    def test_un_nom_deja_connu_ne_cree_pas_de_doublon(self):
        premier = CorrespondantExterne.obtenir_ou_creer("Université de Korhogo")
        second = CorrespondantExterne.obtenir_ou_creer("Université de Korhogo")
        self.assertEqual(premier.pk, second.pk)
        self.assertEqual(CorrespondantExterne.objects.count(), 1)

    def test_les_accents_et_la_casse_sont_ignores(self):
        premier = CorrespondantExterne.obtenir_ou_creer("Université Félix Houphouët-Boigny")
        second = CorrespondantExterne.obtenir_ou_creer("universite felix houphouet-boigny")
        self.assertEqual(premier.pk, second.pk)
        # La graphie d'origine est conservée pour l'affichage.
        self.assertEqual(second.nom, "Université Félix Houphouët-Boigny")

    def test_les_espaces_superflus_sont_absorbes(self):
        premier = CorrespondantExterne.obtenir_ou_creer("  Ministère   de la Santé ")
        second = CorrespondantExterne.obtenir_ou_creer("Ministère de la Santé")
        self.assertEqual(premier.pk, second.pk)
        self.assertEqual(premier.nom, "Ministère de la Santé")

    def test_un_nom_vide_ne_cree_rien(self):
        self.assertIsNone(CorrespondantExterne.obtenir_ou_creer(""))
        self.assertIsNone(CorrespondantExterne.obtenir_ou_creer("   "))
        self.assertIsNone(CorrespondantExterne.obtenir_ou_creer(None))
        self.assertEqual(CorrespondantExterne.objects.count(), 0)

    def test_normalisation(self):
        self.assertEqual(normaliser_nom("Université  FÉLIX "), "universite felix")


@override_settings(SECURE_SSL_REDIRECT=False)
class CourrierSortantTests(TestCase):
    """Le sortant se lit en miroir de l'entrant.

    entrant : expéditeur externe  -> service destinataire interne
    sortant : service émetteur    -> destinataire externe
    """

    def setUp(self):
        self.service = Service.objects.create(nom="Service Courrier", actif=True)
        self.agent_courrier = make_user("courrier", ROLE_COURRIER, self.service)
        self.client.force_login(self.agent_courrier)

    def _donnees_sortant(self, **extra):
        donnees = {
            "reference": "",
            "numero_arrivee": "",
            "sens": Courrier.Sens.SORTANT,
            "nature": Courrier.Nature.ORDRE_MISSION,
            "objet": "Mission de contrôle pédagogique",
            "expediteur": "",
            "destinataire_service": "",
            "service_emetteur": self.service.pk,
            "destinataire_externe_nom": "Université de Daloa",
            "date_reception": "2026-08-04",
            "date_courrier": "",
            "priorite": Courrier.Priorite.NORMALE,
            "receptionne_par": "",
            "observation": "",
        }
        donnees.update(extra)
        return donnees

    def test_enregistrer_un_sortant_cree_le_correspondant(self):
        reponse = self.client.post(reverse("courriers:create"), self._donnees_sortant())
        self.assertEqual(reponse.status_code, 302)

        courrier = Courrier.objects.get()
        self.assertEqual(courrier.service_emetteur, self.service)
        self.assertEqual(courrier.destinataire_externe.nom, "Université de Daloa")
        self.assertEqual(courrier.provenance, "Service Courrier")
        self.assertEqual(courrier.destinataire, "Université de Daloa")

    def test_le_meme_destinataire_ne_cree_pas_deux_fiches(self):
        self.client.post(reverse("courriers:create"), self._donnees_sortant())
        self.client.post(
            reverse("courriers:create"),
            self._donnees_sortant(
                objet="Second envoi",
                destinataire_externe_nom="universite de daloa",
            ),
        )
        self.assertEqual(Courrier.objects.count(), 2)
        self.assertEqual(CorrespondantExterne.objects.count(), 1)

    def test_un_sortant_sans_destinataire_est_refuse(self):
        reponse = self.client.post(
            reverse("courriers:create"),
            self._donnees_sortant(destinataire_externe_nom=""),
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertFormError(
            reponse.context["form"],
            "destinataire_externe_nom",
            "Indiquez l'organisme destinataire de ce courrier.",
        )
        self.assertEqual(Courrier.objects.count(), 0)

    def test_un_sortant_sans_service_emetteur_est_refuse(self):
        reponse = self.client.post(
            reverse("courriers:create"),
            self._donnees_sortant(service_emetteur=""),
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertFormError(
            reponse.context["form"],
            "service_emetteur",
            "Indiquez le service de la DGES à l'origine de ce courrier.",
        )

    def test_un_entrant_sans_expediteur_est_refuse(self):
        reponse = self.client.post(
            reverse("courriers:create"),
            self._donnees_sortant(sens=Courrier.Sens.ENTRANT, expediteur=""),
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertFormError(
            reponse.context["form"],
            "expediteur",
            "Indiquez l'expéditeur de ce courrier.",
        )

    def test_les_rubriques_de_l_autre_sens_sont_videes(self):
        """Un expéditeur laissé en place ferait apparaître dans le registre
        quelqu'un qui n'a jamais rien envoyé.
        """
        self.client.post(
            reverse("courriers:create"),
            self._donnees_sortant(expediteur="Université fantôme", numero_arrivee="A-1"),
        )
        courrier = Courrier.objects.get()
        self.assertEqual(courrier.expediteur, "")
        self.assertEqual(courrier.numero_arrivee, "")
        self.assertIsNone(courrier.destinataire_service)

    def test_le_registre_se_cherche_par_destinataire(self):
        self.client.post(reverse("courriers:create"), self._donnees_sortant())
        reponse = self.client.get(reverse("courriers:list"), {"q": "Daloa"})
        self.assertContains(reponse, "Université de Daloa")

    def test_un_sortant_ancien_garde_sa_provenance(self):
        """Les courriers enregistrés avant la séparation des champs."""
        ancien = Courrier.objects.create(
            objet="Ancien envoi",
            sens=Courrier.Sens.SORTANT,
            expediteur="DIRECTION GÉNÉRALE",
            cree_par=self.agent_courrier,
        )
        self.assertEqual(ancien.provenance, "DIRECTION GÉNÉRALE")


@override_settings(SECURE_SSL_REDIRECT=False)
class DechargeTests(TestCase):
    """Décharge : elle accompagne un courrier sortant et revient signée.

    Ce que ces tests protègent avant tout : qu'aucune rubrique du destinataire
    ne soit pré-remplie. Elles attesteraient de faits qui ne se sont pas encore
    produits, sur un document qui fait preuve.
    """

    def setUp(self):
        self.service = Service.objects.create(nom="Cabinet du Directeur", actif=True)
        self.agent_courrier = make_user("courrier", ROLE_COURRIER, self.service)
        self.agent_isole = make_user("isole", ROLE_AGENT)
        self.destinataire = CorrespondantExterne.obtenir_ou_creer(
            "Université Félix Houphouët-Boigny"
        )
        self.sortant = Courrier.objects.create(
            objet="Transmission des résultats du CEES",
            sens=Courrier.Sens.SORTANT,
            nature=Courrier.Nature.ORDRE_MISSION,
            service_emetteur=self.service,
            destinataire_externe=self.destinataire,
            receptionne_par=self.agent_courrier,
            cree_par=self.agent_courrier,
        )
        self.entrant = Courrier.objects.create(
            objet="Demande de reconnaissance",
            sens=Courrier.Sens.ENTRANT,
            expediteur="ISP Gombe",
            receptionne_par=self.agent_courrier,
            cree_par=self.agent_courrier,
        )

    def test_le_numero_de_decharge_derive_de_la_reference(self):
        """Deux impressions du même courrier portent le même numéro."""
        self.sortant.reference = "COUR-2026-004"
        self.assertEqual(self.sortant.numero_decharge, "DECH-2026-004")

    def test_numero_de_decharge_sans_prefixe_attendu(self):
        self.sortant.reference = "X99"
        self.assertEqual(self.sortant.numero_decharge, "DECH-X99")

    def test_la_decharge_porte_ce_que_la_dges_connait(self):
        self.client.force_login(self.agent_courrier)
        reponse = self.client.get(reverse("courriers:decharge", args=[self.sortant.pk]))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, self.sortant.numero_decharge)
        self.assertContains(reponse, self.sortant.reference)
        self.assertContains(reponse, "Transmission des résultats du CEES")
        self.assertContains(reponse, "Cabinet du Directeur")
        self.assertContains(reponse, "Université Félix Houphouët-Boigny")

    def test_la_decharge_ne_prejuge_pas_du_receptionnaire(self):
        """Le réceptionnaire est extérieur à la DGES : il est inconnu ici."""
        self.agent_courrier.first_name = "Ama"
        self.agent_courrier.last_name = "Kouadio"
        self.agent_courrier.save()
        self.client.force_login(self.agent_courrier)
        reponse = self.client.get(reverse("courriers:decharge", args=[self.sortant.pk]))
        self.assertNotContains(reponse, "Ama Kouadio")

    def test_la_decharge_ne_prejuge_pas_de_la_date_de_reception(self):
        """La date de réception est celle de la remise, encore à venir."""
        self.client.force_login(self.agent_courrier)
        reponse = self.client.get(reverse("courriers:decharge", args=[self.sortant.pk]))
        self.assertNotContains(reponse, self.sortant.date_reception.strftime("%d/%m/%Y"))

    def test_un_courrier_entrant_n_a_pas_de_decharge(self):
        """La DGES le reçoit, elle ne le remet à personne."""
        self.client.force_login(self.agent_courrier)
        reponse = self.client.get(reverse("courriers:decharge", args=[self.entrant.pk]))
        self.assertEqual(reponse.status_code, 404)

    def test_le_bouton_n_apparait_que_sur_un_sortant(self):
        self.client.force_login(self.agent_courrier)
        page_sortant = self.client.get(reverse("courriers:detail", args=[self.sortant.pk]))
        page_entrant = self.client.get(reverse("courriers:detail", args=[self.entrant.pk]))
        self.assertContains(page_sortant, "Imprimer la décharge")
        self.assertNotContains(page_entrant, "Imprimer la décharge")

    def test_un_agent_sans_acces_n_obtient_pas_la_decharge(self):
        self.client.force_login(self.agent_isole)
        reponse = self.client.get(reverse("courriers:decharge", args=[self.sortant.pk]))
        self.assertIn(reponse.status_code, (403, 404))
