# On-Call Guide

On-call rotates weekly, handed off every Monday at 10:00 in `#oncall`.

## Responsibilities
- Acknowledge pages within 5 minutes; escalate to secondary if you cannot.
- Keep the incident channel as the single source of truth during a SEV.
- File a blameless postmortem within 48 hours of any SEV-1 or SEV-2.

## Escalation ladder
1. Primary on-call (PagerDuty schedule `core-primary`).
2. Secondary on-call (`core-secondary`).
3. Engineering manager, then the VP of Engineering for customer-facing SEV-1s.

The on-call is empowered to roll back any deploy without further approval.
