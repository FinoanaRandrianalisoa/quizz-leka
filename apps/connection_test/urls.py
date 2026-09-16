from django.urls import path

from . import views

urlpatterns = [
    path("ping/", views.ping, name="connection-test-ping"),
    path("download/", views.download, name="connection-test-download"),
    path("upload/", views.upload, name="connection-test-upload"),
]
