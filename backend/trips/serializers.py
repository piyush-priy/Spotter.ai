"""
Serializers for Trip Route Analysis request and response payloads.
Validates input constraints per SRS Functional Requirements FR-001 - FR-008.
"""
from datetime import datetime
from rest_framework import serializers


class LocationInputSerializer(serializers.Serializer):
    query = serializers.CharField(required=False, allow_blank=False, max_length=255)
    latitude = serializers.FloatField(required=False, min_value=-90.0, max_value=90.0)
    longitude = serializers.FloatField(required=False, min_value=-180.0, max_value=180.0)

    def validate(self, data):
        has_query = bool(data.get("query"))
        has_coords = ("latitude" in data and "longitude" in data)
        if not has_query and not has_coords:
            raise serializers.ValidationError(
                "Either 'query' (e.g. city name) or both 'latitude' and 'longitude' must be provided."
            )
        return data


class RouteAnalysisRequestSerializer(serializers.Serializer):
    origin = LocationInputSerializer(required=True)
    destination = LocationInputSerializer(required=True)
    departure_at = serializers.DateTimeField(required=True)
    load_weight_lb = serializers.FloatField(
        required=True,
        min_value=0.0,
        error_messages={
            "min_value": "Load weight cannot be negative.",
        }
    )
    checkpoint_spacing_miles = serializers.ChoiceField(
        choices=[10, 25, 50],
        default=25,
        required=False
    )

    def validate_departure_at(self, value: datetime) -> datetime:
        # Check if departure is in timezone-aware format or convert
        if value.tzinfo is None:
            raise serializers.ValidationError(
                "Departure date/time must include an explicit timezone offset (e.g. ISO 8601 with +HH:MM or Z)."
            )
        return value

