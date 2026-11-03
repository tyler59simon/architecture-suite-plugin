# Fictional RidePulse infrastructure (illustrative; not deployable).
resource "google_container_cluster" "gateway" {
  name     = "ridepulse-gateway"
  location = "us-central1"
}

resource "google_cloud_run_v2_service" "dispatch" {
  name     = "dispatch"
  location = "us-central1"
}

resource "google_cloud_run_v2_service" "ingest" {
  name     = "location-ingest"
  location = "us-central1"
}

resource "google_pubsub_topic" "events" {
  name = "ride-events"
}

resource "google_spanner_instance" "trips" {
  name   = "trip-store"
  config = "regional-us-central1"
}

resource "google_redis_instance" "locations" {
  name           = "location-cache"
  memory_size_gb = 4
}

resource "google_bigtable_instance" "telemetry" {
  name = "fleet-telemetry"
}

resource "google_bigquery_dataset" "lake" {
  dataset_id = "telemetry_lake"
}

resource "google_storage_bucket" "archive" {
  name     = "ridepulse-location-archive"
  location = "US"
}
