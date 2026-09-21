import importlib
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.constants import (
    ROLE_AGENT,
    ROLE_AGENT_ETUDE,
    ROLE_DIRECTEUR_GENERAL,
    ROLE_SECRETARIAT,
)

from .forms import BordereauForm
from .models import Bordereau, Organisme, Trimestre, trimestre_de
from .selectors import (
    get_bordereaux_de_la_boite,
    get_compteurs_periode,
    get_tableau_annuel,
)
from .services import signer_engagement, signer_liquidation

# La liste reste figee dans sa migration : c'est elle qui fait foi, et une
# migration ne doit pas dependre de code applicatif susceptible de changer.
# On la charge comme Django charge ses propres migrations.
ORGANISMES_REFERENCE = importlib.import_module(
    "bordereaux.migrations.0003_organismes_dges"
).ORGANISMES

Etat = Bordereau.Etat


def make_user(username, role):
    user = User.objects.create_user(username=username, password="StrongPass123!")
    profile = user.profil
    profile.role = role
    profile.actif = True
    profile.save()
    return user


def make_organisme(nom, sigle):
    """Reprend l'organisme du referentiel quand il porte deja ce nom.

    La migration `0003_organismes_dges` installe la liste reelle de la DGES,
    y compris dans la base de test. Creer un organisme du meme nom violerait
    la contrainte d'unicite : les tests s'appuient donc sur le referentiel
    plutot que de le contredire.
    """
    organisme, _ = Organisme.objects.get_or_create(nom=nom, defaults={"sigle": sigle})
    return organisme


def make_bordereau(organisme, numero, **kwargs):
    valeurs = {
        "organisme": organisme,
        "annee": 2026,
        "trimestre": Trimestre.T1.value,
        "numero": numero,
        "date_reception": date(2026, 1, 5),
    }
    valeurs.update(kwargs)
    return Bordereau.objects.create(**valeurs)


@override_settings(SECURE_SSL_REDIRECT=False)
class ReferentielOrganismesTests(TestCase):
    """La liste des organismes suivis est installee par migration."""

    def test_les_organismes_de_la_dges_sont_installes(self):
        self.assertEqual(Organisme.objects.count(), len(ORGANISMES_REFERENCE))

    def test_chaque_organisme_porte_son_sigle(self):
        attendus = {nom: sigle for sigle, nom in ORGANISMES_REFERENCE}
        for nom, sigle in Organisme.objects.values_list("nom", "sigle"):
            self.assertEqual(sigle, attendus.get(nom), nom)

    def test_les_organismes_sont_suivis_par_defaut(self):
        self.assertFalse(Organisme.objects.filter(actif=False).exists())

    def test_les_sigles_a_casse_mixte_sont_preserves(self):
        # « UJLoG » porte sa casse, et « Prise en charge » n'est pas un
        # acronyme : les passer en majuscules les denaturerait.
        self.assertTrue(Organisme.objects.filter(sigle="UJLoG").exists())
        self.assertTrue(Organisme.objects.filter(sigle="Prise en charge").exists())

    def test_les_accents_ont_survecu_a_l_installation(self):
        organisme = Organisme.objects.get(sigle="UFHB")

        self.assertEqual(organisme.nom, "Université Félix Houphouët-Boigny")


@override_settings(SECURE_SSL_REDIRECT=False)
class EtatBordereauTests(TestCase):
    """L'etat se deduit des dates, comme le decrit la fiche de modelisation."""

    def setUp(self):
        self.organisme = make_organisme("Université Félix Houphouët-Boigny", "UFHB")

    def test_dossier_initial_attend_son_engagement(self):
        bordereau = make_bordereau(self.organisme, "BORD-003")

        self.assertEqual(bordereau.etat, Etat.ATTENTE_ENGAGEMENT)
        self.assertFalse(bordereau.mandat_deduit)
        self.assertEqual(bordereau.mandat_label, "Non déduit")

    def test_engagement_signe_met_le_dossier_en_cours(self):
        bordereau = make_bordereau(self.organisme, "BORD-002", date_engagement=date(2026, 2, 8))

        self.assertEqual(bordereau.etat, Etat.EN_COURS)
        self.assertFalse(bordereau.mandat_deduit)

    def test_liquidation_signee_termine_le_dossier_et_deduit_le_mandat(self):
        bordereau = make_bordereau(
            self.organisme,
            "BORD-001",
            date_engagement=date(2026, 1, 10),
            date_liquidation=date(2026, 1, 25),
        )

        self.assertEqual(bordereau.etat, Etat.TERMINE)
        self.assertTrue(bordereau.mandat_deduit)
        self.assertEqual(bordereau.mandat_label, "Validé par déduction")
        self.assertEqual(bordereau.delai_traitement, 20)

    def test_trimestre_se_deduit_du_mois(self):
        self.assertEqual(trimestre_de(date(2026, 1, 31)), Trimestre.T1)
        self.assertEqual(trimestre_de(date(2026, 6, 1)), Trimestre.T2)
        self.assertEqual(trimestre_de(date(2026, 9, 30)), Trimestre.T3)
        self.assertEqual(trimestre_de(date(2026, 12, 25)), Trimestre.T4)


