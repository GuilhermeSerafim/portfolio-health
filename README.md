# Portfolio health

A small public status feed for four portfolio projects. Python standard library,
curl, GitHub Actions and Pages; no AI calls, account logins, reservations or leads.

Feed: https://guilhermeserafim.github.io/portfolio-health/status.json

The workflow requests a check at minutes **03, 18, 33 and 48 UTC**. GitHub may delay
or skip scheduled runs. Consumers must downgrade observations older than **45
minutes** to `unknown`. This is not an uptime SLA or proof that a whole product
works. See [the contract](CONTRACT.md) and [JSON Schema](status.schema.json).

## Coverage

- GeoRisk / OrbTalus: public synthetic demonstration.
- SEVEN Tools: public demonstration with synthetic scenarios.
- Play Senac: public demonstration with synthetic reservations; selected `main-` module.
- Mesa de Negócios: public landing document and module entry script only.

Checks validate HTTP 200, an expected HTML marker and a selected same-origin
module entry script. By default this is the first module; an explicit filename
prefix selects the application's entry when a helper appears first (for example,
Angular `main-` after polyfills). Missing selected modules fail the check.
They do not execute JavaScript, check transitive imports,
test API/database health or submit forms. Private originals and sleeping Render
backends are not monitored.

Only two equivalent service failures produce `down`; recovery on retry produces
`degraded`. HTTP 401/403, bot challenges and rate limits are inconclusive.
Maintenance is an explicit, time-bounded declaration. Real check times and
per-target identities are included; the publication time cannot renew evidence.

## Run

Python 3.11+ and curl with `%{json}` support are required.

```sh
python -m unittest discover -s tests -v
python monitor.py
```

The collector allows at most four simultaneous targets, 15 seconds per attempt,
one retry after 30 seconds for a service failure, and a 180-second total deadline.
Each response is capped at 2 MiB. Redirects must remain on reviewed HTTPS hosts,
without credentials or query strings. Temporary response bodies are discarded.
`responseTimeMs` measures the complete probe, including retry delay when used;
it is not a page-speed score.

The Pages artifact contains only `status.json`, `status.schema.json` and
`.nojekyll`. No logs, response bodies or credentials are published.

## Operations

Edit `targets.json` only after validating a final public URL and its safe read
path. URL, role or probe-recipe changes (including `entryScriptPrefix`) produce
a new `targetId`, preventing old success from being reused.
`maintenance` may be set on a target with `startsAt`,
`endsAt` (UTC ISO strings) and a short public `message`.

The workflow serializes collection and publication. Optional last-success history
comes only from the previous public snapshot for the same target. If history is
unavailable it remains null; no timestamp is invented.

Review Actions/Pages availability and repository activity periodically. GitHub
can disable schedules after 60 days without repository activity. A manual
`workflow_dispatch` proves publication, not the operation of the scheduler.

Public repository standard runners and Pages fit the documented free offering.
No paid subscriptions are enabled by this project; account-wide quotas, provider
terms and availability may change. See [Actions schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
