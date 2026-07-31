from django.urls import path

from .views import (
    meeting_calendar,
    meeting_create,
    meeting_delete,
    meeting_edit,
    meeting_list,
    meeting_status_update,
    salle_create,
    salle_delete,
    salle_edit,
    salle_list,
)

app_name = "meetings"

urlpatterns = [
    path("", meeting_list, name="list"),
    path("calendar/", meeting_calendar, name="calendar"),
    path("add/", meeting_create, name="create"),
    path("salles/", salle_list, name="salle_list"),
    path("salles/nouvelle/", salle_create, name="salle_create"),
    path("salles/<int:pk>/modifier/", salle_edit, name="salle_edit"),
    path("salles/<int:pk>/supprimer/", salle_delete, name="salle_delete"),
    path("<int:pk>/edit/", meeting_edit, name="edit"),
    path("<int:pk>/delete/", meeting_delete, name="delete"),
    path("<int:pk>/status/<str:status>/", meeting_status_update, name="status"),
]
