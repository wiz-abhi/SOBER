# Secrets Policy

How we store and rotate secrets. Operational facts, not the secrets themselves.

## Storage
- All secrets live in the vault; nothing is committed to git or pasted into chat.
- Services read secrets at boot via short-lived tokens, never from env files on disk.

## Rotation
- Database credentials rotate every 90 days, automatically.
- Any secret exposed in a log, ticket, or agent memory is treated as compromised and rotated **immediately**.
- Rotating a launch/production code invalidates the old value everywhere — old codes never work again.

If you find a secret in the knowledge base, that is a leak. Retract the document and rotate the value.
