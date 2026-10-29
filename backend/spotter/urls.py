"""Spotter URL configuration."""
from django.urls import path, include

urlpatterns = [
    path("api/v1/", include("trips.urls")),
]

