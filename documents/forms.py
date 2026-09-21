from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth.models import User

from accounts.models import Service
from core.forms import AgentMultipleChoiceField, StyledFormMixin
from core.permissions import can_assign_to_anyone, can_manage_courriers

from .models import Document


class DocumentForm(StyledFormMixin, forms.ModelForm):
    destinataires = AgentMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Agents destinataires",
        help_text=(
            "En plus du service, des agents nommément. Maintenez Ctrl "
            "(ou Cmd) pour en choisir plusieurs."
        ),
    )

    class Meta:
        model = Document
        fields = (
            "titre",
            "type_document",
            "fichier",
            "service_concerne",
            "destinataires",
            "pour_tous",
            "statut",
            "est_archive",
        )
        labels = {
            "titre": "Titre",
            "type_document": "Type de document",
            "fichier": "Fichier",
            "service_concerne": "Service concerné",
            "pour_tous": "Tous les agents de la DGES",
            "statut": "Statut",
            "est_archive": "Archivé",
        }
        help_texts = {
            "service_concerne": "Tous les agents de ce service recevront le document.",
        }
        widgets = {
            "fichier": forms.FileInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service_concerne"].queryset = Service.objects.filter(actif=True).order_by("nom")
        self.fields["destinataires"].queryset = User.objects.filter(
            is_active=True,
            profil__actif=True,
        ).order_by("last_name", "first_name", "username")
        # Un agent depose pour son propre service ; le secretariat et le
        # service courrier choisissent librement le service destinataire.
        if user and not can_assign_to_anyone(user) and not can_manage_courriers(user):
            profile = getattr(user, "profil", None)
            if profile and profile.service_id:
                self.fields["service_concerne"].queryset = Service.objects.filter(pk=profile.service_id)

    def clean(self):
        cleaned_data = super().clean()
        # « Tous les agents » absorbe les autres destinations : les conserver
        # laisserait croire, sur la fiche, a une diffusion restreinte.
        if cleaned_data.get("pour_tous"):
            cleaned_data["destinataires"] = User.objects.none()
            cleaned_data["service_concerne"] = None
        return cleaned_data

    def clean_fichier(self):
        uploaded_file = self.cleaned_data.get("fichier")
        if not uploaded_file:
            return uploaded_file

        allowed_extensions = {
            extension.lower()
            for extension in getattr(settings, "DOCUMENT_ALLOWED_EXTENSIONS", [])
        }
        extension = Path(uploaded_file.name).suffix.lower().lstrip(".")

        if allowed_extensions and extension not in allowed_extensions:
            allowed_list = ", ".join(sorted(allowed_extensions))
            raise forms.ValidationError(
                f"Type de fichier non autorise. Formats acceptes : {allowed_list}."
            )

        max_upload_size = getattr(settings, "DOCUMENT_MAX_UPLOAD_SIZE", 0)
        if max_upload_size and uploaded_file.size > max_upload_size:
            max_size_mb = max_upload_size // (1024 * 1024)
            raise forms.ValidationError(
                f"Le fichier depasse la taille maximale autorisee de {max_size_mb} Mo."
            )

        return uploaded_file
