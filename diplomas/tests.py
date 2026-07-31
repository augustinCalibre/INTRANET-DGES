from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
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
from core.models import Notification

from .models import Diplome, LotDiplomes, generate_lot_reference
from .services import create_diplomas_from_rows, parse_diploma_file
from .workflow import apply_transition, get_available_transitions

Statut = LotDiplomes.Status


def make_user(username, role, service=None):
    user = User.objects.create_user(username=username, password="StrongPass123!")
    profile = user.profil
    profile.role = role
    profile.service = service
    profile.actif = True
    profile.save()
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class LotReferenceTests(TestCase):
    def test_reference_is_generated_incrementally(self):
        premier = LotDiplomes.objects.create(etablissement="Université de Kinshasa", nombre_annonce=10)
        second = LotDiplomes.objects.create(etablissement="ISP Gombe", nombre_annonce=5)

        year = premier.date_arrivee.year
        self.assertEqual(premier.reference, f"LOT-DIP-{year}-001")
        self.assertEqual(second.reference, f"LOT-DIP-{year}-002")

    def test_explicit_reference_is_preserved(self):
        lot = LotDiplomes.objects.create(
            reference="LOT-DIP-2026-042",
            etablissement="Université de Lubumbashi",
            nombre_annonce=3,
        )
        self.assertEqual(lot.reference, "LOT-DIP-2026-042")

    def test_generate_reference_ignores_malformed_existing_values(self):
        year = generate_lot_reference().split("-")[2]
        LotDiplomes.objects.create(reference=f"LOT-DIP-{year}-ABC", etablissement="Test", nombre_annonce=1)
        self.assertTrue(generate_lot_reference().startswith(f"LOT-DIP-{year}-"))


