# Why SnapStart was removed from this sample

## Status

Removed across the entire stack as of 2026-06-01. This document captures the
reasoning so that adopters considering SnapStart for their own builds know
what they're trading off.

## What SnapStart promised

Lambda SnapStart for Python 3.12 captures a fully-initialized execution
environment as a snapshot at version-publish time. Subsequent cold-restore
invocations resume from the snapshot in ~150-300ms instead of running the
full ~1190ms init path. For traffic-burst patterns (a guest-facing CRS
booking page that's idle for an hour and then takes a flood of requests
when an OTA dump arrives), the latency win is real.

The pattern that goes with SnapStart is:

- `AutoPublishAlias: live` on every function — every deploy publishes a new
  immutable version, and the `live` alias rolls forward to it.
- API Gateway integrations target the alias, not `$LATEST`.
- AWS bakes a snapshot of each new version asynchronously after publish.

## Why we removed it

Two real production traps surfaced during development of this sample.

### Trap 1: Mersenne Twister state is captured in the snapshot

Python's standard `random` module holds module-level state. SnapStart serializes
that state into the snapshot at publish time. Every restored execution
environment starts from the **identical** RNG state and generates **identical**
sequences until the per-environment state drifts.

This bit us. `complete_booking.py` and `create_reservation.py` both used
`random.choices(...)` to mint `RES-XXXXXX` confirmation numbers. Concurrent
warm-restore workers rolled the same numbers in lockstep, hitting the
`reservations_confirmation_number_key` unique index and 500-ing every batch
booking from the simulator for 72 hours.

Fix shipped: switch to `secrets.choice` (which reads from `os.urandom`,
which the SnapStart restore hook reseeds correctly) on both code paths,
plus removing SnapStart from the three functions that mint such values.
See git history for the full timeline.

The trap doesn't go away just because we fixed the two known sites. Any
future contributor who reaches for `random.choice` for any uniqueness-
critical purpose re-creates the same bug. For a public sample where
adopters copy-paste patterns, that's a footgun we'd be handing them.

### Trap 2: `AutoPublishAlias` only republishes on code-hash changes

SAM's `AutoPublishAlias` macro emits an `AWS::Lambda::Version` resource
whose change-detection key is the **code zip hash**. IAM-role-only
changes, env-var-only changes, and other configuration-only diffs do
not produce a new published version. The `live` alias keeps pointing
at the previous version, which has the *previous* configuration baked
in immutably.

We hit this during the per-function IAM refactor (security review C-1).
Tranche 1 migrated 38 functions from a shared role to a tighter
`LambdaDbReadRole`. CloudFormation deployed the change to `$LATEST`,
but no new version was published — `live` stayed on the old version
with the old role. API Gateway routes through `:live`, so the new
role never took effect. The smoke tests verified the *old* role still
worked, which is the wrong question.

Workarounds exist (manual `lambda publish-version` + `lambda update-alias`
per function), but they require operators to know about and remember to
run them. For a sample, that's an unacceptable burden.

## What we kept and what we lost

### Lost
- ~900ms of cold-start latency on the first request after a function has
  scaled to zero. For an active dev/demo stack, this happens once per
  deploy or once after long idle.
- A few minutes of deploy time from snapshot baking.

### Kept
- All correctness fixes that the SnapStart-era investigation produced, most
  visibly the `secrets.choice`-based confirmation-number generation that's
  more robust regardless of SnapStart's status.
- The DB-busyness fix from the leaked-transaction investigation (driven by
  SnapStart's pinning of Aurora to its 0.5 ACU floor when `INTRANS`
  connections persisted across freezes — see git history).
- The three functions that were already SnapStart-free (the two Step
  Functions task targets and the activity simulator) stay that way.

## When an adopter should consider re-enabling SnapStart

If you fork this sample for production traffic and either of these is true:

- Your CRS hits a daily traffic peak that exceeds your warm pool, and
  cold-start latency on the burst is degrading your guest booking flow.
- Your PMS sees long idle gaps (e.g., overnight) followed by morning
  staff-login bursts, and the warm-up tax is visible to staff.

…then the cold-start win may be worth re-introducing the operational
complexity. Add it back per-function with these guardrails in mind:

1. **No `random.*` for any uniqueness-critical value.** Use `secrets`.
   Audit every existing handler that generates IDs/confirmation numbers/
   tokens. The Mersenne Twister state will be shared across all restored
   workers from the same snapshot.

2. **No DB connections, AWS clients, or wallclock state captured at
   module init.** Lazily initialize on first invocation, after the
   restore hook has fired. `boto3.client(...)` calls at module top-level
   are safe; opening a `psycopg.connect(...)` at module top-level is not.

3. **Expect IAM-only and env-var-only deploys to require manual version
   publication.** Either accept that your IAM tightenings won't take
   effect on the `live` alias until the next code change, or wire a
   post-deploy script that runs `aws lambda publish-version` +
   `aws lambda update-alias` for every function whose configuration
   changed.

4. **Plan for ~1-2 minutes of additional deploy time per function** for
   snapshot baking. With a fleet of 60 functions, that's a real chunk
   of every full-stack deploy.

## Why this matters for sample-readiness

The architectural patterns this sample is meant to teach — six-layer
hospitality model, EventBridge-driven async flows, RDS Proxy IAM auth,
per-function IAM, MFA enforcement at the auth layer — are independent
of the cold-start optimization. Including SnapStart pulled adopters'
attention toward an optimization concern (and its hazards) before they
finished absorbing the architecture. Removing it lets the architecture
speak first.

If you want to learn the SnapStart pattern itself, AWS has dedicated
samples for that purpose. This sample's job is to show how a hotel
platform composes; SnapStart is an opt-in bolt-on, not part of the
core teaching.
