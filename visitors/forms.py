from django import forms
from django.contrib.auth.models import User

from accounts.models import Service
from core.forms import AgentModelChoiceField, StyledFormMixin

from .models import Visitor


class VisitorForm(StyledFormMixin, forms.ModelForm):
    agent_visite = AgentModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Agent visité",
        empty_label="Sélectionner un agent",
    )
    heure_entree = forms.DateTimeField(
        label="Heure d'entrée",
        input_formats=[StyledFormMixin.date_time_input_format, "%d/%m/%Y %H:%M"],
        widget=forms.DateTimeInput(format=StyledFormMixin.date_time_input_format),
    )
    heure_sortie = forms.DateTimeField(
        label="Heure de sortie",
        required=False,
        input_formats=[StyledFormMixin.date_time_input_format, "%d/%m/%Y %H:%M"],
        widget=forms.DateTimeInput(format=StyledFormMixin.date_time_input_format),
    )

    class Meta:
        model = Visitor
        fields = (
            "nom_complet",
            "contact",
            "provenance",
            "motif",
            "service_visite",
            "agent_visite",
            "heure_entree",
            "heure_sortie",
            "statut",
        )
        labels = {
            "nom_complet": "Nom complet",
            "contact": "Contact",
            "provenance": "Structure / provenance",
            "motif": "Motif de visite",
            "service_visite": "Service visité",
            "statut": "Statut",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service_visite"].queryset = Service.objects.filter(actif=True).order_by("nom")
        self.fields["agent_visite"].queryset = User.objects.filter(is_active=True).order_by(
            "last_name",
            "first_name",
            "username",
        )