@override_settings(SECURE_SSL_REDIRECT=False)
class DiplomaAccessTests(TestCase):
    """Qui atteint le registre, qui peut en modifier le contenu."""

    def setUp(self):
        self.service = Service.objects.create(nom="Études et vérification", actif=True)
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE, self.service)
        self.secretaire = make_user("secretaire", ROLE_SECRETARIAT, self.service)
        self.dg = make_user("directeur", ROLE_DIRECTEUR_GENERAL, self.service)
        self.courrier = make_user("courrier", ROLE_COURRIER, self.service)
        self.agent = make_user("agent", ROLE_AGENT, self.service)
        self.lot = LotDiplomes.objects.create(etablissement="Université de Kinshasa", nombre_annonce=2)

    def test_registry_requires_authentication(self):
        response = self.client.get(reverse("diplomas:lot_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_agent_etude_secretariat_and_dg_see_the_registry(self):
        for user in (self.agent_etude, self.secretaire, self.dg):
            self.client.force_login(user)
            response = self.client.get(reverse("diplomas:lot_list"))
            self.assertContains(response, self.lot.reference, msg_prefix=user.username)

    def test_courrier_and_agent_do_not_see_the_lots(self):
        for user in (self.courrier, self.agent):
            self.client.force_login(user)
            response = self.client.get(reverse("diplomas:lot_list"))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.lot.reference, msg_prefix=user.username)

    def test_only_agent_etude_creates_a_lot(self):
        self.client.force_login(self.agent_etude)
        self.assertEqual(self.client.get(reverse("diplomas:lot_create")).status_code, 200)

        for user in (self.secretaire, self.dg, self.courrier, self.agent):
            self.client.force_login(user)
            response = self.client.get(reverse("diplomas:lot_create"))
            self.assertEqual(response.status_code, 403, msg=user.username)

    def test_secretariat_cannot_edit_the_content_of_a_lot(self):
        self.client.force_login(self.secretaire)
        response = self.client.get(reverse("diplomas:diploma_create", args=[self.lot.pk]))
        self.assertEqual(response.status_code, 403)

    def test_secretariat_and_dg_can_export(self):
        for user in (self.secretaire, self.dg):
            self.client.force_login(user)
            response = self.client.get(reverse("diplomas:lot_export", args=[self.lot.pk]))
            self.assertEqual(response.status_code, 200, msg=user.username)


@override_settings(SECURE_SSL_REDIRECT=False)
class WorkflowTests(TestCase):
    """Le circuit : agent d'étude vérifie, secrétariat transmet, DG signe."""

    def setUp(self):
        self.service = Service.objects.create(nom="Études et vérification", actif=True)
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE, self.service)
        self.secretaire = make_user("secretaire", ROLE_SECRETARIAT, self.service)
        self.dg = make_user("directeur", ROLE_DIRECTEUR_GENERAL, self.service)
        self.lot = LotDiplomes.objects.create(
            etablissement="Université de Kinshasa",
            nombre_annonce=2,
            agent_receptionnaire=self.agent_etude,
            cree_par=self.agent_etude,
        )
        Diplome.objects.create(lot=self.lot, nom_beneficiaire="Awa Mbala", numero_diplome="D-001")
        Diplome.objects.create(lot=self.lot, nom_beneficiaire="Jean Kalala", numero_diplome="D-002")

    def _verifier(self):
        """Étapes de l'agent d'étude, jusqu'au lot conforme."""
        for etape in (Statut.EN_VERIFICATION,):
            ok, message = apply_transition(self.lot, etape, self.agent_etude)
            self.assertTrue(ok, message)
        self.lot.diplomes.update(statut=Diplome.Status.CONFORME)
        ok, message = apply_transition(self.lot, Statut.CONFORME, self.agent_etude)
        self.assertTrue(ok, message)

    def _transmettre(self):
        ok, message = apply_transition(self.lot, Statut.TRANSMIS_DG, self.secretaire)
        self.assertTrue(ok, message)

    def test_agent_etude_verifie_et_declare_conforme(self):
        self._verifier()
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.CONFORME)

    def test_secretariat_ne_demarre_pas_la_verification(self):
        ok, message = apply_transition(self.lot, Statut.EN_VERIFICATION, self.secretaire)
        self.assertFalse(ok)
        self.assertIn("agent d'étude", message)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.RECU)

    def test_agent_etude_ne_transmet_pas_au_dg(self):
        self._verifier()
        ok, message = apply_transition(self.lot, Statut.TRANSMIS_DG, self.agent_etude)
        self.assertFalse(ok)
        self.assertIn("Secrétariat", message)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.CONFORME)

    def test_le_secretariat_transmet(self):
        self._verifier()
        self._transmettre()
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.TRANSMIS_DG)
        self.assertEqual(self.lot.transmis_par, self.secretaire)
        self.assertIsNotNone(self.lot.date_transmission_dg)

    def test_seul_le_dg_signe(self):
        self._verifier()
        self._transmettre()

        for user in (self.secretaire, self.agent_etude):
            ok, message = apply_transition(self.lot, Statut.SIGNE, user)
            self.assertFalse(ok, msg=user.username)
            self.assertIn("Directeur Général", message)

        ok, message = apply_transition(self.lot, Statut.SIGNE, self.dg)
        self.assertTrue(ok, message)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.SIGNE)
        self.assertEqual(self.lot.signe_par, self.dg)

    def test_un_lot_non_transmis_ne_peut_pas_etre_signe(self):
        ok, message = apply_transition(self.lot, Statut.SIGNE, self.dg)
        self.assertFalse(ok)
        self.assertIn("circuit", message)

    def test_anomalie_bloque_la_conformite(self):
        apply_transition(self.lot, Statut.EN_VERIFICATION, self.agent_etude)
        diplome = self.lot.diplomes.first()
        diplome.statut = Diplome.Status.NON_CONFORME
        diplome.anomalie = Diplome.Anomalie.ERREUR_NOM
        diplome.save()

        ok, message = apply_transition(self.lot, Statut.CONFORME, self.agent_etude)
        self.assertFalse(ok)
        self.assertIn("non conformes", message)

    def test_lot_vide_ne_peut_pas_etre_declare_conforme(self):
        self.lot.diplomes.all().delete()
        apply_transition(self.lot, Statut.EN_VERIFICATION, self.agent_etude)
        ok, message = apply_transition(self.lot, Statut.CONFORME, self.agent_etude)
        self.assertFalse(ok)
        self.assertIn("Aucun diplôme", message)

    def test_retour_pour_correction_exige_un_motif_et_appartient_au_dg(self):
        self._verifier()
        self._transmettre()

        ok, message = apply_transition(self.lot, Statut.EN_VERIFICATION, self.secretaire)
        self.assertFalse(ok)
        self.assertIn("Directeur Général", message)

        ok, message = apply_transition(self.lot, Statut.EN_VERIFICATION, self.dg)
        self.assertFalse(ok)
        self.assertIn("motif", message)

        ok, message = apply_transition(
            self.lot,
            Statut.EN_VERIFICATION,
            self.dg,
            commentaire="Deux noms mal orthographiés.",
        )
        self.assertTrue(ok, message)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.EN_VERIFICATION)
        self.assertIsNone(self.lot.date_transmission_dg)

    def test_la_transmission_notifie_le_dg(self):
        self._verifier()
        self._transmettre()
        notification = Notification.objects.filter(
            utilisateur=self.dg,
            type_notification=Notification.Type.DIPLOME,
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn(self.lot.reference, notification.titre)

    def test_la_signature_se_repercute_sur_les_diplomes(self):
        self._verifier()
        self._transmettre()
        self.assertEqual(self.lot.diplomes.filter(statut=Diplome.Status.TRANSMIS_DG).count(), 2)

        apply_transition(self.lot, Statut.SIGNE, self.dg)
        self.assertEqual(self.lot.diplomes.filter(statut=Diplome.Status.SIGNE).count(), 2)

    def test_le_retour_au_service_appartient_au_secretariat(self):
        self._verifier()
        self._transmettre()
        apply_transition(self.lot, Statut.SIGNE, self.dg)

        ok, message = apply_transition(self.lot, Statut.RETOURNE, self.agent_etude)
        self.assertFalse(ok)
        self.assertIn("Secrétariat", message)

        ok, message = apply_transition(self.lot, Statut.RETOURNE, self.secretaire)
        self.assertTrue(ok, message)

    def test_les_actions_proposees_dependent_du_role(self):
        self._verifier()

        cibles_agent = {item["target"] for item in get_available_transitions(self.lot, self.agent_etude)}
        cibles_secretaire = {item["target"] for item in get_available_transitions(self.lot, self.secretaire)}
        cibles_dg = {item["target"] for item in get_available_transitions(self.lot, self.dg)}

        self.assertIn(Statut.TRANSMIS_DG, cibles_secretaire)
        self.assertNotIn(Statut.TRANSMIS_DG, cibles_agent)
        self.assertNotIn(Statut.TRANSMIS_DG, cibles_dg)

    def test_la_vue_refuse_un_statut_hors_circuit(self):
        self.client.force_login(self.agent_etude)
        response = self.client.post(
            reverse("diplomas:lot_status", args=[self.lot.pk, Statut.ARCHIVE]),
        )
        self.assertEqual(response.status_code, 302)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.RECU)

    def test_la_vue_de_transmission_est_refusee_a_l_agent_etude(self):
        self._verifier()
        self.client.force_login(self.agent_etude)
        self.client.post(reverse("diplomas:lot_status", args=[self.lot.pk, Statut.TRANSMIS_DG]))
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.CONFORME)

    def test_la_vue_de_transmission_fonctionne_pour_le_secretariat(self):
        self._verifier()
        self.client.force_login(self.secretaire)
        self.client.post(reverse("diplomas:lot_status", args=[self.lot.pk, Statut.TRANSMIS_DG]))
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.TRANSMIS_DG)


