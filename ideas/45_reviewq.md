# 45 — `reviewq` (the review queue across many repos and orgs)

> **Difficulty 4/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `gh` (`gh search prs --review-requested=@me`), `glab mr list`, GitHub's dashboard, `review-requested` browser extensions, `octobox`.
> **Pivot required?** Yes — multi-host, multi-org aggregation with *age × size × staleness* ranking.

## The problem

You're in three GitHub orgs plus one GitLab group. Your review queue is spread across four web dashboards. `gh search prs --review-requested=@me --archived=false` works for GitHub and is a good start — but it doesn't cover GitLab, doesn't rank, and doesn't answer "which of these is blocking someone else".

## Design

```bash
reviewq                                  # ranked queue across all configured hosts/orgs
reviewq --orgs myorg,ossorg --group team-a --mine
reviewq watch --interval 10m --notify    # desktop notification for new requests
reviewq stale --older-than 5d            # PRs you've been asked to review and have ignored
reviewq summarize --format markdown      # paste into standup
```

Ranking must be transparent (print the score components):

```
score = 3·(blocked?) + 2·(age_days/7) + 1·log10(diff_lines) - 2·(draft) - 1·(ci_failing)
```

| repo | # | title | author | age | +/- | ci | waiting on me |
|---|---|---|---|---|---|---|---|
| shop-api | 412 | fix cart rounding | @li | 6d ⚠ | +48/-12 | ✗ | review (requested 6d ago) |
| infra | 88 | bump terraform | @sam | 2d | +900/-800 | ✓ | review (huge diff) |

Columns that matter: `draft` (skip), `ci` status (reviewing a red PR is wasted time), `mergeable`/`conflicts`, whether your review is the *only* thing blocking merge, and the last comment author (has the author answered your question?).

## Implementation

- **Auth reuse, not re-invention**: shell out to `gh api` and `glab api` when the CLIs exist and are authenticated; otherwise accept a token from the environment (`GITHUB_TOKEN`, `GITLAB_TOKEN`). Never store tokens yourself.
- **Efficient GraphQL**: one GitHub GraphQL query per search (`search(query: "is:open review-requested:@me")`), requesting `title, additions, deletions, updatedAt, reviewDecision, isDraft, mergeable, statusCheckRollup { state }` — 30–80 PRs in one request instead of N+1 REST calls.
- **GitLab**: `GET /merge_requests?scope=assigned_to_me&state=opened`, plus `reviewers` in the payload; paginate with `X-Next-Page`.
- **Cache** responses in `$XDG_CACHE_HOME/reviewq/` for 60 s so `--watch` and repeated invocations stay fast and under rate limits.
- **"Blocked on me"** determination: PR is not a draft, CI not failing, `reviewDecision != APPROVED` or your review state is `CHANGES_REQUESTED`/pending, and the last activity is from someone else.

## Tests

`respx`/`responses` fixtures for GitHub GraphQL and GitLab REST (captured, redacted). Assert: ranking order on a fixed clock, drafts excluded unless `--include-drafts`, rate-limit headers handled (403 + `X-RateLimit-Remaining: 0` → wait or degrade), pagination across 3 pages, and a repo that vanished (404) not aborting the whole run.

## Pitfalls

- Review requests can be *teams*, not you — query `review-requested:@me` plus `team-review-requested:org/team` if configured.
- Diffs over ~5,000 lines: fetch `additions/deletions` from the search payload, never from `/pulls/{n}/files` (N+1 and truncation at 3,000 files).
- Never post review comments automatically — this tool reads. Keep `--notify` local (desktop) and opt-in.
- Timezones: sort by `updatedAt` but *display* "6d ago" from `now(tz)`; a queue that says "1d" for yesterday's 23:50 request is annoying.
- Rate limits are per-token per-hour: cache aggressively, and add `--no-cache` for debugging.

## Definition of done

One command shows a correctly ranked queue across 2 GitHub orgs + 1 GitLab group in under 2 s warm, and `stale` surfaces the 3 PRs people are waiting on you for.
