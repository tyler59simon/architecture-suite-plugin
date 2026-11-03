"""Scores candidate drivers for a trip."""
from google.cloud import pubsub_v1

from dispatch import pricing


class MatchingEngine:
    def match(self, trip):
        fare = pricing.FarePricer().quote(trip)
        return {"trip": trip, "fare": fare}


publisher = pubsub_v1.PublisherClient()
