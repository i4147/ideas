# 77 — `aws-cost-estimator` (what will this stack cost?)

> **Difficulty 6/10** · **Effort ~8 days** · **Tier: hard**
> **Prior art: ❌ solved, and by a free tool** — `infracost` (the standard: parses Terraform plan JSON, prices against the AWS Pricing API, posts PR comments; free for Terraform/CDK), `cloud-custodian` (compliance/cost actions), `aws-pricing` (Python API wrapper), `boto3` `pricing` client, `terraform-cost-estimation` (unmaintained predecessors), AWS Cost Explorer/Budgets (actuals, not estimates), `checkov` (policy, not pricing).
> **Merged from:** `aws-cost-estimator` ×2 (interactive prompts + terraform/cdk parsing).
> **Verdict: don't build the estimator.** Build the *explainer* only if you have a specific angle.

## Why the obvious version fails

Prices are not a table you can hardcode: 400+ services, per-region prices, tiered volume pricing, Savings Plans/RI discounts, data-transfer tiers, EBS/IOPS combinations, and request-based pricing (Lambda, S3, API Gateway). `infracost` maintains a generated price database, refreshed weekly, and reconciles it against the AWS Price List API. Your static dictionary will be wrong within a month, and wrong cost estimates are worse than none.

Also: "estimate AWS costs for a given service configuration with interactive prompts" (one of the two source ideas) is a calculator UI — the AWS pricing calculator exists, is authoritative, and is shareable via URL.

## The three angles that are still open

1. **"Why did the bill change?"** — Cost Explorer gives totals and a service breakdown; it does not explain *which resource* changed. Mapping a `+$412` delta to "the NAT Gateway you added on Tuesday" needs resource-level cost allocation: `aws ce get-cost-and-usage` with `GROUP BY RESOURCE_ID` (only available when cost allocation tags/resource IDs are activated — detect and explain that prerequisite), joined against `describe-*` calls for creation dates and tags. A CLI that answers "what did I add that costs money?" is genuinely useful and unserved.
2. **Idle spend detection**: unattached EBS volumes, unused Elastic IPs, idle load balancers (CloudWatch `RequestCount=0`), old snapshots, stopped instances with attached volumes, over-provisioned RDS (CPU < 5 % for 30 days), and NAT Gateway data processing (the classic surprise). These are *findings with dollar amounts*, from CloudWatch + resource APIs — deterministic, no pricing guesswork beyond a small known-rate table.
3. **Estimate from a running account vs from code**: `terraform plan`-based estimation is `infracost`'s job; actual-resource-based estimation from CloudWatch metrics is not.

## Design (the defensible version)

```bash
cost-explain delta --period 2026-10-01:2026-11-01 --group-by resource
cost-explain idle --region ca-central-1 --min-usd 5
cost-explain tag-audit --require team,env,cost-center
```

Sample output:

```
COST DELTA  Oct 1–31 vs Sep 1–30:  +$1,284 (from $3,410 to $4,694)
TOP CONTRIBUTORS
  +$612  nat-gateway  nat-0a1b…  (created 2026-10-04)   data processing 2.1TB
  +$401  rds  db-prod-replica    (created 2026-10-11)   db.r6g.xlarge multi-AZ
  +$188  ec2  i-0f2c…            instance type changed m5.large → m5.2xlarge (Oct 6, CloudTrail)
  -$117  s3   logs-bucket        lifecycle rule took effect

IDLE (potential saving $214/mo)
  $96   3 unattached EBS volumes (gp3, 1.6TB total)         created 2025-11…2026-03
  $48   2 idle ALBs (RequestCount = 0 for 14d)
  $70   1 Elastic IP not associated
```

## Data sources, all read-only

- `aws ce get-cost-and-usage` (Cost Explorer API, `$0.01/request` — warn, batch by month) with `Granularity=MONTHLY`, `GroupBy=[{Type: DIMENSION, Key: RESOURCE_ID}]`.
- `aws resourcegroupstaggingapi get-resources` for the inventory + tags.
- `aws ec2 describe-volumes --filters Name=status,Values=available`, `describe-addresses`, `describe-load-balancers` + CloudWatch `RequestCount` (`Sum` over 14d).
- CloudTrail `lookup-events` for "who changed the instance type" (best effort, 90-day window).
- Rate table for a *small* set (EBS $/GB-month, EIP hourly, NAT hourly + $/GB) from the AWS Price List API at runtime, cached 7 days — not hardcoded.

Everything is `boto3` with a read-only IAM policy that the tool prints (`cost-explain iam-policy`).

## Tests

`moto` (AWS mock) fixtures: volumes in `available`/`in-use`, EIPs attached/detached, an ALB with zero requests, cost data shaped like `get-cost-and-usage` responses with resource grouping. Assert: idle findings and dollar math against a fixture rate table, delta attribution joins by resource id, missing cost-allocation tags produce a clear prerequisite message (not an empty report), and no write API is ever called (assert with a moto mock that raises on any non-`Describe*`/`Get*`). Pagination: 3 pages of results.

## Pitfalls

- Cost Explorer is `us-east-1` only, regardless of your region — a classic first bug.
- Estimates are not bills: label every number as an estimate and show the period and rounding.
- Savings Plans/RI/credits distort deltas — report "on-demand equivalent" separately from net cost.
- Resource IDs in Cost Explorer require activation (12–24 h lag); detect and tell the user exactly what to enable.
- Never request write permissions "to clean up"; this tool reports, a human acts.
- Multi-account: `--profile`/`--assume-role` per account, and aggregate explicitly.

## Definition of done

On a real account, `delta` attributes ≥70 % of a month-over-month change to specific resource IDs with creation dates, and `idle` finds the three classic wasters with defensible dollar amounts. Otherwise use `infracost` for code, Cost Explorer for actuals.