@override_settings(SECURE_SSL_REDIRECT=False)
class SignatureTests(TestCase):
    def setUp(self):
        self.user = make_user("secretariat", ROLE_SECRETARIAT)
        self.organisme = make_organisme("Université de Cocody", "UC")
        self.bordereau = make_bordereau(self.organisme, "BORD-010")

    def test_signature_engagement_enregistre_un_historique(self):
        reussi, _ = signer_engagement(self.bordereau, self.user, date(2026, 1, 12))

        self.bordereau.refresh_from_db()
        self.assertTrue(reussi)
        self.assertEqual(self.bordereau.etat, Etat.EN_COURS)
        historique = self.bordereau.historiques.first()
        self.assertEqual(historique.action, "Signature de l'engagement")
        self.assertEqual(historique.nouvel_etat, Etat.EN_COURS)

    def test_liquidation_refusee_sans_engagement(self):
        reussi, message = signer_liquidation(self.bordereau, self.user, date(2026, 1, 20))

        self.bordereau.refresh_from_db()
        self.assertFalse(reussi)
        self.assertIn("engagement", message.lower())
        self.assertEqual(self.bordereau.etat, Etat.ATTENTE_ENGAGEMENT)

    def test_liquidation_mentionne_la_deduction_du_mandat(self):
        signer_engagement(self.bordereau, self.user, date(2026, 1, 12))
        reussi, _ = signer_liquidation(self.bordereau, self.user, date(2026, 1, 25))

        self.bordereau.refresh_from_db()
        self.assertTrue(reussi)
        self.assertTrue(self.bordereau.mandat_deduit)
        self.assertIn("déduction", self.bordereau.historiques.first().commentaire)

    def test_signature_anterieure_a_la_reception_refusee(self):
        reussi, message = signer_engagement(self.bordereau, self.user, date(2026, 1, 1))

        self.assertFalse(reussi)
        self.assertIn("réception", message)

    def test_liquidation_anterieure_a_l_engagement_refusee(self):
        signer_engagement(self.bordereau, self.user, date(2026, 1, 12))
        reussi, message = signer_liquidation(self.bordereau, self.user, date(2026, 1, 8))

        self.assertFalse(reussi)
        self.assertIn("avant l'engagement", message)

    def test_signature_datee_du_futur_refusee(self):
        demain = timezone.localdate() + timedelta(days=1)
        bordereau = make_bordereau(
            self.organisme,
            "BORD-011",
            date_reception=timezone.localdate(),
            annee=timezone.localdate().year,
        )

        reussi, message = signer_engagement(bordereau, self.user, demain)

        self.assertFalse(reussi)
        self.assertIn("futur", message)

    def test_seconde_signature_du_meme_type_refusee(self):
        signer_engagement(self.bordereau, self.user, date(2026, 1, 12))
        reussi, message = signer_engagement(self.bordereau, self.user, date(2026, 1, 15))

        self.assertFalse(reussi)
        self.assertIn("déjà signé", message)


