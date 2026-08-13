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

from .forms import LotDiplomesForm
from .models import Diplome, LotDiplomes, generate_lot_reference
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

    def test_lot_sans_anomalie_est_declare_conforme(self):
        """Le cas normal : rien à signaler, donc tout est conforme.

        L'ancienne règle exigeait des diplômes enregistrés et bloquait
        précisément ce cas, puisqu'on ne saisit plus que les non conformes.
        """
        self.lot.diplomes.all().delete()
        apply_transition(self.lot, Statut.EN_VERIFICATION, self.agent_etude)
        ok, message = apply_transition(self.lot, Statut.CONFORME, self.agent_etude)
        self.assertTrue(ok, message)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.CONFORME)

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
        """Un diplôme saisi sans anomalie ne retire rien aux conformes.

        Le lot annonce trois diplômes. Un seul est signalé non conforme : les
        deux autres le sont d'office, qu'ils aient ou non une fiche.
        """
        Diplome.objects.create(lot=self.lot, nom_beneficiaire="Awa Mbala", numero_diplome="D-001")
        Diplome.objects.create(
            lot=self.lot,
            nom_beneficiaire="Jean Kalala",
            numero_diplome="D-002",
            statut=Diplome.Status.NON_CONFORME,
            anomalie=Diplome.Anomalie.MANQUANT,
        )

        self.assertEqual(self.lot.nombre_anomalies, 1)
        self.assertEqual(self.lot.nombre_conformes, 2)
        self.assertEqual(self.lot.ecart, 0)
        self.assertFalse(self.lot.has_ecart)
        self.assertTrue(self.lot.has_anomalies)

    def test_etablissement_falls_back_on_the_lot(self):
        diplome = Diplome.objects.create(lot=self.lot, nom_beneficiaire="Awa", numero_diplome="D-010")
        self.assertEqual(diplome.etablissement_effectif, "Université de Kinshasa")


@override_settings(SECURE_SSL_REDIRECT=False)
class ListeDuLotTests(TestCase):
    """La liste arrive en PDF ou en Word, et n'est pas dépouillée.

    Les établissements ne produisent pas de tableur : exiger un format qu'on
    ne reçoit jamais revient à n'avoir aucune liste. Elle est donc jointe
    telle quelle, comme pièce de référence.
    """

    def setUp(self):
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE)
        self.agent_isole = make_user("isole", ROLE_AGENT)
        self.lot = LotDiplomes.objects.create(
            etablissement="Université de Kinshasa", nombre_annonce=3
        )

    def _fichier(self, nom="liste.pdf", taille=1024):
        return SimpleUploadedFile(nom, b"x" * taille, content_type="application/pdf")

    def _donnees_lot(self, **extra):
        donnees = {
            "reference": "",
            "etablissement": "Université de Kinshasa",
            "date_arrivee": "2026-08-13",
            "nombre_annonce": 3,
            "agent_receptionnaire": "",
            "service_concerne": "",
            "observation": "",
        }
        donnees.update(extra)
        return donnees

    def test_une_liste_pdf_est_acceptee(self):
        formulaire = LotDiplomesForm(
            data=self._donnees_lot(), files={"fichier_liste": self._fichier("liste.pdf")}
        )
        self.assertTrue(formulaire.is_valid(), formulaire.errors)

    def test_une_liste_word_est_acceptee(self):
        for nom in ("liste.doc", "liste.docx"):
            formulaire = LotDiplomesForm(
                data=self._donnees_lot(), files={"fichier_liste": self._fichier(nom)}
            )
            self.assertTrue(formulaire.is_valid(), f"{nom} : {formulaire.errors}")

    def test_un_tableur_est_refuse(self):
        """Le format qu'on ne reçoit jamais et qui bloquait l'enregistrement."""
        for nom in ("liste.xlsx", "liste.csv"):
            formulaire = LotDiplomesForm(
                data=self._donnees_lot(), files={"fichier_liste": self._fichier(nom)}
            )
            self.assertFalse(formulaire.is_valid(), nom)
            self.assertIn("fichier_liste", formulaire.errors)

    def test_un_fichier_trop_lourd_est_refuse(self):
        formulaire = LotDiplomesForm(
            data=self._donnees_lot(),
            files={"fichier_liste": self._fichier("liste.pdf", taille=11 * 1024 * 1024)},
        )
        self.assertFalse(formulaire.is_valid())

    def test_la_liste_n_est_pas_obligatoire(self):
        """Un lot peut être enregistré avant que la liste ne soit numérisée."""
        formulaire = LotDiplomesForm(data=self._donnees_lot())
        self.assertTrue(formulaire.is_valid(), formulaire.errors)

    def test_le_telechargement_passe_par_une_vue_controlee(self):
        self.lot.fichier_liste.save("liste.pdf", self._fichier(), save=True)
        self.client.force_login(self.agent_etude)
        reponse = self.client.get(reverse("diplomas:lot_liste_download", args=[self.lot.pk]))
        self.assertEqual(reponse.status_code, 200)
        reponse.close()

    def test_un_lot_sans_liste_renvoie_404(self):
        self.client.force_login(self.agent_etude)
        reponse = self.client.get(reverse("diplomas:lot_liste_download", args=[self.lot.pk]))
        self.assertEqual(reponse.status_code, 404)

    def test_un_agent_sans_acces_n_obtient_pas_la_liste(self):
        self.lot.fichier_liste.save("liste.pdf", self._fichier(), save=True)
        self.client.force_login(self.agent_isole)
        reponse = self.client.get(reverse("diplomas:lot_liste_download", args=[self.lot.pk]))
        self.assertIn(reponse.status_code, (403, 404))


