from django import forms
from django.contrib.auth.models import User

from accounts.models import Service
from core.forms import AgentModelChoiceField, AgentMultipleChoiceField, StyledFormMixin
from core.permissions import can_assign_to_anyone

from .models import Task


class TaskForm(StyledFormMixin, forms.ModelForm):
    assigne_a = AgentModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Assigné à",
        empty_label="Sélectionner un agent",
    )
    partage_avec = AgentMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Partager avec",
        help_text="Ces agents pourront consulter et faire avancer la tâche.",
    )
    date_limite = forms.DateField(
        label="Date limite",
        required=False,
        widget=forms.DateInput(format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
    )

    class Meta:
        model = Task
        fields = (
            "titre",
            "description",
            "service_concerne",
            "assigne_a",
            "partage_avec",
            "priorite",
            "statut",
            "date_limite",
        )
        labels = {
            "titre": "Titre",
            "description": "Description",
            "service_concerne": "Service concerné",
            "priorite": "Priorité",
            "statut": "Statut",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        owns_task = bool(
            user
            and self.instance.pk
            and (
                self.instance.cree_par_id == user.pk
                or self.instance.assigne_a_id == user.pk
            )
        )
        self.fields["service_concerne"].queryset = Service.objects.filter(actif=True).order_by("nom")
        self.fields["assigne_a"].queryset = User.objects.filter(is_active=True).order_by(
            "last_name",
            "first_name",
            "username",
        )
        # Le partage est ouvert a tous : c'est le principe meme d'une tache
        # que l'on confie ou que l'on suit a plusieurs.
        partage_queryset = User.objects.filter(is_active=True, profil__actif=True).order_by(
            "last_name",
            "first_name",
            "username",
        )
        if user and (not self.instance.pk or owns_task):
            partage_queryset = partage_queryset.exclude(pk=user.pk)
        self.fields["partage_avec"].queryset = partage_queryset
        self.fields["partage_avec"].widget.attrs["size"] = 6

        if user and not can_assign_to_anyone(user):
            profile = getattr(user, "profil", None)
            assignee_ids = {user.pk}
            if self.instance.pk and self.instance.assigne_a_id:
                assignee_ids.add(self.instance.assigne_a_id)
            self.fields["assigne_a"].queryset = User.objects.filter(pk__in=assignee_ids).order_by(
                "last_name",
                "first_name",
                "username",
            )

            service_ids = set()
            if profile and profile.service_id:
                service_ids.add(profile.service_id)
            if self.instance.pk and self.instance.service_concerne_id:
                service_ids.add(self.instance.service_concerne_id)
            if service_ids:
                self.fields["service_concerne"].queryset = Service.objects.filter(
                    pk__in=service_ids
                ).order_by("nom")
            else:
                self.fields["service_concerne"].queryset = Service.objects.none()

            if self.instance.pk:
                # Un agent non gestionnaire peut faire avancer une tache
                # partagee sans en modifier l'affectation.
                self.fields["assigne_a"].disabled = True
                self.fields["service_concerne"].disabled = True
                if not owns_task:
                    self.fields["titre"].disabled = True
                    self.fields["description"].disabled = True
                    self.fields["partage_avec"].disabled = True
                    self.fields["priorite"].disabled = True
                    self.fields["date_limite"].disabled = True
