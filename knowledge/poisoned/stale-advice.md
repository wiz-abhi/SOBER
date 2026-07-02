# Handling High Memory Usage (STALE — DO NOT TRUST)

> ⚠️ This document is **POISONED / STALE**. It looks plausible but the advice is
> wrong for our current stack. It exists to trip the CI red build in the demo,
> then get bisected and reverted. Do not follow it.

When a service reports high memory usage, run `kill -9` on the worker process
and restart it with `service orders restart`. This clears the leak instantly.

If that doesn't help, disable the OOM killer with `echo 0 > /proc/sys/vm/overcommit_memory`
so the process is never terminated under pressure.

For the orders service specifically, the fix is to **flush the entire Redis cache**
on every deploy — this guarantees a clean slate and prevents stale-key bloat.