class ConformiteDuLotTests(TestCase):
    """Seuls les non conformes sont saisis ; la différence est conforme.

    C'est le cœur du nouveau mode de vérification : dépouiller deux cents
    lignes pour n'en signaler que trois n'a jamais eu de sens.
    """

    def setUp(self):
        self.lot = LotDiplomes.objects.create(
            etablissement="Université de Kinshasa", nombre_annonce=200
        )

    def _signaler_non_conforme(self, numero):
        return Diplome.objects.create(
            lot=self.lot,
            nom_beneficiaire=f"Agent {numero}",
            numero_diplome=numero,
            statut=Diplome.Status.NON_CONFORME,
            anomalie=Diplome.Anomalie.PIECE_NON_CONFORME,
        )

    def test_sans_anomalie_tout_le_lot_est_conforme(self):
        self.assertEqual(self.lot.nombre_conformes, 200)
        self.assertEqual(self.lot.nombre_anomalies, 0)
        self.assertFalse(self.lot.has_ecart)

    def test_les_conformes_sont_la_difference(self):
        self._signaler_non_conforme("D-001")
        self._signaler_non_conforme("D-002")
        self._signaler_non_conforme("D-003")
        self.assertEqual(self.lot.nombre_anomalies, 3)
        self.assertEqual(self.lot.nombre_conformes, 197)

    def test_le_taux_de_conformite_suit(self):
        for numero in range(1, 21):
            self._signaler_non_conforme(f"D-{numero:03d}")
        self.assertEqual(self.lot.nombre_conformes, 180)
        self.assertEqual(self.lot.taux_conformite, 90)

    def test_plus_d_anomalies_que_d_annonces_est_signale(self):
        """Le nombre annoncé est faux, ou une saisie est en double."""
        lot = LotDiplomes.objects.create(etablissement="ISP Gombe", nombre_annonce=2)
        for numero in range(1, 4):
            Diplome.objects.create(
                lot=lot,
                nom_beneficiaire=f"Agent {numero}",
                numero_diplome=f"E-{numero}",
                statut=Diplome.Status.NON_CONFORME,
                anomalie=Diplome.Anomalie.PIECE_NON_CONFORME,
            )
        self.assertTrue(lot.has_ecart)
        self.assertEqual(lot.ecart, 1)
        self.assertEqual(lot.nombre_conformes, 0)

    def test_un_lot_sans_nombre_annonce_ne_divise_pas_par_zero(self):
        lot = LotDiplomes.objects.create(etablissement="ISP Gombe", nombre_annonce=0)
        self.assertEqual(lot.taux_conformite, 0)
        self.assertEqual(lot.nombre_conformes, 0)


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


