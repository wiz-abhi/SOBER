# Cache Runbook

We run Redis as a look-aside cache in front of Postgres.

## Symptoms of a cache incident
- Latency spikes on read-heavy endpoints while the DB looks healthy.
- `redis-cli info stats` shows a collapsing `keyspace_hit_ratio`.

## Recovery
1. Do **not** flush the whole cache under load — a cold cache stampedes the DB.
2. Instead, warm critical keys first with `cache-warm --top 500`, then evict stale namespaces selectively.
3. If Redis itself is down, the app degrades gracefully to direct DB reads; scale up DB replicas to absorb the load.

Cache TTLs are 15 minutes by default; never set a TTL below 60 seconds in production.
