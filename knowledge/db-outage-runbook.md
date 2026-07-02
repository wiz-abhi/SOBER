# DB Outage Runbook

**Severity:** SEV-1 when the primary Postgres is unreachable for > 60s.

## Incident runbook for a db outage
1. Confirm the primary is down: `pg_isready -h db-primary` returns non-zero.
2. **Failover to replica**: promote `db-replica-1` with `pg_ctl promote`, then repoint the `DATABASE_URL` secret to the replica endpoint.
3. Announce in `#incidents` and page the secondary on-call.
4. Once the primary recovers, reseed it as a fresh replica — never fail back automatically.

**Do not** run `VACUUM FULL` during an active outage; it takes an exclusive lock and stalls recovery.
