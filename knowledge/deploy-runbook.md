# Deploy Runbook

Our deploys are blue/green through the `shipit` CLI.

## Standard deploy
1. Merge to `main`; CI builds an immutable image tagged with the commit SHA.
2. Run `shipit deploy --env staging --sha <sha>` and wait for the smoke suite to go green.
3. Promote with `shipit deploy --env prod --sha <sha>`; this shifts 10% of traffic first, then 100% after the canary window.
4. Watch the error-rate dashboard for 15 minutes before declaring success.

## Rollback
Run `shipit rollback --env prod` — it repoints the load balancer to the previous green stack. Rollbacks are instant and never require a rebuild.
