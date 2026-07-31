from django.contrib import admin

from .models import Service, UserProfile


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("nom", "est_service_courrier", "responsable", "actif")
    list_filter = ("est_service_courrier", "actif")
    search_fields = ("nom", "description", "responsable__username")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "service", "fonction", "role", "actif")
    list_filter = ("role", "service", "actif")
    search_fields = (
        "utilisateur__username",
        "utilisateur__first_name",
        "utilisateur__last_name",
        "fonction",
    )
    autocomplete_fields = ("utilisateur", "service")

# Register your models here.