@override_settings(SECURE_SSL_REDIRECT=False)
class ComptagesTests(TestCase):
    """Les comptages SQL doivent dire la meme chose que `Bordereau.etat`."""

    def setUp(self):
        self.user = make_user("dg", ROLE_DIRECTEUR_GENERAL)
        self.organisme = make_organisme("Université Félix Houphouët-Boigny", "UFHB")
        make_bordereau(
            self.organisme,
            "BORD-001",
            date_engagement=date(2026, 1, 10),
            date_liquidation=date(2026, 1, 25),
        )
        make_bordereau(self.organisme, "BORD-002", date_engagement=date(2026, 2, 8))
        make_bordereau(self.organisme, "BORD-003")
        make_bordereau(
            self.organisme,
            "BORD-004",
            date_engagement=date(2026, 3, 15),
            date_liquidation=date(2026, 3, 28),
        )

    def test_repartition_du_trimestre(self):
        compteurs = get_compteurs_periode(self.user, 2026, Trimestre.T1.value, self.organisme)

        self.assertEqual(compteurs["total"], 4)
        self.assertEqual(compteurs["termines"], 2)
        self.assertEqual(compteurs["en_cours"], 1)
        self.assertEqual(compteurs["attente"], 1)

    def test_la_somme_des_etats_vaut_le_total(self):
        compteurs = get_compteurs_periode(self.user, 2026)
        somme = compteurs["termines"] + compteurs["en_cours"] + compteurs["attente"]

        self.assertEqual(somme, compteurs["total"])

    def test_tableau_annuel_ouvre_quatre_boites_par_organisme(self):
        lignes = get_tableau_annuel(self.user, 2026, [self.organisme])

        self.assertEqual(len(lignes), 1)
        self.assertEqual(len(lignes[0]["boites"]), 4)
        self.assertEqual(lignes[0]["total"], 4)
        self.assertEqual(lignes[0]["boites"][0]["termines"], 2)
        # Les trimestres sans bordereau restent presents, a zero.
        self.assertEqual(lignes[0]["boites"][1]["total"], 0)


