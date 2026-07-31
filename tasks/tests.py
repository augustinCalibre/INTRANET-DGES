from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.constants import ROLE_AGENT, ROLE_SECRETARIAT
from accounts.models import Service

from .models import Task
from .selectors import can_modify_task, get_visible_tasks


def make_user(username, role=ROLE_AGENT, service=None):
    user = User.objects.create_user(username=username, password="StrongPass123!")
    profile = user.profil
    profile.role = role
    profile.service = service
    profile.actif = True
    profile.save()
    return user


class TaskOverduePropertiesTests(TestCase):
    def test_open_task_with_past_deadline_is_overdue(self):
        task = Task(
            titre="Relance courrier",
            description="Verifier le dossier",
            statut=Task.Status.EN_COURS,
            date_limite=timezone.localdate() - timedelta(days=3),
        )

        self.assertTrue(task.is_overdue)
        self.assertEqual(task.days_overdue, 3)
        self.assertEqual(task.display_status_label, "En retard")
        self.assertEqual(task.overdue_label, "Retard de 3 jours")

    def test_closed_task_with_past_deadline_is_not_overdue(self):
        task = Task(
            titre="Note finalisee",
            description="Archive",
            statut=Task.Status.VALIDE,
            date_limite=timezone.localdate() - timedelta(days=5),
        )

        self.assertFalse(task.is_overdue)
        self.assertEqual(task.days_overdue, 0)
        self.assertEqual(task.display_status_label, task.get_statut_display())


@override_settings(SECURE_SSL_REDIRECT=False)
class TaskSharingTests(TestCase):
    """Chacun gere ses taches et peut les partager avec d'autres agents."""

    def setUp(self):
        self.service = Service.objects.create(nom="Planification", actif=True)
        self.autre_service = Service.objects.create(nom="Archives", actif=True)
        self.proprietaire = make_user("proprietaire", ROLE_AGENT, self.service)
        self.collegue = make_user("collegue", ROLE_AGENT, self.autre_service)
        self.tiers = make_user("tiers", ROLE_AGENT, self.autre_service)
        self.secretaire = make_user("secretaire", ROLE_SECRETARIAT, self.service)

        self.tache = Task.objects.create(
            titre="Compiler le suivi des universités",
            description="Rassembler les fiches de suivi.",
            cree_par=self.proprietaire,
            service_concerne=self.service,
        )

    def test_le_createur_voit_et_modifie_sa_tache(self):
        self.assertIn(self.tache, get_visible_tasks(self.proprietaire))
        self.assertTrue(can_modify_task(self.tache, self.proprietaire))

    def test_un_agent_etranger_ne_voit_pas_la_tache(self):
        self.assertNotIn(self.tache, get_visible_tasks(self.tiers))
        self.assertFalse(can_modify_task(self.tache, self.tiers))

    def test_le_partage_ouvre_la_consultation_et_la_modification(self):
        self.tache.partage_avec.add(self.collegue)

        self.assertIn(self.tache, get_visible_tasks(self.collegue))
        self.assertTrue(can_modify_task(self.tache, self.collegue))
        # Le tiers non partage reste dehors.
        self.assertFalse(can_modify_task(self.tache, self.tiers))

    def test_le_secretariat_garde_la_main_sur_toutes_les_taches(self):
        self.assertTrue(can_modify_task(self.tache, self.secretaire))

    def test_la_vue_de_modification_refuse_un_agent_non_concerne(self):
        self.client.force_login(self.tiers)
        response = self.client.get(reverse("tasks:edit", args=[self.tache.pk]))
        # La tache n'est meme pas visible : 404 avant tout controle de droits.
        self.assertEqual(response.status_code, 404)

    def test_la_vue_de_modification_accepte_un_agent_partage(self):
        self.tache.partage_avec.add(self.collegue)
        self.client.force_login(self.collegue)
        response = self.client.get(reverse("tasks:edit", args=[self.tache.pk]))
        self.assertEqual(response.status_code, 200)

    def test_un_agent_partage_ne_peut_modifier_que_le_statut(self):
        self.tache.assigne_a = self.proprietaire
        self.tache.save(update_fields=["assigne_a"])
        self.tache.partage_avec.add(self.collegue)

        self.client.force_login(self.collegue)
        response = self.client.post(
            reverse("tasks:edit", args=[self.tache.pk]),
            {
                "titre": "Titre pirate",
                "description": "Tentative de detournement",
                "service_concerne": self.autre_service.pk,
                "assigne_a": self.tiers.pk,
                "partage_avec": [self.tiers.pk],
                "priorite": Task.Priority.URGENTE,
                "statut": Task.Status.EN_COURS,
                "date_limite": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.tache.refresh_from_db()
        self.assertEqual(self.tache.titre, "Compiler le suivi des universités")
        self.assertEqual(self.tache.description, "Rassembler les fiches de suivi.")
        self.assertEqual(self.tache.service_concerne, self.service)
        self.assertEqual(self.tache.assigne_a, self.proprietaire)
        self.assertEqual(self.tache.priorite, Task.Priority.NORMALE)
        self.assertEqual(self.tache.statut, Task.Status.EN_COURS)
        self.assertIn(self.collegue, self.tache.partage_avec.all())
        self.assertNotIn(self.tiers, self.tache.partage_avec.all())

    def test_un_collegue_de_service_sans_partage_ne_modifie_pas(self):
        """La visibilite par service n'accorde pas le droit de modifier."""
        collegue_service = make_user("collegue_service", ROLE_AGENT, self.service)

        self.assertIn(self.tache, get_visible_tasks(collegue_service))
        self.assertFalse(can_modify_task(self.tache, collegue_service))

        self.client.force_login(collegue_service)
        response = self.client.get(reverse("tasks:edit", args=[self.tache.pk]))
        self.assertEqual(response.status_code, 403)

    def test_le_partage_est_enregistre_a_la_creation(self):
        self.client.force_login(self.proprietaire)
        response = self.client.post(
            reverse("tasks:create"),
            {
                "titre": "Préparer la revue mensuelle",
                "description": "Collecter les indicateurs.",
                "service_concerne": self.service.pk,
                "assigne_a": self.proprietaire.pk,
                "partage_avec": [self.collegue.pk],
                "priorite": Task.Priority.NORMALE,
                "statut": Task.Status.NOUVEAU,
                "date_limite": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        tache = Task.objects.get(titre="Préparer la revue mensuelle")
        self.assertIn(self.collegue, tache.partage_avec.all())

    def test_le_partage_label_liste_les_agents(self):
        self.tache.partage_avec.add(self.collegue)
        self.assertIn("collegue", self.tache.partage_label)

    def test_on_ne_se_partage_pas_une_tache_a_soi_meme(self):
        from .forms import TaskForm

        form = TaskForm(user=self.proprietaire)
        self.assertNotIn(self.proprietaire, form.fields["partage_avec"].queryset)
