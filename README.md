# SOBER — CI/CD for Agent Brains

> Git, pipelines, canary deploys, and Dependabot — for memory.
> Built on [Cognee](https://github.com/topoteretes/cognee) for **The Hangover Part AI: Where's My Context?** hackathon.

Your agent's memory is production infrastructure — but today it ships with no version control, no tests, no rollback, and no deploy pipeline. SOBER is the missing operations layer: a `brain` CLI + GitHub Action that treats a Cognee knowledge graph as a **versioned, testable, revertable, deployable artifact**.

*(Full README lands with the submission — this is the Day-1 stub.)*

## Status

- [x] Repo scaffold
- [ ] Gate 1: cognee installs on Windows
- [ ] Gate 2: keyless memory round-trip (add → recall → forget → gone)
- [ ] Gate 3: snapshot/export round-trip
- [ ] `brain` CLI: snapshot / diff / test / revert / bisect
- [ ] Memory CI suite with forbidden-knowledge tests
- [ ] GitHub Action PR flow
- [ ] improve() gating + nightly self-improvement PR
- [ ] Cognee Cloud canary (push/serve)

## AI-assistance disclosure

This project is built with **Claude Code** (Anthropic) as an AI pair programmer, per the hackathon's AI-use disclosure requirement. All architecture decisions and final code are reviewed by the human author.