@override_settings(SECURE_SSL_REDIRECT=False)
class BordereauFormTests(TestCase):
    def setUp(self):
        self.organisme = make_organisme("Université de Bouaké", "UB")

    def donnees(self, **surcharges):
        valeurs = {
            "organisme": self.organisme.pk,
            "annee": 2026,
            "trimestre": Trimestre.T1.value,
            "numero": "BORD-001",
            "date_reception": "2026-01-05",
            "date_engagement": "",
            "date_liquidation": "",
            "observation": "",
        }
        valeurs.update(surcharges)
        return valeurs

    def test_numero_en_double_refuse_dans_la_meme_annee(self):
        make_bordereau(self.organisme, "BORD-001")

        form = BordereauForm(data=self.donnees())

        self.assertFalse(form.is_valid())
        self.assertIn("numero", form.errors)

    def test_meme_numero_accepte_sur_une_autre_annee(self):
        make_bordereau(self.organisme, "BORD-001")

        form = BordereauForm(data=self.donnees(annee=2025, date_reception="2025-01-06"))

        self.assertTrue(form.is_valid(), form.errors)

    def test_date_de_reception_dans_le_futur_refusee(self):
        demain = timezone.localdate() + timedelta(days=1)

        form = BordereauForm(data=self.donnees(date_reception=demain.isoformat()))

        self.assertFalse(form.is_valid())
        self.assertIn("date_reception", form.errors)

    def test_liquidation_sans_engagement_refusee(self):
        form = BordereauForm(data=self.donnees(date_liquidation="2026-01-25"))

        self.assertFalse(form.is_valid())
        self.assertIn("date_engagement", form.errors)

    def test_chronologie_des_signatures_controlee(self):
        form = BordereauForm(
            data=self.donnees(date_engagement="2026-01-20", date_liquidation="2026-01-10")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("date_liquidation", form.errors)


@override_settings(SECURE_SSL_REDIRECT=False)
class NumeroFacultatifTests(TestCase):
    """Un bordereau peut etre enregistre avant d'etre numerote."""

    def setUp(self):
        self.organisme = make_organisme("Université de Daloa", "UJLoG")

    def test_bordereau_sans_numero_se_designe_par_sa_date(self):
        bordereau = make_bordereau(self.organisme, "")

        self.assertFalse(bordereau.est_numerote)
        self.assertIn("05/01/2026", bordereau.libelle)
        self.assertIn("Sans numéro", bordereau.libelle)

    def test_plusieurs_bordereaux_sans_numero_coexistent(self):
        make_bordereau(self.organisme, "")
        make_bordereau(self.organisme, "", date_reception=date(2026, 1, 20))

        self.assertEqual(Bordereau.objects.filter(numero="").count(), 2)

    def test_formulaire_accepte_un_numero_vide(self):
        form = BordereauForm(
            data={
                "organisme": self.organisme.pk,
                "annee": 2026,
                "trimestre": Trimestre.T1.value,
                "numero": "",
                "date_reception": "2026-01-05",
                "date_engagement": "",
                "date_liquidation": "",
                "observation": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_le_doublon_reste_refuse_entre_numeros_renseignes(self):
        make_bordereau(self.organisme, "BORD-001")
        make_bordereau(self.organisme, "")

        form = BordereauForm(
            data={
                "organisme": self.organisme.pk,
                "annee": 2026,
                "trimestre": Trimestre.T1.value,
                "numero": "BORD-001",
                "date_reception": "2026-01-05",
                "date_engagement": "",
                "date_liquidation": "",
                "observation": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("numero", form.errors)

    def test_les_dossiers_sans_numero_ferment_la_boite(self):
        user = make_user("secretariat", ROLE_SECRETARIAT)
        make_bordereau(self.organisme, "")
        make_bordereau(self.organisme, "BORD-002", date_reception=date(2026, 1, 8))
        make_bordereau(self.organisme, "BORD-001", date_reception=date(2026, 1, 9))

        numeros = list(
            get_bordereaux_de_la_boite(
                user, 2026, Trimestre.T1.value, self.organisme
            ).values_list("numero", flat=True)
        )

        self.assertEqual(numeros, ["BORD-001", "BORD-002", ""])


@override_settings(SECURE_SSL_REDIRECT=False)
class PieceJointeTests(TestCase):
    """Le bordereau lui-meme peut etre charge et reste consultable.

    Les depots vont dans un dossier temporaire, detruit a la fin : sans cela
    chaque execution laisserait des pieces de test dans le `media` reel.
    """

    @classmethod
    def setUpClass(cls):
        cls.media_temporaire = tempfile.mkdtemp(prefix="bordereaux-tests-")
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_temporaire)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        shutil.rmtree(cls.media_temporaire, ignore_errors=True)

    def setUp(self):
        self.user = make_user("secretariat", ROLE_SECRETARIAT)
        self.client.force_login(self.user)
        self.organisme = make_organisme("Université de Korhogo", "UPGC")

    def piece(self, nom="bordereau.pdf", contenu=b"%PDF-1.4 piece de test"):
        return SimpleUploadedFile(nom, contenu, content_type="application/pdf")

    def donnees(self, **surcharges):
        valeurs = {
            "organisme": self.organisme.pk,
            "annee": 2026,
            "trimestre": Trimestre.T1.value,
            "numero": "BORD-050",
            "date_reception": "2026-01-05",
            "date_engagement": "",
            "date_liquidation": "",
            "observation": "",
        }
        valeurs.update(surcharges)
        return valeurs

    def test_le_bordereau_joint_est_enregistre(self):
        reponse = self.client.post(
            reverse("bordereaux:create"),
            {**self.donnees(), "fichier": self.piece()},
        )

        bordereau = Bordereau.objects.get(numero="BORD-050")
        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(bordereau.fichier)
        self.assertTrue(bordereau.fichier_est_pdf)

    def test_un_format_non_prevu_est_refuse(self):
        reponse = self.client.post(
            reverse("bordereaux:create"),
            {
                **self.donnees(),
                "fichier": SimpleUploadedFile("bordereau.exe", b"MZ", content_type="application/exe"),
            },
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Bordereau.objects.filter(numero="BORD-050").exists())
        self.assertContains(reponse, "Format non pris en charge")

    def test_la_piece_ne_se_sert_qu_aux_comptes_autorises(self):
        self.client.post(reverse("bordereaux:create"), {**self.donnees(), "fichier": self.piece()})
        bordereau = Bordereau.objects.get(numero="BORD-050")

        self.client.force_login(make_user("agent", ROLE_AGENT))
        reponse = self.client.get(reverse("bordereaux:fichier", args=[bordereau.pk]))

        self.assertEqual(reponse.status_code, 403)

    def test_le_pdf_s_affiche_dans_la_fiche_sans_etre_devine(self):
        self.client.post(reverse("bordereaux:create"), {**self.donnees(), "fichier": self.piece()})
        bordereau = Bordereau.objects.get(numero="BORD-050")

        reponse = self.client.get(reverse("bordereaux:fichier", args=[bordereau.pk]) + "?consulter=1")

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["X-Content-Type-Options"], "nosniff")
        self.assertEqual(reponse["X-Frame-Options"], "SAMEORIGIN")
        self.assertNotIn("attachment", reponse.get("Content-Disposition", ""))

    def test_un_document_word_est_toujours_telecharge(self):
        self.client.post(
            reverse("bordereaux:create"),
            {**self.donnees(), "fichier": self.piece("bordereau.docx", b"PK document")},
        )
        bordereau = Bordereau.objects.get(numero="BORD-050")

        reponse = self.client.get(reverse("bordereaux:fichier", args=[bordereau.pk]) + "?consulter=1")

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("attachment", reponse["Content-Disposition"])

    def test_fiche_sans_piece_renvoie_404(self):
        bordereau = make_bordereau(self.organisme, "BORD-060")

        reponse = self.client.get(reverse("bordereaux:fichier", args=[bordereau.pk]))

        self.assertEqual(reponse.status_code, 404)


@override_settings(SECURE_SSL_REDIRECT=False)
class AccesTests(TestCase):
    def setUp(self):
        self.organisme = make_organisme("Université Félix Houphouët-Boigny", "UFHB")
        self.bordereau = make_bordereau(self.organisme, "BORD-001")

    def test_agent_sans_capacite_n_accede_pas_au_suivi(self):
        self.client.force_login(make_user("agent", ROLE_AGENT))

        reponse = self.client.get(reverse("bordereaux:tableau"))

        self.assertEqual(reponse.status_code, 403)

    def test_dg_consulte_mais_ne_saisit_pas(self):
        self.client.force_login(make_user("dg", ROLE_DIRECTEUR_GENERAL))

        self.assertEqual(self.client.get(reverse("bordereaux:tableau")).status_code, 200)
        self.assertEqual(self.client.get(reverse("bordereaux:create")).status_code, 403)

    def test_secretariat_saisit_un_bordereau(self):
        self.client.force_login(make_user("secretariat", ROLE_SECRETARIAT))

        reponse = self.client.post(
            reverse("bordereaux:create"),
            {
                "organisme": self.organisme.pk,
                "annee": 2026,
                "trimestre": Trimestre.T2.value,
                "numero": "BORD-020",
                "date_reception": "2026-04-03",
                "date_engagement": "",
                "date_liquidation": "",
                "observation": "",
            },
        )

        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(Bordereau.objects.filter(numero="BORD-020").exists())

    def test_agent_etude_n_a_pas_acces_au_module(self):
        self.client.force_login(make_user("verificateur", ROLE_AGENT_ETUDE))

        reponse = self.client.get(reverse("bordereaux:tableau"))

        self.assertEqual(reponse.status_code, 403)

    def test_signature_par_une_vue_refusee_au_dg(self):
        self.client.force_login(make_user("dg2", ROLE_DIRECTEUR_GENERAL))

        reponse = self.client.post(
            reverse("bordereaux:signer", args=[self.bordereau.pk, "engagement"]),
            {"date_signature": "2026-01-10", "commentaire": ""},
        )

        self.assertEqual(reponse.status_code, 403)


@override_settings(SECURE_SSL_REDIRECT=False)
class VuesTests(TestCase):
    def setUp(self):
        self.user = make_user("secretariat", ROLE_SECRETARIAT)
        self.client.force_login(self.user)
        self.organisme = make_organisme("Université Félix Houphouët-Boigny", "UFHB")
        self.bordereau = make_bordereau(
            self.organisme,
            "BORD-001",
            date_engagement=date(2026, 1, 10),
            date_liquidation=date(2026, 1, 25),
        )

    def test_la_boite_trimestrielle_liste_ses_bordereaux(self):
        reponse = self.client.get(
            reverse("bordereaux:boite", args=[2026, Trimestre.T1.value, self.organisme.pk])
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "BORD-001")
        self.assertContains(reponse, "Terminé")

    def test_la_fiche_affiche_le_mandat_deduit(self):
        reponse = self.client.get(reverse("bordereaux:detail", args=[self.bordereau.pk]))

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Validé par déduction")

    def test_signature_depuis_la_vue(self):
        bordereau = make_bordereau(self.organisme, "BORD-030")

        reponse = self.client.post(
            reverse("bordereaux:signer", args=[bordereau.pk, "engagement"]),
            {"date_signature": "2026-01-10", "commentaire": "Parapheur n°12"},
        )

        bordereau.refresh_from_db()
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(bordereau.etat, Etat.EN_COURS)

    def test_export_csv_ne_contient_aucun_montant(self):
        reponse = self.client.get(reverse("bordereaux:export_annee", args=[2026]))

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("text/csv", reponse["Content-Type"])
        contenu = reponse.content.decode("utf-8-sig")
        self.assertIn("BORD-001", contenu)
        self.assertIn("Mandat déduit", contenu)
        self.assertNotIn("Montant", contenu)

    def test_organisme_avec_bordereaux_ne_se_supprime_pas(self):
        admin = User.objects.create_superuser("root", "root@dges.local", "StrongPass123!")
        self.client.force_login(admin)

        reponse = self.client.post(
            reverse("bordereaux:organisme_delete", args=[self.organisme.pk]),
            follow=True,
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(Organisme.objects.filter(pk=self.organisme.pk).exists())
