# Portfolio health implementation

## Scope and authorization

Create this isolated public monitor and feed, using existing GitHub access.
No portfolio/demo edits, private-origin checks or transactional requests.
The existing research defines the comparison and the 15-minute/45-minute policy.

## Tasks

1. Define the contract and test status classification, pending targets, expiry,
   history isolation, total deadline and bounded safe transport.
2. Implement a Python standard-library collector with curl, aggregate JSON and
   no paid/AI dependencies. Tests replace only external transport.
3. Publish an independently hosted JSON artifact with pinned GitHub Actions.
4. Verify CI, public headers/schema and at least one genuine `schedule` run.

## Review focus

No false green from stale or incomplete evidence; challenge pages versus valid
Cloudflare-injected HTML; no redirected private/third-party probes; total deadline
must kill owned curl processes; no false claim of browser/API coverage; missing
URLs remain pending; snapshot publication cannot overwrite newer evidence.

## Decisions

- New standalone repository initialized on main: no existing shared work is
  present, and public creation/publication is explicitly authorized.
- No extra status page, dashboard, database or portfolio integration in this
  repository. Only the JSON artifact, source, tests and documentation.
- Use standard library + curl supplied by the runner; no package installation.
- The parent Manager supplies one independent review; this executor does not
  create additional agents.