@override_settings(SECURE_SSL_REDIRECT=False)
class DiplomaContentTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Études et vérification", actif=True)
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE, self.service)
        self.lot = LotDiplomes.objects.create(etablissement="Université de Kinshasa", nombre_annonce=3)

    def test_diploma_edition_is_closed_after_transmission(self):
        self.lot.statut = Statut.TRANSMIS_DG
        self.lot.save(update_fields=["statut"])
        self.client.force_login(self.agent_etude)

        response = self.client.get(reverse("diplomas:diploma_create", args=[self.lot.pk]))
        self.assertRedirects(response, reverse("diplomas:lot_detail", args=[self.lot.pk]))

    def test_counters_reflect_the_registered_diplomas(self):
        Diplome.objects.create(lot=self.lot, nom_beneficiaire="Awa Mbala", numero_diplome="D-001")
        Diplome.objects.create(
            lot=self.lot,
            nom_beneficiaire="Jean Kalala",
            numero_diplome="D-002",
            statut=Diplome.Status.NON_CONFORME,
            anomalie=Diplome.Anomalie.MANQUANT,
        )

        self.assertEqual(self.lot.nombre_enregistre, 2)
        self.assertEqual(self.lot.nombre_anomalies, 1)
        self.assertEqual(self.lot.ecart, -1)
        self.assertTrue(self.lot.has_ecart)
        self.assertTrue(self.lot.has_anomalies)

    def test_etablissement_falls_back_on_the_lot(self):
        diplome = Diplome.objects.create(lot=self.lot, nom_beneficiaire="Awa", numero_diplome="D-010")
        self.assertEqual(diplome.etablissement_effectif, "Université de Kinshasa")


