from django.urls import path

from .views import home, messaging_redirect

app_name = "core"

urlpatterns = [
    path("", home, name="home"),
    path("messagerie/", messaging_redirect, name="messaging"),
]
