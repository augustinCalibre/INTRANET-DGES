from pathlib import Path

from django import forms
from django.utils import timezone

from core.forms import StyledFormMixin

from .models import Bordereau, Organisme, Trimestre, trimestre_de
from .selectors import get_organismes

# Le selecteur de dates renvoie toujours AAAA-MM-JJ ; la saisie au clavier
# reste possible au format francais.
FORMATS_DATE = ["%Y-%m-%d", "%d/%m/%Y"]

# Le bordereau arrive tel qu'il circule : un PDF, un document Word, ou la
# photographie de la piece papier. Aucun autre format n'est accepte — et
# notamment aucun format que le navigateur interpreterait lui-meme.
EXTENSIONS_FICHIER = (".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png")
MAX_TAILLE_FICHIER = 10 * 1024 * 1024


def champ_date(label, requis=True, aide=""):
    return forms.DateField(
        label=label,
        required=requis,
        help_text=aide,
        widget=forms.DateInput(format="%Y-%m-%d"),
        input_formats=FORMATS_DATE,
    )


class OrganismeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Organisme
        fields = ("nom", "sigle", "actif")
        labels = {
            "nom": "Nom de l'organisme",
            "sigle": "Sigle",
            "actif": "Organisme suivi",
        }
        help_texts = {
            "sigle": "Affiché dans le tableau de suivi. Par exemple UFHB.",
            "actif": "Décochez pour retirer l'organisme du tableau sans effacer son historique.",
        }

    def clean_nom(self):
        nom = (self.cleaned_data.get("nom") or "").strip()
        doublons = Organisme.objects.filter(nom__iexact=nom)
        if self.instance.pk:
            doublons = doublons.exclude(pk=self.instance.pk)
        if doublons.exists():
            raise forms.ValidationError("Un organisme porte déjà ce nom.")
        return nom

    def clean_sigle(self):
        # La casse est laissee telle que saisie. La forcer en majuscules
        # abimerait les sigles qui n'en sont pas vraiment — « UJLoG » porte sa
        # casse, et « Prise en charge » deviendrait un cri.
        return (self.cleaned_data.get("sigle") or "").strip()