@override_settings(SECURE_SSL_REDIRECT=False)
class DiplomaImportTests(TestCase):
    def setUp(self):
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE)
        self.lot = LotDiplomes.objects.create(etablissement="Université de Kinshasa", nombre_annonce=3)

    def _csv_file(self, content, name="lot.csv"):
        return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")

    def test_csv_with_semicolons_and_accents_is_parsed(self):
        uploaded = self._csv_file(
            "Nom;Numéro;Filière;Année\n"
            "Awa Mbala;D-001;Droit;2024-2025\n"
            "Jean Kalala;D-002;Économie;2024-2025\n"
        )
        rows, resume = parse_diploma_file(uploaded, self.lot)

        self.assertEqual(resume["total"], 2)
        self.assertEqual(resume["valides"], 2)
        self.assertEqual(rows[0]["data"]["nom_beneficiaire"], "Awa Mbala")
        self.assertEqual(rows[0]["data"]["filiere"], "Droit")

    def test_missing_required_columns_is_reported(self):
        uploaded = self._csv_file("Filière;Année\nDroit;2024-2025\n")
        with self.assertRaises(ValueError) as error:
            parse_diploma_file(uploaded, self.lot)
        self.assertIn("Colonnes obligatoires", str(error.exception))

    def test_rows_without_a_number_are_rejected(self):
        uploaded = self._csv_file("Nom;Numéro\nAwa Mbala;\nJean Kalala;D-002\n")
        rows, resume = parse_diploma_file(uploaded, self.lot)

        self.assertEqual(resume["valides"], 1)
        self.assertEqual(resume["rejetes"], 1)
        self.assertFalse(rows[0]["is_valid"])

    def test_duplicates_inside_the_file_are_rejected(self):
        uploaded = self._csv_file("Nom;Numéro\nAwa Mbala;D-001\nAwa Mbala;D-001\n")
        rows, resume = parse_diploma_file(uploaded, self.lot)

        self.assertEqual(resume["valides"], 1)
        self.assertIn("doublon", rows[1]["errors"][0])

    def test_numbers_already_present_in_the_lot_are_rejected(self):
        Diplome.objects.create(lot=self.lot, nom_beneficiaire="Awa Mbala", numero_diplome="D-001")
        uploaded = self._csv_file("Nom;Numéro\nAwa Mbala;D-001\n")
        rows, _ = parse_diploma_file(uploaded, self.lot)

        self.assertFalse(rows[0]["is_valid"])
        self.assertIn("existe deja", rows[0]["errors"][0])

    def test_unsupported_extension_is_refused(self):
        uploaded = SimpleUploadedFile("lot.pdf", b"%PDF-1.4", content_type="application/pdf")
        with self.assertRaises(ValueError):
            parse_diploma_file(uploaded, self.lot)

    def test_creation_from_preview_rows(self):
        rows = [
            {"data": {"nom_beneficiaire": "Awa Mbala", "numero_diplome": "D-001", "filiere": "Droit"}},
            {"data": {"nom_beneficiaire": "Jean Kalala", "numero_diplome": "D-002"}},
            {"data": {"nom_beneficiaire": "", "numero_diplome": "D-003"}},
        ]
        created, ignored = create_diplomas_from_rows(self.lot, rows, self.agent_etude)

        self.assertEqual(created, 2)
        self.assertEqual(ignored, 1)
        self.assertEqual(self.lot.diplomes.count(), 2)

    def test_import_flow_shows_a_preview_before_saving(self):
        self.client.force_login(self.agent_etude)
        response = self.client.post(
            reverse("diplomas:diploma_import", args=[self.lot.pk]),
            {"fichier": self._csv_file("Nom;Numéro\nAwa Mbala;D-001\n")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vérifier l'aperçu")
        self.assertEqual(self.lot.diplomes.count(), 0, "L'aperçu ne doit rien enregistrer.")

    def test_xlsx_import_when_openpyxl_is_available(self):
        try:
            from openpyxl import Workbook
        except ImportError:
            self.skipTest("openpyxl n'est pas installé dans cet environnement.")

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["Nom", "Numero", "Filiere"])
        worksheet.append(["Awa Mbala", "D-001", "Droit"])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        uploaded = SimpleUploadedFile(
            "lot.xlsx",
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        rows, resume = parse_diploma_file(uploaded, self.lot)

        self.assertEqual(resume["valides"], 1)
        self.assertEqual(rows[0]["data"]["numero_diplome"], "D-001")


@override_settings(SECURE_SSL_REDIRECT=False)
class DiplomaSearchAndExportTests(TestCase):
    def setUp(self):
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE)
        self.lot = LotDiplomes.objects.create(etablissement="Université de Kinshasa", nombre_annonce=1)
        self.diplome = Diplome.objects.create(
            lot=self.lot,
            nom_beneficiaire="Awa Mbala",
            numero_diplome="D-2026-0148",
            filiere="Droit",
        )

    def test_search_finds_a_diploma_by_number(self):
        self.client.force_login(self.agent_etude)
        response = self.client.get(reverse("diplomas:search"), {"q": "D-2026-0148"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Awa Mbala")

    def test_search_without_criteria_shows_no_result_table(self):
        self.client.force_login(self.agent_etude)
        response = self.client.get(reverse("diplomas:search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lancez une recherche")

    def test_registry_export_returns_a_csv(self):
        self.client.force_login(self.agent_etude)
        response = self.client.get(reverse("diplomas:registry_export"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(self.lot.reference, response.content.decode("utf-8"))

    def test_lot_export_lists_the_diplomas(self):
        self.client.force_login(self.agent_etude)
        response = self.client.get(reverse("diplomas:lot_export", args=[self.lot.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("D-2026-0148", response.content.decode("utf-8"))
