from django.contrib import admin

from .models import Bordereau, BordereauHistory, Organisme


@admin.register(Organisme)
class OrganismeAdmin(admin.ModelAdmin):
    list_display = ("nom", "sigle", "actif", "display_nb_bordereaux")
    list_filter = ("actif",)
    search_fields = ("nom", "sigle")
    ordering = ("nom",)

    @admin.display(description="Bordereaux")
    def display_nb_bordereaux(self, obj):
        return obj.bordereaux.count()


@admin.register(Bordereau)
class BordereauAdmin(admin.ModelAdmin):
    list_display = (
        "display_libelle",
        "organisme",
        "annee",
        "trimestre",
        "date_reception",
        "date_engagement",
        "date_liquidation",
        "display_etat",
        "display_piece",
    )
    list_filter = ("annee", "trimestre", "organisme")
    search_fields = ("numero", "organisme__nom", "organisme__sigle", "observation")
    autocomplete_fields = ("organisme", "cree_par")
    ordering = ("-annee", "trimestre", "numero")

    # Un bordereau sans numero laisserait une premiere colonne vide, donc un
    # lien de modification invisible : on affiche sa designation de repli.
    @admin.display(description="N° de bordereau", ordering="numero")
    def display_libelle(self, obj):
        return obj.libelle

    @admin.display(description="État")
    def display_etat(self, obj):
        return obj.etat_label

    @admin.display(description="Pièce", boolean=True)
    def display_piece(self, obj):
        return bool(obj.fichier)


@admin.register(BordereauHistory)
class BordereauHistoryAdmin(admin.ModelAdmin):
    list_display = ("bordereau", "action", "ancien_etat", "nouvel_etat", "utilisateur", "date")
    list_filter = ("nouvel_etat", "date")
    search_fields = ("bordereau__numero", "action", "commentaire")
    ordering = ("-date",)
