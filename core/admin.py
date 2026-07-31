from django.contrib import admin

from .models import ActivityLog, ConnexionLog, Notification


@admin.register(ConnexionLog)
class ConnexionLogAdmin(admin.ModelAdmin):
    list_display = ("date", "libelle_compte", "resultat", "adresse_ip", "poste")
    list_filter = ("resultat", "date")
    search_fields = ("utilisateur__username", "identifiant_saisi", "adresse_ip")
    ordering = ("-date",)
    readonly_fields = ("utilisateur", "identifiant_saisi", "resultat", "adresse_ip", "poste", "date")

    def has_add_permission(self, request):
        # L'historique se remplit par les signaux d'authentification.
        return False


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("module", "action", "objet", "utilisateur", "date")
    list_filter = ("module", "date")
    search_fields = ("action", "objet", "utilisateur__username")
    ordering = ("-date",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("titre", "type_notification", "utilisateur", "lu", "created_at")
    list_filter = ("type_notification", "lu", "created_at")
    search_fields = ("titre", "message", "utilisateur__username")
    ordering = ("-created_at",)
