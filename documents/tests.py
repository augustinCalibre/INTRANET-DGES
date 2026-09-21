import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.constants import ROLE_AGENT, ROLE_SECRETARIAT
from accounts.models import Service
from core.models import Notification

from .models import Document
from .selectors import get_visible_documents

@override_settings(SECURE_SSL_REDIRECT=False)
class DocumentSecurityTests(TestCase):
    def setUp(self):
        self.temp_media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.override.enable()

        self.primary_service = Service.objects.create(nom="Planification", actif=True)
        self.secondary_service = Service.objects.create(nom="Archives", actif=True)

        self.manager = User.objects.create_user(username="manager_doc", password="StrongPass123!")
        self.agent = User.objects.create_user(username="agent_doc", password="StrongPass123!")
        self.other_agent = User.objects.create_user(username="autre_agent_doc", password="StrongPass123!")

        self._assign_role(self.manager, ROLE_SECRETARIAT, self.primary_service)
        self._assign_role(self.agent, ROLE_AGENT, self.primary_service)
        self._assign_role(self.other_agent, ROLE_AGENT, self.secondary_service)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.temp_media_root, ignore_errors=True)

    def _assign_role(self, user, role, service):
        profile = user.profil
        profile.role = role
        profile.service = service
        profile.actif = True
        profile.save()

    def test_agent_simple_cannot_access_document_creation_view(self):
        self.client.login(username="agent_doc", password="StrongPass123!")

        response = self.client.get(reverse("documents:create"))

        self.assertEqual(response.status_code, 403)

    @override_settings(DOCUMENT_ALLOWED_EXTENSIONS=("pdf", "txt"), DOCUMENT_MAX_UPLOAD_SIZE=1024)
    def test_disallowed_document_extension_is_rejected(self):
        self.client.login(username="manager_doc", password="StrongPass123!")

        response = self.client.post(
            reverse("documents:create"),
            {
                "titre": "Document dangereux",
                "type_document": Document.Type.RAPPORT,
                "service_concerne": self.primary_service.pk,
                "statut": Document.Status.ACTIF,
                "fichier": SimpleUploadedFile(
                    "payload.html",
                    b"<script>alert('xss')</script>",
                    content_type="text/html",
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Type de fichier non autorise")
        self.assertFalse(Document.objects.filter(titre="Document dangereux").exists())

    def test_document_download_is_limited_to_visible_documents(self):
        document = Document.objects.create(
            titre="Procedure interne",
            type_document=Document.Type.PROCEDURE,
            service_concerne=self.primary_service,
            auteur=self.manager,
            statut=Document.Status.ACTIF,
            fichier=SimpleUploadedFile(
                "procedure.txt",
                b"contenu securise",
                content_type="text/plain",
            ),
        )

        self.client.login(username="autre_agent_doc", password="StrongPass123!")
        hidden_response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(hidden_response.status_code, 404)

        self.client.login(username="agent_doc", password="StrongPass123!")
        allowed_response = self.client.get(reverse("documents:download", args=[document.pk]))

        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(
            allowed_response["Content-Disposition"],
            f'attachment; filename="{Path(document.fichier.name).name}"',
        )
        self.assertEqual(allowed_response["X-Content-Type-Options"], "nosniff")


@override_settings(SECURE_SSL_REDIRECT=False)
class DocumentDestinatairesTests(TestCase):
    """Un document s'adresse a un service, a des agents nommes, ou a tous."""

    def setUp(self):
        self.temp_media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.override.enable()

        self.service = Service.objects.create(nom="Planification", actif=True)
        self.autre_service = Service.objects.create(nom="Archives", actif=True)

        self.secretaire = self._compte("secretaire_dest", ROLE_SECRETARIAT, self.service)
        self.agent_du_service = self._compte("agent_du_service", ROLE_AGENT, self.service)
        self.agent_exterieur = self._compte("agent_exterieur", ROLE_AGENT, self.autre_service)
        self.agent_tiers = self._compte("agent_tiers", ROLE_AGENT, self.autre_service)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.temp_media_root, ignore_errors=True)

    def _compte(self, username, role, service):
        user = User.objects.create_user(username=username, password="StrongPass123!")
        profile = user.profil
        profile.role = role
        profile.service = service
        profile.actif = True
        profile.save()
        return user

    def _document(self, **kwargs):
        valeurs = {
            "titre": "Note de service",
            "type_document": Document.Type.NOTE,
            "auteur": self.secretaire,
            "statut": Document.Status.ACTIF,
            "fichier": SimpleUploadedFile("note.txt", b"contenu", content_type="text/plain"),
        }
        valeurs.update(kwargs)
        return Document.objects.create(**valeurs)

    def _voit(self, user, document):
        return get_visible_documents(user).filter(pk=document.pk).exists()

    def test_un_agent_nomme_voit_le_document_hors_de_son_service(self):
        document = self._document()
        document.destinataires.add(self.agent_exterieur)

        self.assertTrue(self._voit(self.agent_exterieur, document))
        self.assertFalse(self._voit(self.agent_tiers, document))

    def test_le_document_pour_tous_est_visible_de_chacun(self):
        document = self._document(pour_tous=True)

        self.assertTrue(self._voit(self.agent_exterieur, document))
        self.assertTrue(self._voit(self.agent_tiers, document))
        self.assertTrue(self._voit(self.agent_du_service, document))

    def test_le_service_reste_un_chemin_de_diffusion(self):
        document = self._document(service_concerne=self.service)

        self.assertTrue(self._voit(self.agent_du_service, document))
        self.assertFalse(self._voit(self.agent_exterieur, document))

    def test_service_et_agents_se_cumulent(self):
        document = self._document(service_concerne=self.service)
        document.destinataires.add(self.agent_exterieur)

        self.assertTrue(self._voit(self.agent_du_service, document))
        self.assertTrue(self._voit(self.agent_exterieur, document))
        self.assertFalse(self._voit(self.agent_tiers, document))

    def test_un_document_sans_destination_ne_sort_pas_de_chez_son_auteur(self):
        document = self._document()

        self.assertTrue(self._voit(self.secretaire, document))
        self.assertFalse(self._voit(self.agent_du_service, document))
        self.assertTrue(document.est_sans_destinataire)

    def test_les_destinataires_sont_enregistres_par_le_formulaire(self):
        # `save(commit=False)` dans la vue ignore les relations multiples :
        # sans `save_m2m()`, les destinataires disparaissaient en silence.
        self.client.login(username="secretaire_dest", password="StrongPass123!")

        reponse = self.client.post(
            reverse("documents:create"),
            {
                "titre": "Note diffusée",
                "type_document": Document.Type.NOTE,
                "service_concerne": self.service.pk,
                "destinataires": [self.agent_exterieur.pk, self.agent_tiers.pk],
                "statut": Document.Status.ACTIF,
                "fichier": SimpleUploadedFile("note.txt", b"contenu", content_type="text/plain"),
            },
        )

        document = Document.objects.get(titre="Note diffusée")
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(document.destinataires.count(), 2)

    def test_pour_tous_absorbe_les_autres_destinations(self):
        self.client.login(username="secretaire_dest", password="StrongPass123!")

        self.client.post(
            reverse("documents:create"),
            {
                "titre": "Circulaire générale",
                "type_document": Document.Type.NOTE,
                "service_concerne": self.service.pk,
                "destinataires": [self.agent_exterieur.pk],
                "pour_tous": "on",
                "statut": Document.Status.ACTIF,
                "fichier": SimpleUploadedFile("note.txt", b"contenu", content_type="text/plain"),
            },
        )

        document = Document.objects.get(titre="Circulaire générale")
        self.assertTrue(document.pour_tous)
        self.assertIsNone(document.service_concerne)
        self.assertEqual(document.destinataires.count(), 0)
        self.assertEqual(document.portee_labels, ["Tous les agents"])

    def test_la_portee_enumere_le_service_puis_les_agents(self):
        document = self._document(service_concerne=self.service)
        document.destinataires.add(self.agent_exterieur)

        self.assertEqual(
            document.portee_labels,
            [self.service.nom, self.agent_exterieur.username],
        )

    def test_le_telechargement_suit_la_diffusion(self):
        document = self._document(pour_tous=True)

        self.client.login(username="agent_tiers", password="StrongPass123!")
        reponse = self.client.get(reverse("documents:download", args=[document.pk]))

        self.assertEqual(reponse.status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False)
class DocumentNotificationsTests(TestCase):
    """Un destinataire est averti, et une seule fois."""

    def setUp(self):
        self.temp_media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.override.enable()

        self.service = Service.objects.create(nom="Planification", actif=True)
        self.autre_service = Service.objects.create(nom="Archives", actif=True)
        self.secretaire = self._compte("secretaire_notif", ROLE_SECRETARIAT, self.service)
        self.agent_du_service = self._compte("agent_notifie", ROLE_AGENT, self.service)
        self.agent_exterieur = self._compte("agent_hors", ROLE_AGENT, self.autre_service)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.temp_media_root, ignore_errors=True)

    def _compte(self, username, role, service):
        user = User.objects.create_user(username=username, password="StrongPass123!")
        profile = user.profil
        profile.role = role
        profile.service = service
        profile.actif = True
        profile.save()
        return user

    def _notifications(self, user):
        return Notification.objects.filter(
            utilisateur=user,
            type_notification=Notification.Type.DOCUMENT,
        )

    def _deposer(self, **extra):
        donnees = {
            "titre": "Note diffusée",
            "type_document": Document.Type.NOTE,
            "statut": Document.Status.ACTIF,
            "fichier": SimpleUploadedFile("note.txt", b"contenu", content_type="text/plain"),
        }
        donnees.update(extra)
        self.client.login(username="secretaire_notif", password="StrongPass123!")
        return self.client.post(reverse("documents:create"), donnees)

    def test_un_agent_nomme_est_averti(self):
        self._deposer(destinataires=[self.agent_exterieur.pk])

        self.assertEqual(self._notifications(self.agent_exterieur).count(), 1)
        notification = self._notifications(self.agent_exterieur).first()
        self.assertIn("Note diffusée", notification.titre)
        self.assertIn("/download/", notification.url)

    def test_le_service_vise_est_averti(self):
        self._deposer(service_concerne=self.service.pk)

        self.assertEqual(self._notifications(self.agent_du_service).count(), 1)
        self.assertEqual(self._notifications(self.agent_exterieur).count(), 0)

    def test_la_diffusion_generale_avertit_tout_le_monde(self):
        self._deposer(pour_tous="on")

        self.assertEqual(self._notifications(self.agent_du_service).count(), 1)
        self.assertEqual(self._notifications(self.agent_exterieur).count(), 1)

    def test_l_auteur_ne_s_avertit_pas_lui_meme(self):
        self._deposer(pour_tous="on")

        self.assertEqual(self._notifications(self.secretaire).count(), 0)

    def test_corriger_le_titre_ne_renotifie_personne(self):
        self._deposer(destinataires=[self.agent_exterieur.pk])
        document = Document.objects.get(titre="Note diffusée")

        self.client.post(
            reverse("documents:edit", args=[document.pk]),
            {
                "titre": "Note diffusée (corrigée)",
                "type_document": Document.Type.NOTE,
                "destinataires": [self.agent_exterieur.pk],
                "statut": Document.Status.ACTIF,
            },
        )

        self.assertEqual(self._notifications(self.agent_exterieur).count(), 1)

    def test_un_destinataire_ajoute_apres_coup_est_averti(self):
        self._deposer(destinataires=[self.agent_exterieur.pk])
        document = Document.objects.get(titre="Note diffusée")

        self.client.post(
            reverse("documents:edit", args=[document.pk]),
            {
                "titre": "Note diffusée",
                "type_document": Document.Type.NOTE,
                "destinataires": [self.agent_exterieur.pk, self.agent_du_service.pk],
                "statut": Document.Status.ACTIF,
            },
        )

        self.assertEqual(self._notifications(self.agent_du_service).count(), 1)
        self.assertEqual(self._notifications(self.agent_exterieur).count(), 1)

    def test_ouvrir_la_liste_solde_le_compteur(self):
        self._deposer(destinataires=[self.agent_exterieur.pk])
        self.client.logout()

        self.client.login(username="agent_hors", password="StrongPass123!")
        self.assertEqual(self._notifications(self.agent_exterieur).filter(lu=False).count(), 1)
        self.client.get(reverse("documents:list"))

        self.assertEqual(self._notifications(self.agent_exterieur).filter(lu=False).count(), 0)

    def test_le_badge_du_menu_compte_les_documents_non_lus(self):
        self._deposer(destinataires=[self.agent_exterieur.pk])
        self.client.logout()

        self.client.login(username="agent_hors", password="StrongPass123!")
        reponse = self.client.get(reverse("dashboard:home"))

        self.assertEqual(reponse.context["nouveaux_documents_count"], 1)

    def test_un_document_sans_destinataire_n_avertit_personne(self):
        self._deposer()

        self.assertEqual(
            Notification.objects.filter(type_notification=Notification.Type.DOCUMENT).count(),
            0,
        )
