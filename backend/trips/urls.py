"""Trips app URL patterns."""
from django.urls import path
from .views import HealthView, RouteAnalysisView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("health", HealthView.as_view(), name="health-noslash"),
    path("trips/route-analysis", RouteAnalysisView.as_view(), name="route-analysis"),
    path("trips/route-analysis/", RouteAnalysisView.as_view(), name="route-analysis-slash"),
]

