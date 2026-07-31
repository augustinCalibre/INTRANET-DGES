from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User

from core.forms import StyledFormMixin

from .models import Service, UserProfile


class MotDePasseChangeForm(StyledFormMixin, PasswordChangeForm):
    """Formulaire de changement de mot de passe, habillé comme les autres."""

    old_password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Confirmer le nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )


class ConnexionForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(label="Nom d'utilisateur")
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)


class AgentUserCreationForm(StyledFormMixin, UserCreationForm):
    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Email", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Identifiant",
        }


class AgentUserUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Identifiant",
            "first_name": "Prénom",
            "last_name": "Nom",
            "email": "Email",
        }


class ServiceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Service
        fields = ("nom", "description", "responsable", "est_service_courrier", "actif")
        labels = {
            "nom": "Nom du service",
            "description": "Description",
            "responsable": "Responsable",
            "est_service_courrier": "Service chargé du courrier",
            "actif": "Service actif",
        }
        help_texts = {
            "actif": "Un service inactif reste dans l'historique mais n'est plus proposé.",
            "est_service_courrier": (
                "Repère organisationnel. Les droits sur le courrier viennent du rôle "
                "des agents, pas de cette case."
            ),
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsable"].queryset = User.objects.filter(is_active=True).order_by(
            "last_name",
            "first_name",
            "username",
        )
        self.fields["responsable"].required = False

    def clean_nom(self):
        nom = (self.cleaned_data.get("nom") or "").strip()
        doublons = Service.objects.filter(nom__iexact=nom)
        if self.instance.pk:
            doublons = doublons.exclude(pk=self.instance.pk)
        if doublons.exists():
            raise forms.ValidationError("Un service porte déjà ce nom.")
        return nom


class UserProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("service", "fonction", "role", "telephone", "actif")
        labels = {
            "service": "Service",
            "fonction": "Fonction",
            "role": "Rôle",
            "telephone": "Téléphone",
            "actif": "Compte actif",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.filter(actif=True).order_by("nom")
