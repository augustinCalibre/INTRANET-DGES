from pathlib import Path

from django import forms
from django.contrib.auth.models import User

from accounts.models import Service
from core.forms import AgentModelChoiceField, StyledFormMixin

from .models import Diplome, LotDiplomes
from .services import SUPPORTED_IMPORT_EXTENSIONS

MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024


class LotDiplomesForm(StyledFormMixin, forms.ModelForm):
    agent_receptionnaire = AgentModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Agent réceptionnaire",
        empty_label="Sélectionner un agent",
    )
    date_arrivee = forms.DateField(
        label="Date d'arrivée",
        widget=forms.DateInput(format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
    )

    class Meta:
        model = LotDiplomes
        fields = (
            "reference",
            "etablissement",
            "date_arrivee",
            "nombre_annonce",
            "agent_receptionnaire",
            "service_concerne",
            "observation",
        )
        labels = {
            "reference": "Référence du lot",
            "etablissement": "Établissement d'origine",
            "nombre_annonce": "Nombre de diplômes annoncé",
            "service_concerne": "Service concerné",
            "observation": "Observation",
        }
        help_texts = {
            "reference": "Laisser vide pour une attribution automatique (LOT-DIP-année-numéro).",
            "nombre_annonce": "Nombre déclaré par l'établissement à la remise du lot.",
        }
        widgets = {
            "observation": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service_concerne"].queryset = Service.objects.filter(actif=True).order_by("nom")
        self.fields["agent_receptionnaire"].queryset = User.objects.filter(is_active=True).order_by(
            "last_name",
            "first_name",
            "username",
        )
        self.fields["reference"].required = False
        self.fields["reference"].widget.attrs["placeholder"] = "Automatique"

    def clean_reference(self):
        reference = (self.cleaned_data.get("reference") or "").strip().upper()
        if not reference:
            return ""

        duplicates = LotDiplomes.objects.filter(reference=reference)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Cette référence de lot est déjà utilisée.")
        return reference


class DiplomeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Diplome
        fields = (
            "nom_beneficiaire",
            "numero_diplome",
            "filiere",
            "etablissement",
            "annee_academique",
            "statut",
            "anomalie",
            "observations",
        )
        labels = {
            "nom_beneficiaire": "Nom du bénéficiaire",
            "numero_diplome": "Numéro du diplôme",
            "filiere": "Filière",
            "etablissement": "Établissement",
            "annee_academique": "Année académique",
            "statut": "Statut",
            "anomalie": "Type d'anomalie",
            "observations": "Observations",
        }
        help_texts = {
            "etablissement": "Laisser vide pour reprendre l'établissement du lot.",
            "annee_academique": "Par exemple 2024-2025.",
            "anomalie": "À renseigner uniquement si le diplôme est non conforme.",
        }
        widgets = {
            "observations": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, lot=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lot = lot or getattr(self.instance, "lot", None)
        self.fields["anomalie"].required = False
        if self.lot:
            self.fields["etablissement"].widget.attrs["placeholder"] = self.lot.etablissement

    def clean_numero_diplome(self):
        numero = (self.cleaned_data.get("numero_diplome") or "").strip()
        if not numero or not self.lot:
            return numero

        duplicates = Diplome.objects.filter(lot=self.lot, numero_diplome__iexact=numero)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Ce numéro de diplôme existe déjà dans ce lot.")
        return numero

    def clean(self):
        cleaned_data = super().clean()
        statut = cleaned_data.get("statut")
        anomalie = cleaned_data.get("anomalie")

        if statut == Diplome.Status.NON_CONFORME and not anomalie:
            self.add_error("anomalie", "Précisez le type d'anomalie constatée.")

        # Signaler une anomalie sur un diplome encore a verifier le bascule
        # automatiquement en non conforme : les deux informations restent coherentes.
        if anomalie and statut in {Diplome.Status.A_VERIFIER, Diplome.Status.CONFORME}:
            cleaned_data["statut"] = Diplome.Status.NON_CONFORME

        if statut != Diplome.Status.NON_CONFORME and not anomalie:
            cleaned_data["anomalie"] = ""

        return cleaned_data


class DiplomeImportForm(forms.Form):
    fichier = forms.FileField(
        label="Fichier des diplômes",
        help_text=f"Formats acceptés : {', '.join(SUPPORTED_IMPORT_EXTENSIONS)}. Taille maximale : 5 Mo.",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv,.xlsx"}),
    )

    def clean_fichier(self):
        uploaded_file = self.cleaned_data["fichier"]
        extension = Path(uploaded_file.name).suffix.lower()

        if extension not in SUPPORTED_IMPORT_EXTENSIONS:
            raise forms.ValidationError(
                f"Format non pris en charge. Fournissez un fichier {' ou '.join(SUPPORTED_IMPORT_EXTENSIONS)}."
            )
        if uploaded_file.size > MAX_IMPORT_FILE_SIZE:
            raise forms.ValidationError("Le fichier dépasse la taille maximale autorisée de 5 Mo.")
        return uploaded_file
