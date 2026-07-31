from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import Service
from core.forms import StyledFormMixin

from .models import Meeting, Salle
from .services import find_room_conflicts, format_meeting_datetime


class SalleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Salle
        fields = ("nom", "localisation", "capacite", "equipements", "actif")
        labels = {
            "nom": "Nom de la salle",
            "localisation": "Localisation",
            "capacite": "Capacité",
            "equipements": "Équipements",
            "actif": "Salle disponible",
        }
        help_texts = {
            "capacite": "Nombre de places assises. Laisser à 0 si l'information n'est pas connue.",
        }

    def clean_nom(self):
        nom = (self.cleaned_data.get("nom") or "").strip()
        doublons = Salle.objects.filter(nom__iexact=nom)
        if self.instance.pk:
            doublons = doublons.exclude(pk=self.instance.pk)
        if doublons.exists():
            raise forms.ValidationError("Une salle porte déjà ce nom.")
        return nom


class AgentMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        full_name = obj.get_full_name().strip()
        return full_name or obj.username


class MeetingForm(StyledFormMixin, forms.ModelForm):
    date_heure = forms.DateTimeField(
        label="Date et heure",
        widget=forms.DateTimeInput(format=StyledFormMixin.date_time_input_format),
        input_formats=[StyledFormMixin.date_time_input_format],
    )
    services_concernes = forms.ModelMultipleChoiceField(
        queryset=Service.objects.none(),
        required=False,
        label="Services concernes",
    )
    membres_invites = AgentMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Agents invites",
    )
    description = forms.CharField(
        label="Objet / ordre du jour",
        required=False,
        widget=forms.Textarea,
    )

    salle_reservee = forms.ModelChoiceField(
        queryset=Salle.objects.none(),
        label="Salle",
        empty_label="Sélectionner une salle",
    )
    duree_minutes = forms.IntegerField(
        label="Durée (minutes)",
        min_value=15,
        max_value=Meeting.DUREE_MAX_MINUTES,
        initial=60,
        help_text="Sert à détecter les conflits d'occupation de la salle.",
    )

    class Meta:
        model = Meeting
        fields = (
            "titre",
            "description",
            "date_heure",
            "duree_minutes",
            "salle_reservee",
            "services_concernes",
            "membres_invites",
            "statut",
        )
        labels = {
            "titre": "Titre de la reunion",
            "statut": "Statut",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["salle_reservee"].queryset = Salle.objects.filter(actif=True).order_by("nom")
        self.fields["services_concernes"].queryset = Service.objects.filter(actif=True).order_by("nom")
        self.fields["membres_invites"].queryset = User.objects.filter(
            is_active=True,
            profil__actif=True,
        ).select_related("profil", "profil__service").order_by("first_name", "last_name", "username")

        self.fields["services_concernes"].widget.attrs["size"] = 6
        self.fields["membres_invites"].widget.attrs["size"] = 8

    def clean(self):
        cleaned_data = super().clean()
        date_heure = cleaned_data.get("date_heure")
        statut = cleaned_data.get("statut")
        services = cleaned_data.get("services_concernes")
        membres = cleaned_data.get("membres_invites")

        if not services and not membres:
            raise forms.ValidationError("Selectionnez au moins un agent invite ou un service concerne.")

        if (
            date_heure
            and date_heure < timezone.now()
            and statut in {Meeting.Status.BROUILLON, Meeting.Status.VALIDEE, Meeting.Status.REPORTEE}
        ):
            self.add_error("date_heure", "La date de reunion doit etre dans le futur pour une reunion active.")

        if date_heure and date_heure > timezone.now() and statut == Meeting.Status.TENUE:
            self.add_error("statut", "Une reunion future ne peut pas encore etre marquee comme tenue.")

        # Conflit d'occupation : on refuse la reservation en nommant la reunion
        # qui tient deja le creneau, pour que l'utilisateur sache quoi faire.
        salle = cleaned_data.get("salle_reservee")
        duree = cleaned_data.get("duree_minutes") or 60
        if salle and date_heure and statut in Meeting.OCCUPYING_STATUSES:
            conflits = find_room_conflicts(
                salle,
                date_heure,
                duree,
                exclude_pk=self.instance.pk if self.instance.pk else None,
            )
            if conflits:
                details = ", ".join(
                    f"« {reunion.titre} » de {format_meeting_datetime(reunion.date_heure)} "
                    f"à {timezone.localtime(reunion.date_fin).strftime('%H:%M')}"
                    for reunion in conflits[:3]
                )
                self.add_error(
                    "salle_reservee",
                    f"La salle {salle.nom} est déjà occupée sur ce créneau : {details}.",
                )

        return cleaned_data
