from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth.models import User

from accounts.models import Service
from core.forms import AgentModelChoiceField, StyledFormMixin

from .models import CorrespondantExterne, Courrier, InstructionCourrier
from .services import build_imputation_grid


class FicheAnalyseForm(forms.ModelForm):
    """Partie de la fiche renseignée par le Directeur Général.

    La grille d'imputation est construite à partir des services actifs et de
    leurs agents. Elle est rendue à la main dans le gabarit, colonne par
    colonne comme sur l'imprimé : un rendu automatique perdrait la grille.
    """

    services_imputes = forms.ModelMultipleChoiceField(
        queryset=Service.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Services imputés",
    )
    agents_imputes = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Agents imputés",
    )
    instructions = forms.ModelMultipleChoiceField(
        queryset=InstructionCourrier.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Instructions",
    )
    ouvrir_des_taches = forms.BooleanField(
        required=False,
        label="Ouvrir une tâche de suivi pour chaque imputation",
        help_text=(
            "Chaque agent ou service imputé reçoit une tâche portant l'objet du "
            "courrier et vos instructions."
        ),
    )

    class Meta:
        model = Courrier
        fields = (
            "services_imputes",
            "agents_imputes",
            "instructions",
            "autres_instructions",
            "instruction_dg",
        )
        labels = {
            "autres_instructions": "Autres",
            "instruction_dg": "Observations du Directeur Général",
        }
        widgets = {
            "autres_instructions": forms.Textarea(
                attrs={"rows": 2, "class": "form-control", "placeholder": "Rubrique « AUTRES » de la fiche"}
            ),
            "instruction_dg": forms.Textarea(
                attrs={"rows": 3, "class": "form-control", "placeholder": "Suite à donner, délai, service à saisir…"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["services_imputes"].queryset = Service.objects.filter(actif=True)
        self.fields["agents_imputes"].queryset = User.objects.filter(
            is_active=True, profil__actif=True
        )
        self.fields["instructions"].queryset = InstructionCourrier.objects.filter(actif=True)

    @property
    def grille_imputations(self):
        """Une colonne par service, avec le service puis ses agents."""
        services_coches = set()
        agents_coches = set()
        if self.instance.pk:
            services_coches = set(self.instance.services_imputes.values_list("id", flat=True))
            agents_coches = set(self.instance.agents_imputes.values_list("id", flat=True))

        colonnes = []
        for entree in build_imputation_grid():
            service = entree["service"]
            colonnes.append(
                {
                    "service": service,
                    "service_cochee": service.pk in services_coches,
                    "agents": [
                        {
                            "objet": agent,
                            "nom": agent.get_full_name().strip() or agent.username,
                            "cochee": agent.pk in agents_coches,
                        }
                        for agent in entree["agents"]
                    ],
                }
            )
        return colonnes

    @property
    def instructions_cochables(self):
        selectionnees = (
            {item.pk for item in self.instance.instructions.all()} if self.instance.pk else set()
        )
        return [
            {"objet": instruction, "cochee": instruction.pk in selectionnees}
            for instruction in self.fields["instructions"].queryset
        ]


class CourrierForm(StyledFormMixin, forms.ModelForm):
    receptionne_par = AgentModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Agent réceptionnaire",
        empty_label="Sélectionner un agent",
    )
    date_reception = forms.DateField(
        label="Date de réception",
        widget=forms.DateInput(format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
    )
    date_courrier = forms.DateField(
        label="Date du courrier",
        required=False,
        widget=forms.DateInput(format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
    )
    # Saisie assistee du destinataire d'un courrier sortant.
    #
    # Une zone de texte adossee a la liste des correspondants deja connus,
    # plutot qu'une liste fermee doublee d'un bouton « nouveau » : on tape, on
    # reconnait, on valide. Un nom inedit cree sa fiche sans detour, et
    # `normaliser_nom` empeche « Universite FHB » de cotoyer « Université
    # F.H.B. » dans le repertoire.
    destinataire_externe_nom = forms.CharField(
        label="Destinataire",
        required=False,
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "list": "listeCorrespondants",
                "autocomplete": "off",
                "placeholder": "Université, ministère, établissement…",
            }
        ),
        help_text="Tapez les premières lettres : les destinataires déjà utilisés sont proposés. Un nom nouveau est enregistré automatiquement.",
    )

    class Meta:
        model = Courrier
        fields = (
            "reference",
            "numero_arrivee",
            "sens",
            "nature",
            "objet",
            "expediteur",
            "destinataire_service",
            "service_emetteur",
            "date_reception",
            "date_courrier",
            "priorite",
            "fichier",
            "observation",
        )
        labels = {
            "reference": "Suivi du courrier n°",
            "numero_arrivee": "Courrier arrivée n°",
            "sens": "Sens",
            "nature": "Nature du document",
            "objet": "Objet du courrier",
            "expediteur": "Expéditeur",
            "destinataire_service": "Service destinataire",
            "priorite": "Priorité",
            "fichier": "Pièce numérisée",
            "observation": "Observation",
        }
        help_texts = {
            "reference": "Laisser vide pour une attribution automatique (COUR-année-numéro).",
            "numero_arrivee": "Numéro porté sur la pièce à son arrivée, s'il existe.",
            "nature": "Le sens dit s'il entre ou s'il sort, la nature dit de quel document il s'agit.",
            "expediteur": "Organisme, établissement ou personne à l'origine du courrier.",
        }
        widgets = {
            "observation": forms.Textarea(attrs={"rows": 3}),
            "fichier": forms.FileInput(),
        }

    # Les champs des deux sens se suivent, pour que le formulaire se lise dans
    # l'ordre du geste : d'où vient le courrier, puis où il va.
    field_order = [
        "reference",
        "numero_arrivee",
        "sens",
        "nature",
        "objet",
        "expediteur",
        "destinataire_service",
        "service_emetteur",
        "destinataire_externe_nom",
        "date_reception",
        "date_courrier",
        "priorite",
        "receptionne_par",
        "fichier",
        "observation",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        services_actifs = Service.objects.filter(actif=True).order_by("nom")
        self.fields["destinataire_service"].queryset = services_actifs
        self.fields["service_emetteur"].queryset = services_actifs
        self.fields["receptionne_par"].queryset = User.objects.filter(is_active=True).order_by(
            "last_name",
            "first_name",
            "username",
        )
        self.fields["reference"].required = False
        self.fields["reference"].widget.attrs["placeholder"] = "Automatique"

        # Chaque champ declare le sens auquel il appartient. Le gabarit s'en
        # sert pour n'afficher que les rubriques utiles, et la validation en
        # tire les champs a exiger : une seule source, pas deux listes a
        # tenir accordees.
        for nom_champ, sens in self.CHAMPS_PAR_SENS.items():
            self.fields[nom_champ].widget.attrs["data-sens"] = sens

        if self.instance.pk and self.instance.destinataire_externe:
            self.fields["destinataire_externe_nom"].initial = (
                self.instance.destinataire_externe.nom
            )

    # Champs propres a un sens. Les autres valent pour les deux.
    CHAMPS_PAR_SENS = {
        "expediteur": Courrier.Sens.ENTRANT,
        "destinataire_service": Courrier.Sens.ENTRANT,
        "numero_arrivee": Courrier.Sens.ENTRANT,
        "receptionne_par": Courrier.Sens.ENTRANT,
        "service_emetteur": Courrier.Sens.SORTANT,
        "destinataire_externe_nom": Courrier.Sens.SORTANT,
    }

    @property
    def correspondants_connus(self):
        """Alimente la liste de suggestions du champ destinataire."""
        return CorrespondantExterne.objects.filter(actif=True).values_list("nom", flat=True)

    def clean_reference(self):
        reference = (self.cleaned_data.get("reference") or "").strip().upper()
        if not reference:
            return ""

        doublons = Courrier.objects.filter(reference=reference)
        if self.instance.pk:
            doublons = doublons.exclude(pk=self.instance.pk)
        if doublons.exists():
            raise forms.ValidationError("Cette référence de courrier est déjà utilisée.")
        return reference

    def clean_fichier(self):
        fichier = self.cleaned_data.get("fichier")
        if not fichier:
            return fichier

        extensions = {
            extension.lower()
            for extension in getattr(settings, "DOCUMENT_ALLOWED_EXTENSIONS", [])
        }
        extension = Path(fichier.name).suffix.lower().lstrip(".")
        if extensions and extension not in extensions:
            autorisees = ", ".join(sorted(extensions))
            raise forms.ValidationError(
                f"Type de fichier non autorisé. Formats acceptés : {autorisees}."
            )

        taille_max = getattr(settings, "DOCUMENT_MAX_UPLOAD_SIZE", 0)
        if taille_max and fichier.size > taille_max:
            mega = taille_max // (1024 * 1024)
            raise forms.ValidationError(
                f"Le fichier dépasse la taille maximale autorisée de {mega} Mo."
            )
        return fichier

    def clean(self):
        cleaned_data = super().clean()
        reception = cleaned_data.get("date_reception")
        courrier = cleaned_data.get("date_courrier")
        sens = cleaned_data.get("sens")

        if reception and courrier and courrier > reception:
            self.add_error(
                "date_courrier",
                "La date du courrier ne peut pas être postérieure à sa réception.",
            )

        # Chaque sens exige ses propres rubriques. Un courrier sortant sans
        # destinataire ne peut pas donner de décharge, et un courrier entrant
        # sans expéditeur ne se retrouve pas dans le registre.
        if sens == Courrier.Sens.SORTANT:
            if not cleaned_data.get("service_emetteur"):
                self.add_error(
                    "service_emetteur",
                    "Indiquez le service de la DGES à l'origine de ce courrier.",
                )
            if not (cleaned_data.get("destinataire_externe_nom") or "").strip():
                self.add_error(
                    "destinataire_externe_nom",
                    "Indiquez l'organisme destinataire de ce courrier.",
                )
        elif sens == Courrier.Sens.ENTRANT and not (cleaned_data.get("expediteur") or "").strip():
            self.add_error("expediteur", "Indiquez l'expéditeur de ce courrier.")

        return cleaned_data

    def save(self, commit=True):
        courrier = super().save(commit=False)

        if courrier.sens == Courrier.Sens.SORTANT:
            courrier.destinataire_externe = CorrespondantExterne.obtenir_ou_creer(
                self.cleaned_data.get("destinataire_externe_nom")
            )
            # Les rubriques de l'autre sens sont vidées : les laisser en place
            # après un changement de sens ferait apparaître dans le registre
            # un expéditeur qui n'a jamais rien envoyé.
            courrier.expediteur = ""
            courrier.destinataire_service = None
            courrier.numero_arrivee = ""
            courrier.receptionne_par = None
        else:
            courrier.service_emetteur = None
            courrier.destinataire_externe = None

        if commit:
            courrier.save()
            self.save_m2m()
        return courrier
