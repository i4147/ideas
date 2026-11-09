# 50 — `gh-issue-triage` (issue backlog automation for a solo maintainer)

> **Difficulty 4/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ⚠️ mostly solved** — `actions/stale` (official GitHub action, auto-close with grace period), `probot` apps (`stale`, `issue-label-bot`, `welcome`), `github/issue-labeler` (regex/YAML rules), `gh issue list --json`, `label-sync`, `triage` GitHub Action, `claude-code-action`-style bots.
> **Pivot required?** Yes — but "solo maintainer, local, dry-run-first" is a defensible niche.

## What exists, and why the naive version fails

`actions/stale` alone covers: labels on inactivity, comment warnings, close after N days, exempt labels, and per-issue-type config. It runs in CI for free and needs no token plumbing. `github/issue-labeler` covers keyword→label rules. So the "label + close stale + assign" feature list is a dupe.

Real gaps, in order of usefulness:

1. **Local, ad-hoc, dry-run triage without CI.** For a maintainer who doesn't want a GitHub Action with write permissions on their repo, running `gh-issue-triage --dry-run` locally and seeing proposed actions is genuinely nicer. `gh`+`actions/stale` require either setting up a workflow or clicking.
2. **Semantic duplicate detection** across issues (embedding-free: TF-IDF over titles+bodies, or `difflib` on normalised text, then a similarity threshold). "Same bug reported 5 times" is the #1 solo-maintainer pain, and `actions/stale` cannot do it. Keep it local and explainable: show the top 3 similar issues with scores.
3. **Reproducibility checklist**: does the issue contain version, OS, command, traceback? Detect missing sections and post a template-specific nudge (`--template-check`). This measurably improves report quality and no tool does it.
4. **Weekly digest with pressure signals**: issues that are (a) unanswered by the maintainer for >7 days, (b) labelled `bug` with no reproduction, (c) duplicates of a closed fix. This is what the maintainer actually reads.

## Design

```bash
gh-issue-triage report                     # digest, read-only by default
gh-issue-triage plan --stale 60d           # proposed labels/comments/closes, as a diff
gh-issue-triage apply --plan plan.json --yes
gh-issue-triage dupes --threshold 0.82
gh-issue-triage reply --template missing-repro ISSUE
```

Rules in `.github/issue-triage.toml`:

```toml
[labels]
bug = ["(?i)\\b(error|traceback|exception|crash)\\b"]
feature = ["(?i)\\b(feature request|would be nice|proposal)\\b"]
[stale]
after = "60d"; close_after = "14d"; exempt = ["security", "help wanted", "pinned"]
[repro]
required = ["version", "os", "traceback"]      # headers or fenced blocks to look for
```

**Always plan → apply**, never mutate during `report`. Every apply writes a `triage.log` (issue, action, rule, timestamp) so a misfire is explainable and reversible (`gh issue edit` to undo labels).

## Implementation

- Use `gh api`/`gh issue list --json` rather than a bespoke HTTP client: auth, pagination, and enterprise hosts come free. Wrap `/repos/{o}/{r}/issues?state=open&per_page=100` with `--paginate` (careful: the issues endpoint returns PRs too — filter `pull_request in .`).
- **Rate-limit aware**: `gh api rate_limit` first; cache the issue list for 10 minutes.
- Duplicate detection: normalise (lowercase, strip code blocks/templates/URLs), TF-IDF vectors over title+body, cosine similarity, then a second gate (same labels or same file mentioned) to cut false positives. Report the matched pair with the shared keyphrase — explainability matters more than recall here.
- **Never auto-close security issues**, and never close an issue with activity from a non-bot in the last 7 days.

## Tests

Fixture issue JSON (captured, redacted) — 20 issues with known labels/dupes/staleness. Assert: rules produce exactly the expected plan; a duplicate pair is detected; a security-labelled issue is exempt; `apply` without `--yes` exits non-zero; dry-run makes zero API calls (assert with a mocked transport); pagination over 3 pages; and an issue authored by a bot is skipped.

## Pitfalls

- Bots and dependabot issues will dominate the digest — filter `user.type == "Bot"` by default.
- Comments posted by the tool must be idempotent (check for an existing marker string like `<!-- triage:missing-repro -->`) or you'll spam.
- Assigning to "the repo owner" is wrong in orgs; use `--assign self` explicitly.
- Timezone/locale in `--stale 60d` must use the API's `updated_at`, not local file times.
- Don't be the bot that closes a good issue because the maintainer was on holiday: require `--min-issues 10` style guardrails to be deliberately disabled.

## Definition of done

`report` gives a solo maintainer a one-screen digest with 3 real duplicates and the 4 issues that need a reply, and `apply` is fully previewable and logged.
