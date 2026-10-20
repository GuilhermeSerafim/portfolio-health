# Portfolio health feed v1

Public project IDs: `georisk`, `seven-tools`, `playsenac`, `mesa`.

The feed measures the public demonstration URL, not the private original product.
It makes read-only HTTPS requests to the HTML document and its first same-origin
module entry script. `coverage: "http-content"` does not assert that a browser
executed the application, that a form delivered a lead, or that an API/database
works. No inference, user transaction or browser credential is used.

Top-level fields:

- `schemaVersion`: `1`.
- `generatedAt`: UTC time this complete snapshot was produced.
- `maxAgeSeconds`: `2700` (45 minutes).
- `source`: `provider`, `event`, `runId`, `commit`, `observationScope`.
- `projects`: an **array** of four project objects with the IDs above.

Each project has `id`, `name`, `targetId`, `role`, `url`, `phase`, `status`,
`reasonCode`, `publicMessage`, `checkedAt`, `lastSuccessAt`, `validUntil`,
`coverage`, `components`, and `maintenance`.

The machine-readable definition is [status.schema.json](status.schema.json).
`components` is an array: zero items for pending targets, otherwise one
`public-entry` component aggregating the document and entry-script checks.
`maintenance` is null or `{startsAt, endsAt, message}`. Component timestamps are
the same real completed attempt used by the aggregate; checking the entry script
does not execute it.

`phase` is `active` or `pending`. An unpublished target has a null URL and
timestamps, `phase: "pending"`, `status: "unknown"` and `reasonCode: "demo_pending"`.
`targetId` changes when the measured URL or coverage changes. Historical success
must not cross targets.

Statuses: `operational`, `degraded`, `maintenance`, `down`, `unknown`.
A repeated service failure can produce `down`, scoped to one observer.
An HTTP 401/403, challenge, rate limit, blocked redirect, collector exception or
expired result produces `unknown`. A failure followed by success is `degraded`.
Maintenance is an explicit bounded declaration; it is not inferred from errors.

Consumers MUST:

1. Validate the schema, known IDs, status enumeration and UTC timestamps.
2. Treat malformed, missing, future-dated (over five minutes), unavailable or
   expired evidence as `unknown`, regardless of the supplied status.
3. Recompute expiry at least once per minute and on tab focus. A successful fetch,
   304, fresh `generatedAt` or cache refresh never renews `checkedAt`.
4. Check both project and component timestamps. Expiry is the earlier of
   `validUntil` and `checkedAt + 2700 seconds`. No timestamp means no green badge.
5. Keep navigation usable when the feed fails. A pending target must not receive
   an invented link, status or timestamp.
6. Display coverage and last check time. Suggested wording: "Demo responded to
   the last check"; use "Availability not confirmed" for unknown.
7. Treat a maintenance notice separately from stale observations. Do not extend
   its end time automatically.

`lastSuccessAt` is known history for this exact target and coverage. It can be
null, including after history cannot be recovered. `generatedAt` is not a probe
timestamp. Source `event: "workflow_dispatch"` proves a manual run only;
`event: "schedule"` identifies a scheduled run, without any timing SLA.

The feed contains no provider credentials, response bodies, private URLs or error
traces. CORS and HTTP cache behavior must be checked at the published URL.
