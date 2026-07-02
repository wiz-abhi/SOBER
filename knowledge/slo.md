# Service Level Objectives

Our published SLOs and the error budgets that back them.

| Service | Availability SLO | Latency SLO (p99) |
|---------|------------------|-------------------|
| api-gateway | 99.95% | 300ms |
| orders | 99.9% | 500ms |
| inventory | 99.5% | 800ms |

## Error budget policy
- When a service burns 50% of its monthly error budget, feature deploys pause and reliability work takes priority.
- Budget resets on the first of each month.
- A single SEV-1 that exhausts the budget triggers a mandatory reliability review.
