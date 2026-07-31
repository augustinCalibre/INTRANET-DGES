from django.urls import path

from .views import document_create, document_delete, document_download, document_edit, document_list

app_name = "documents"

urlpatterns = [
    path("", document_list, name="list"),
    path("courriers/", document_list, name="courriers"),
    path("add/", document_create, name="create"),
    path("<int:pk>/download/", document_download, name="download"),
    path("<int:pk>/edit/", document_edit, name="edit"),
    path("<int:pk>/delete/", document_delete, name="delete"),
]
