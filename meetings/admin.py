from django.contrib import admin

from .models import Salle


@admin.register(Salle)
class SalleAdmin(admin.ModelAdmin):
    list_display = ("nom", "localisation", "capacite", "equipements", "actif")
    list_filter = ("actif",)
    search_fields = ("nom", "localisation", "equipements")
    ordering = ("nom",)

from .models import Meeting


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("titre", "date_heure", "salle_reservee", "statut", "organisee_par", "validee_par")
    list_filter = ("statut", "date_heure", "services_concernes")
    search_fields = ("titre", "description", "salle_reservee__nom")
    filter_horizontal = ("services_concernes", "membres_invites")

