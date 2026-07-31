import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.constants import ROLE_AGENT, ROLE_SECRETARIAT
from accounts.models import Service

from .models import Document

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
