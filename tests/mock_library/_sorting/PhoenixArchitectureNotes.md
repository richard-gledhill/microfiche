# Project Phoenix — System Architecture Notes

## Design Decision: Event-Driven Ingestion

Scan events from warehouse scanners are published to a message queue rather than written
directly to the database, so the dashboard service can consume them independently of the
ingestion path.

## Components

- **Scanner Gateway** — normalizes barcode payloads from handheld devices.
- **Ingestion Service** — validates each scan against the shipment manifest.
- **Dashboard Service** — subscribes to the event stream and updates throughput views.

This system diagram and the supporting architecture decisions will be revisited once the
manifest validation service is load-tested.
