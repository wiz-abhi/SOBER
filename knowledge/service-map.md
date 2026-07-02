# Service Map

Operational facts about our core services.

- **api-gateway** — public entrypoint, terminates TLS, routes to internal services. Owned by team Platform.
- **orders** — handles checkout and order state. Talks to Postgres (`db-primary`) and Redis. Owned by team Commerce.
- **inventory** — stock levels and reservations. Event-driven off the `orders` Kafka topic. Owned by team Commerce.
- **notifications** — email/SMS fan-out. Owned by team Growth.

## Key endpoints
- Health checks live at `/healthz` on every service.
- Metrics are scraped from `/metrics` (Prometheus format) every 15s.