@override_settings(SECURE_SSL_REDIRECT=False)
class ConsultationDeLaListeTests(TestCase):
    """La liste se consulte dans la page, sans passer par le téléchargement.

    C'est le document qu'on garde sous les yeux pendant la vérification : le
    reléguer derrière un téléchargement obligerait à le rouvrir à chaque
    diplôme contrôlé.
    """

    def setUp(self):
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE)
        self.lot = LotDiplomes.objects.create(
            etablissement="Université de Kinshasa", nombre_annonce=5
        )
        self.client.force_login(self.agent_etude)

    def _joindre(self, nom="liste.pdf"):
        self.lot.fichier_liste.save(
            nom, SimpleUploadedFile(nom, b"%PDF-1.4 contenu", content_type="application/pdf"), save=True
        )

    def test_un_pdf_s_affiche_dans_la_page(self):
        self._joindre()
        reponse = self.client.get(
            reverse("diplomas:lot_liste_download", args=[self.lot.pk]), {"consulter": "1"}
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertNotIn("attachment", reponse.get("Content-Disposition", ""))
        self.assertEqual(reponse["X-Content-Type-Options"], "nosniff")
        reponse.close()

    def test_un_document_word_est_toujours_telecharge(self):
        """Le navigateur ne sait pas le rendre, et le servir en ligne
        laisserait un fichier déposé décider de son interprétation."""
        self._joindre("liste.docx")
        reponse = self.client.get(
            reverse("diplomas:lot_liste_download", args=[self.lot.pk]), {"consulter": "1"}
        )
        self.assertIn("attachment", reponse["Content-Disposition"])
        reponse.close()

    def test_sans_consulter_le_fichier_est_telecharge(self):
        self._joindre()
        reponse = self.client.get(reverse("diplomas:lot_liste_download", args=[self.lot.pk]))
        self.assertIn("attachment", reponse["Content-Disposition"])
        reponse.close()

    def test_la_fiche_du_lot_montre_l_apercu(self):
        self._joindre()
        reponse = self.client.get(reverse("diplomas:lot_detail", args=[self.lot.pk]))
        self.assertContains(reponse, "diploma-liste-apercu")
        self.assertContains(reponse, "Ouvrir dans un onglet")

    def test_la_fiche_invite_a_joindre_la_liste_quand_elle_manque(self):
        reponse = self.client.get(reverse("diplomas:lot_detail", args=[self.lot.pk]))
        self.assertContains(reponse, "Liste non jointe")
        self.assertNotContains(reponse, "diploma-liste-apercu")


@override_settings(SECURE_SSL_REDIRECT=False)
class ApercuDansLaFicheTests(TestCase):
    """L'aperçu doit pouvoir s'afficher dans un cadre de la fiche.

    L'intergiciel anti-détournement de clic pose « X-Frame-Options: DENY » sur
    toutes les réponses. Sans exception explicite, le navigateur refuse le
    document et la fiche affiche « Échec de chargement du document PDF ».
    """

    def setUp(self):
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE)
        self.lot = LotDiplomes.objects.create(
            etablissement="Université de Kinshasa", nombre_annonce=4
        )
        self.lot.fichier_liste.save(
            "liste.pdf",
            SimpleUploadedFile("liste.pdf", b"%PDF-1.4 contenu", content_type="application/pdf"),
            save=True,
        )
        self.client.force_login(self.agent_etude)

    def test_la_consultation_autorise_le_cadre_de_meme_origine(self):
        reponse = self.client.get(
            reverse("diplomas:lot_liste_download", args=[self.lot.pk]), {"consulter": "1"}
        )
        self.assertEqual(reponse["X-Frame-Options"], "SAMEORIGIN")
        reponse.close()

    def test_le_telechargement_reste_interdit_de_cadre(self):
        """Rien n'oblige à assouplir la règle hors de l'aperçu."""
        reponse = self.client.get(reverse("diplomas:lot_liste_download", args=[self.lot.pk]))
        self.assertEqual(reponse["X-Frame-Options"], "DENY")
        reponse.close()


class ConformiteSansSaisieTests(TestCase):
    """Un lot sans anomalie doit pouvoir être déclaré conforme.

    C'est le cas normal du nouveau mode de vérification. L'ancienne règle
    exigeait des diplômes enregistrés : elle bloquait précisément ce cas.
    """

    def setUp(self):
        self.agent_etude = make_user("verificateur", ROLE_AGENT_ETUDE)
        self.lot = LotDiplomes.objects.create(
            etablissement="Université de Kinshasa",
            nombre_annonce=120,
            cree_par=self.agent_etude,
        )

    def test_un_lot_sans_anomalie_passe_conforme(self):
        ok, message = apply_transition(self.lot, Statut.EN_VERIFICATION, self.agent_etude)
        self.assertTrue(ok, message)
        ok, message = apply_transition(self.lot, Statut.CONFORME, self.agent_etude)
        self.assertTrue(ok, message)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.statut, Statut.CONFORME)

    def test_une_anomalie_ouverte_bloque_toujours(self):
        Diplome.objects.create(
            lot=self.lot,
            nom_beneficiaire="Awa Mbala",
            numero_diplome="D-001",
            statut=Diplome.Status.NON_CONFORME,
            anomalie=Diplome.Anomalie.MANQUANT,
        )
        apply_transition(self.lot, Statut.EN_VERIFICATION, self.agent_etude)
        ok, message = apply_transition(self.lot, Statut.CONFORME, self.agent_etude)
        self.assertFalse(ok)
        self.assertIn("non conformes", message)

    def test_un_lot_sans_nombre_annonce_est_refuse(self):
        """Sans nombre annoncé, rien ne dit ce qui a été vérifié."""
        lot = LotDiplomes.objects.create(
            etablissement="ISP Gombe", nombre_annonce=0, cree_par=self.agent_etude
        )
        apply_transition(lot, Statut.EN_VERIFICATION, self.agent_etude)
        ok, message = apply_transition(lot, Statut.CONFORME, self.agent_etude)
        self.assertFalse(ok)
        self.assertIn("annoncé", message)