class BordereauForm(StyledFormMixin, forms.ModelForm):
    date_reception = champ_date("Date de réception")
    date_engagement = champ_date(
        "Signature de l'engagement",
        requis=False,
        aide="Laisser vide tant que l'engagement n'est pas signé.",
    )
    date_liquidation = champ_date(
        "Signature de la liquidation",
        requis=False,
        aide="Sa saisie clôt le circuit et vaut validation du mandat.",
    )

    class Meta:
        model = Bordereau
        fields = (
            "organisme",
            "annee",
            "trimestre",
            "numero",
            "date_reception",
            "fichier",
            "date_engagement",
            "date_liquidation",
            "observation",
        )
        labels = {
            "numero": "N° de bordereau",
            "annee": "Année",
            "trimestre": "Trimestre",
            "fichier": "Bordereau (PDF, Word ou image)",
            "observation": "Observation",
        }
        help_texts = {
            "numero": "Le numéro porté sur le bordereau. Laisser vide s'il n'est pas encore attribué.",
            "trimestre": "Trimestre de rattachement du dossier.",
            "fichier": "Le bordereau scanné ou photographié. Il reste consultable depuis sa fiche.",
        }
        widgets = {
            "observation": forms.Textarea(attrs={"rows": 3}),
            "fichier": forms.FileInput(attrs={"accept": ",".join(EXTENSIONS_FICHIER)}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # La liste deroulante montre les sigles : elle se trie sur eux, pas sur
        # les noms complets qu'elle n'affiche pas.
        self.fields["organisme"].queryset = get_organismes()
        self.fields["organisme"].empty_label = "Sélectionner un organisme"
        self.fields["numero"].required = False
        self.fields["numero"].widget.attrs["placeholder"] = "BORD-001 (facultatif)"
        self.fields["annee"].widget.attrs.update({"min": 2000, "max": 2100, "step": 1})

    def clean_numero(self):
        # Le controle de doublon a besoin de l'organisme et de l'annee : il se
        # termine dans clean(), une fois ces deux champs valides.
        return (self.cleaned_data.get("numero") or "").strip()

    def clean_fichier(self):
        fichier = self.cleaned_data.get("fichier")
        # Un champ de fichier inchange rend l'objet deja enregistre : rien a
        # revalider, le fichier a passe ce controle a son depot.
        if not fichier or not hasattr(fichier, "size"):
            return fichier

        extension = Path(fichier.name).suffix.lower()
        if extension not in EXTENSIONS_FICHIER:
            raise forms.ValidationError(
                "Format non pris en charge. Déposez le bordereau en "
                + ", ".join(e.lstrip(".").upper() for e in EXTENSIONS_FICHIER)
                + "."
            )
        if fichier.size > MAX_TAILLE_FICHIER:
            mega = MAX_TAILLE_FICHIER // (1024 * 1024)
            raise forms.ValidationError(
                f"Le fichier dépasse la taille maximale autorisée de {mega} Mo."
            )
        return fichier

    def clean_annee(self):
        annee = self.cleaned_data.get("annee")
        if annee and not 2000 <= annee <= 2100:
            raise forms.ValidationError("Indiquez une année comprise entre 2000 et 2100.")
        return annee

    def clean(self):
        cleaned_data = super().clean()
        organisme = cleaned_data.get("organisme")
        annee = cleaned_data.get("annee")
        numero = cleaned_data.get("numero")
        reception = cleaned_data.get("date_reception")
        engagement = cleaned_data.get("date_engagement")
        liquidation = cleaned_data.get("date_liquidation")
        aujourdhui = timezone.localdate()

        # Un numero vide n'entre pas dans ce controle : plusieurs dossiers
        # peuvent attendre leur numero sans etre des doublons.
        if organisme and annee and numero:
            doublons = Bordereau.objects.filter(
                organisme=organisme,
                annee=annee,
                numero__iexact=numero,
            )
            if self.instance.pk:
                doublons = doublons.exclude(pk=self.instance.pk)
            if doublons.exists():
                self.add_error(
                    "numero",
                    f"{organisme.libelle_court} a déjà un bordereau {numero} en {annee}.",
                )

        # L'engagement est la premiere signature du circuit : une liquidation
        # seule laisserait un dossier termine dont on ignore quand il a commence.
        if liquidation and not engagement:
            self.add_error(
                "date_engagement",
                "La liquidation suppose un engagement signé : renseignez sa date.",
            )

        for champ, valeur, libelle in (
            ("date_reception", reception, "de réception"),
            ("date_engagement", engagement, "de l'engagement"),
            ("date_liquidation", liquidation, "de la liquidation"),
        ):
            if valeur and valeur > aujourdhui:
                self.add_error(champ, f"La date {libelle} ne peut pas être dans le futur.")

        if reception and engagement and engagement < reception:
            self.add_error(
                "date_engagement",
                "L'engagement ne peut pas être signé avant la réception du bordereau.",
            )

        if engagement and liquidation and liquidation < engagement:
            self.add_error(
                "date_liquidation",
                "La liquidation ne peut pas être signée avant l'engagement.",
            )

        return cleaned_data


class SignatureForm(forms.Form):
    """Saisie d'une date de signature depuis la fiche d'un bordereau."""

    date_signature = champ_date("Date de signature")
    commentaire = forms.CharField(
        label="Observation",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_signature"].widget.attrs.update(
            {
                "class": "form-control",
                "data-flatpickr": "date",
                "type": "text",
                "autocomplete": "off",
                "placeholder": "JJ/MM/AAAA",
            }
        )


def initial_bordereau(organisme=None, annee=None, trimestre=None):
    """Valeurs de depart d'une creation, deduites de la boite d'ou l'on vient."""
    aujourdhui = timezone.localdate()
    return {
        "organisme": organisme,
        "annee": annee or aujourdhui.year,
        "trimestre": trimestre or trimestre_de(aujourdhui).value,
        "date_reception": aujourdhui,
    }


TRIMESTRE_CHOICES = Trimestre.choices
