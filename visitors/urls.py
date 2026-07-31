from django.urls import path

from .views import visitor_checkout, visitor_create, visitor_delete, visitor_edit, visitor_list

app_name = "visitors"

urlpatterns = [
    path("", visitor_list, name="list"),
    path("add/", visitor_create, name="create"),
    path("<int:pk>/edit/", visitor_edit, name="edit"),
    path("<int:pk>/delete/", visitor_delete, name="delete"),
    path("<int:pk>/checkout/", visitor_checkout, name="checkout"),
]
