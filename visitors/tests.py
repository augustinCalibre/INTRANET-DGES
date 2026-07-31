from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.constants import ROLE_SECRETARIAT
from accounts.models import Service

from .models import Visitor

@override_settings(SECURE_SSL_REDIRECT=False)
class VisitorCheckoutSecurityTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Secretariat Test", actif=True)
        self.user = User.objects.create_user(username="secretariat_test", password="StrongPass123!")
        profile = self.user.profil
        profile.role = ROLE_SECRETARIAT
        profile.service = self.service
        profile.actif = True
        profile.save()

        self.visitor = Visitor.objects.create(
            nom_complet="Visiteur securite",
            contact="000000",
            motif="Test",
            service_visite=self.service,
            agent_visite=self.user,
            cree_par=self.user,
        )

    def test_checkout_requires_post(self):
        self.client.login(username="secretariat_test", password="StrongPass123!")

        response = self.client.get(reverse("visitors:checkout", args=[self.visitor.pk]))
        self.visitor.refresh_from_db()

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.visitor.statut, Visitor.Status.PRESENT)
        self.assertIsNone(self.visitor.heure_sortie)

    def test_checkout_post_marks_visitor_as_sorti(self):
        self.client.login(username="secretariat_test", password="StrongPass123!")

        response = self.client.post(
            reverse("visitors:checkout", args=[self.visitor.pk]),
            {"next": reverse("visitors:list")},
        )
        self.visitor.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.visitor.statut, Visitor.Status.SORTI)
        self.assertIsNotNone(self.visitor.heure_sortie)
