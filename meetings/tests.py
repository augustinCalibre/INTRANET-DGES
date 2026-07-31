from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.constants import ROLE_SECRETARIAT, ROLE_SECRETARIAT_ADJOINT
from accounts.models import Service
from core.models import Notification
from core.permissions import can_manage_meetings

from .forms import MeetingForm
from .models import Meeting, Salle
from .selectors import get_visible_meetings
from .services import (
    create_meeting_notifications,
    dispatch_due_meeting_reminders,
    find_room_conflicts,
    get_room_occupancy,
)
from .views import can_modify_meeting

@override_settings(SECURE_SSL_REDIRECT=False)
class MeetingNotificationTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Personnel")
        self.organizer = User.objects.create_user(username="secretariat", password="pass")
        self.organizer.profil.role = ROLE_SECRETARIAT
        self.organizer.profil.save()

        self.invited = User.objects.create_user(username="agent1", password="pass", first_name="Agent", last_name="Un")
        self.invited.profil.service = self.service
        self.invited.profil.save()

        self.salle = Salle.objects.create(nom="Salle A", capacite=12)
        self.meeting = Meeting.objects.create(
            titre="Preparation de reunion hebdomadaire",
            date_heure=timezone.now() + timedelta(days=1),
            salle_reservee=self.salle,
            statut=Meeting.Status.VALIDEE,
            organisee_par=self.organizer,
            validee_par=self.organizer,
        )
        self.meeting.services_concernes.add(self.service)

    def test_create_meeting_notifications_for_concerned_users(self):
        create_meeting_notifications(self.meeting)

        self.assertEqual(Notification.objects.filter(utilisateur=self.invited).count(), 1)
        notification = Notification.objects.get(utilisateur=self.invited)
        self.assertIn("reunion", notification.titre.lower())

    def test_visible_meetings_for_service_member(self):
        meetings = get_visible_meetings(self.invited)
        self.assertEqual(meetings.count(), 1)

    def test_la_fonction_saisie_librement_ne_donne_aucun_droit(self):
        """Le droit vient du role, jamais du libelle de la fonction.

        Auparavant toute fonction contenant « personnel » ou « rh » ouvrait la
        gestion des reunions de toute la direction : une faute de frappe
        retirait le droit, et « Gestion du personnel enseignant » l'accordait.
        """
        agent = User.objects.create_user(username="personnel", password="pass")
        agent.profil.fonction = "Chargé du personnel"
        agent.profil.save()

        self.assertFalse(can_manage_meetings(agent))

    def test_le_secretariat_gere_le_planning(self):
        self.assertTrue(can_manage_meetings(self.organizer))

    def test_le_secretariat_adjoint_gere_aussi_le_planning(self):
        adjoint = User.objects.create_user(username="adjoint", password="pass")
        adjoint.profil.role = ROLE_SECRETARIAT_ADJOINT
        adjoint.profil.save()

        self.assertTrue(can_manage_meetings(adjoint))

    def test_dispatch_due_meeting_reminders_sends_single_notification(self):
        self.meeting.date_heure = timezone.now() + timedelta(minutes=10)
        self.meeting.save(update_fields=["date_heure"])
        Notification.objects.all().delete()

        dispatch_due_meeting_reminders()
        dispatch_due_meeting_reminders()

        self.meeting.refresh_from_db()
        self.assertIsNotNone(self.meeting.rappel_15_envoye_at)
        self.assertEqual(Notification.objects.filter(utilisateur=self.invited).count(), 1)

    def test_calendar_view_is_accessible(self):
        client = Client()
        client.force_login(self.organizer)

        response = client.get(reverse("meetings:calendar"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calendrier mensuel")

    def test_meeting_status_update_marks_meeting_as_held(self):
        self.meeting.date_heure = timezone.now() - timedelta(minutes=5)
        self.meeting.save(update_fields=["date_heure"])
        client = Client()
        client.force_login(self.organizer)

        response = client.post(
            reverse("meetings:status", args=[self.meeting.pk, Meeting.Status.TENUE]),
            {"next": reverse("meetings:list")},
        )

        self.assertEqual(response.status_code, 302)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.statut, Meeting.Status.TENUE)


@override_settings(SECURE_SSL_REDIRECT=False)
class SalleOccupationTests(TestCase):
    """Une salle ne peut pas etre retenue deux fois sur le meme creneau."""

    def setUp(self):
        self.salle = Salle.objects.create(nom="Salle du Conseil", capacite=20)
        self.autre_salle = Salle.objects.create(nom="Bureau du secretariat", capacite=6)
        self.organisateur = User.objects.create_user(username="organisateur", password="pass")
        self.debut = timezone.now() + timedelta(days=1)

        self.existante = Meeting.objects.create(
            titre="Comité de direction",
            date_heure=self.debut,
            duree_minutes=90,
            salle_reservee=self.salle,
            statut=Meeting.Status.VALIDEE,
            organisee_par=self.organisateur,
        )

    def test_la_fin_est_deduite_de_la_duree(self):
        self.assertEqual(self.existante.date_fin, self.debut + timedelta(minutes=90))
        self.assertEqual(self.existante.duree_label, "1 h 30")

    def test_un_creneau_qui_chevauche_est_detecte(self):
        conflits = find_room_conflicts(self.salle, self.debut + timedelta(minutes=30), 60)
        self.assertEqual(conflits, [self.existante])

    def test_un_creneau_qui_englobe_est_detecte(self):
        conflits = find_room_conflicts(self.salle, self.debut - timedelta(minutes=30), 240)
        self.assertEqual(conflits, [self.existante])

    def test_un_creneau_qui_suit_immediatement_est_libre(self):
        conflits = find_room_conflicts(self.salle, self.debut + timedelta(minutes=90), 60)
        self.assertEqual(conflits, [])

    def test_un_creneau_qui_precede_est_libre(self):
        conflits = find_room_conflicts(self.salle, self.debut - timedelta(minutes=60), 60)
        self.assertEqual(conflits, [])

    def test_une_autre_salle_reste_libre(self):
        conflits = find_room_conflicts(self.autre_salle, self.debut, 90)
        self.assertEqual(conflits, [])

    def test_une_reunion_annulee_libere_la_salle(self):
        self.existante.statut = Meeting.Status.ANNULEE
        self.existante.save(update_fields=["statut"])

        self.assertEqual(find_room_conflicts(self.salle, self.debut, 90), [])

    def test_une_reunion_tenue_libere_la_salle(self):
        self.existante.statut = Meeting.Status.TENUE
        self.existante.save(update_fields=["statut"])

        self.assertEqual(find_room_conflicts(self.salle, self.debut, 90), [])

    def test_la_reunion_ne_se_bloque_pas_elle_meme(self):
        conflits = find_room_conflicts(self.salle, self.debut, 90, exclude_pk=self.existante.pk)
        self.assertEqual(conflits, [])

    def test_le_formulaire_refuse_un_creneau_occupe(self):
        form = MeetingForm(
            data={
                "titre": "Réunion concurrente",
                "description": "",
                "date_heure": timezone.localtime(self.debut + timedelta(minutes=15)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "duree_minutes": 60,
                "salle_reservee": self.salle.pk,
                "membres_invites": [self.organisateur.pk],
                "statut": Meeting.Status.VALIDEE,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("salle_reservee", form.errors)
        self.assertIn("déjà occupée", form.errors["salle_reservee"][0])

    def test_le_formulaire_accepte_un_creneau_libre(self):
        form = MeetingForm(
            data={
                "titre": "Réunion suivante",
                "description": "",
                "date_heure": timezone.localtime(self.debut + timedelta(hours=3)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "duree_minutes": 60,
                "salle_reservee": self.salle.pk,
                "membres_invites": [self.organisateur.pk],
                "statut": Meeting.Status.VALIDEE,
            }
        )
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_l_etat_d_occupation_est_calcule(self):
        en_cours = Meeting.objects.create(
            titre="Réunion en cours",
            date_heure=timezone.now() - timedelta(minutes=15),
            duree_minutes=60,
            salle_reservee=self.autre_salle,
            statut=Meeting.Status.VALIDEE,
            organisee_par=self.organisateur,
        )

        etat = get_room_occupancy(self.autre_salle)
        self.assertTrue(etat["occupee"])
        self.assertEqual(etat["reunion_en_cours"], en_cours)

        etat_libre = get_room_occupancy(self.salle)
        self.assertFalse(etat_libre["occupee"])
        self.assertEqual(etat_libre["prochaine_reunion"], self.existante)


@override_settings(SECURE_SSL_REDIRECT=False)
class MeetingOwnershipTests(TestCase):
    """Chacun organise ses reunions ; le secretariat gere celles de tous."""

    def setUp(self):
        self.salle = Salle.objects.create(nom="Salle B")
        self.agent = User.objects.create_user(username="agent_libre", password="pass")
        self.autre_agent = User.objects.create_user(username="autre_agent", password="pass")
        self.secretaire = User.objects.create_user(username="secretaire_reunion", password="pass")
        self.secretaire.profil.role = ROLE_SECRETARIAT
        self.secretaire.profil.save()

        self.reunion = Meeting.objects.create(
            titre="Point d'équipe",
            date_heure=timezone.now() + timedelta(days=2),
            salle_reservee=self.salle,
            statut=Meeting.Status.VALIDEE,
            organisee_par=self.agent,
        )
        self.reunion.membres_invites.add(self.agent, self.autre_agent)

    def test_tout_agent_peut_ouvrir_le_formulaire_de_creation(self):
        client = Client()
        client.force_login(self.agent)
        self.assertEqual(client.get(reverse("meetings:create")).status_code, 200)

    def test_l_organisateur_modifie_sa_reunion(self):
        self.assertTrue(can_modify_meeting(self.reunion, self.agent))

    def test_un_invite_ne_modifie_pas_la_reunion_d_un_autre(self):
        self.assertFalse(can_modify_meeting(self.reunion, self.autre_agent))

        client = Client()
        client.force_login(self.autre_agent)
        response = client.get(reverse("meetings:edit", args=[self.reunion.pk]))
        self.assertEqual(response.status_code, 403)

    def test_le_secretariat_modifie_les_reunions_de_tous(self):
        self.assertTrue(can_modify_meeting(self.reunion, self.secretaire))

    def test_seul_le_secretariat_gere_les_salles(self):
        client = Client()
        client.force_login(self.agent)
        self.assertEqual(client.get(reverse("meetings:salle_create")).status_code, 403)

        client.force_login(self.secretaire)
        self.assertEqual(client.get(reverse("meetings:salle_create")).status_code, 200)

    def test_l_etat_des_salles_est_consultable_par_tous(self):
        client = Client()
        client.force_login(self.agent)
        response = client.get(reverse("meetings:salle_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salle B")
