"""Quotes surge-aware fares."""
from google.cloud import spanner


class FarePricer:
    def quote(self, trip):
        return round(trip.get("distance_km", 0) * 1.4, 2)


database = spanner.Client()
