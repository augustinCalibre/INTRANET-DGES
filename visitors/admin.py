from django.contrib import admin

from .models import Visitor


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = (
        "nom_complet",
        "service_visite",
        "agent_visite",
        "statut",
        "heure_entree",
        "heure_sortie",
    )
    list_filter = ("statut", "service_visite")
    search_fields = ("nom_complet", "contact", "provenance", "motif")
    autocomplete_fields = ("service_visite", "agent_visite", "cree_par")

# Register your models here.
