# Deployment Guide

End-to-end instructions to deploy the AnyCompany Hotel CRS + PMS platform to a clean AWS account. Target audience: anyone with admin AWS access, working in a terminal.

Total time on a fresh account: about **25 minutes**.

---

## Prerequisites

| Tool | Min version | Purpose |
|---|---|---|
| AWS CLI v2 | 2.x | Manage AWS resources |
| AWS SAM CLI | 1.100+ | Deploy the nested CloudFormation stack |
| Python | 3.12 | Lambda runtime and the migration / seed scripts |
| Node.js | 20+ | Frontend builds (CRS + PMS) |
| npm | 10+ | Frontend dependencies |
| Docker | Latest | `sam build` container builds |

Install the Python helpers used by migration and seed scripts:

```bash
pip install "psycopg[binary]>=3.1.0" boto3
```

## Before you start

### AWS profile

You need an AWS profile with admin-level permissions (CloudFormation, Lambda, S3, IAM, Cognito, API Gateway, SQS, Step Functions, Secrets Manager).

```bash
aws configure --profile my-profile
aws sts get-caller-identity --profile my-profile   # sanity check

export AWS_PROFILE=my-profile
export AWS_REGION=us-east-1
```

> ### ⚠️ Region: deploying outside `us-east-1` requires `EnableCloudFrontWaf=false`
>
> The platform deploys to any region (the template uses the `AWS::Region`
> pseudo-parameter throughout) **with one exception**: the SPA distributions'
> WAF is a `Scope: CLOUDFRONT` WAFv2 WebACL, and AWS only allows those to be
> **created in `us-east-1`**. Because it's part of this single stack, a deploy to
> any other region fails with `"The scope is not valid"` unless you disable it.
>
> - **Deploying to `us-east-1` (default):** nothing to do — the CloudFront WAF
>   deploys normally (`EnableCloudFrontWaf` defaults to `true`).
> - **Deploying to ANY other region:** add `EnableCloudFrontWaf=false` to your
>   parameter overrides (see Step 2). The SPA CloudFront distributions then deploy
>   **without** a WAF. The **regional WAF on the REST API stages** (the data plane)
>   is unaffected and always deploys — so your APIs stay protected. If you need a
>   WAF on CloudFront in a non-`us-east-1` deployment, create a `Scope: CLOUDFRONT`
>   WebACL in `us-east-1` separately and associate it with the distributions
>   out-of-band.
>
> Set `AWS_REGION` (and the `region` in `samconfig.toml`) to your target region and
> use it consistently for every step below. Also note: if you customize ACM
> certificates for the distributions, those must also live in `us-east-1`.
>
> _Verified 2026-06-04: full from-scratch deploy + migrations + seeds + both
> frontends to a separate account in `us-east-2` with `EnableCloudFrontWaf=false`._

```bash
export AWS_REGION=us-east-2   # example: any non-us-east-1 region
```

### Stripe test keys

1. Go to <https://dashboard.stripe.com/test/apikeys>.
2. Copy the **Publishable** (`pk_test_...`) and **Secret** (`sk_test_...`) keys.

The secret key goes to AWS Secrets Manager; the publishable key is injected into the frontend at build time. Neither is committed. All `.env*` files are in `.gitignore`.

---

## Step 1 — Store the Stripe secret

```bash
aws secretsmanager create-secret \
  --name anycompany-booking-stripe-dev \
  --secret-string '{"api_key":"sk_test_YOUR_SECRET","webhook_secret":"whsec_placeholder"}'
```

If it already exists, use `update-secret` instead. The webhook secret is a placeholder — you'll replace it in Step 7.

---

## Step 2 — Deploy the stack

A single `sam deploy` brings up VPC, Aurora, Cognito, EventBridge, SQS, Step Functions, analytics, WAF, two API Gateways, two S3 + CloudFront distributions, and every Lambda.

```bash
sam build
sam deploy --guided     # first time — answers saved to samconfig.toml
# sam deploy            # subsequent deploys

# Deploying outside us-east-1? You MUST disable the CloudFront-scope WAF
# (see the Region note above). Example for a non-us-east-1 region:
# sam deploy --region us-east-2 \
#   --parameter-overrides Environment=dev EnableCloudFrontWaf=false
```

During `--guided`, accept defaults and say **Yes** to:
- Allow SAM CLI IAM role creation
- Save arguments to configuration file

Keep rollback enabled. Takes 8–12 minutes (longer on a fresh account — Aurora +
the VPC-attached Lambda fleet dominate; a true clean-account run is ~25–30 min).

**If the deploy fails mid-way**: most often it's an orphan S3 bucket from a prior attempt. Check the CloudFormation events in the console. Delete the offending bucket and rerun `sam deploy`.

---

## Step 3 — Capture stack outputs

Pull the User Pool ID into a shell variable; later steps need it.

```bash
USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name anycompany-booking \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text)
```

The `auth.yaml` stack defines the two custom attributes (`custom:property_id` and `custom:region`) directly in the user pool schema, and the SPA client lists them in `ReadAttributes`/`WriteAttributes`, so they're available immediately — no `add-custom-attributes` CLI step needed.

> **Updating an existing pre-rebrand pool?** If you're working with a Cognito pool that was originally created without those custom attributes, you'll need to add them once with:
>
> ```bash
> aws cognito-idp add-custom-attributes \
>   --user-pool-id $USER_POOL_ID \
>   --custom-attributes \
>     Name=property_id,AttributeDataType=String,Mutable=true \
>     Name=region,AttributeDataType=String,Mutable=true
> ```
>
> Fresh deploys with the current `auth.yaml` don't need this — the schema includes them from day one.

---

## Step 4 — Run database migrations

The database sits in a private VPC, so migrations run through a short-lived Lambda:

```bash
for f in 001_initial_schema.sql \
         002_integration_fields.sql \
         003_pms_schema.sql \
         004_pms_reservation_room_id.sql \
         005_pms_room_status.sql \
         006_add_property_region.sql; do
  python3 scripts/run_migration.py \
    --stack anycompany-booking \
    --db-name anycompany \
    --db-user anycompany_admin \
    --sql-file scripts/migrations/$f \
    --profile $AWS_PROFILE --region $AWS_REGION
done
```

`run_migration.py` creates a temporary Lambda in the VPC, runs the SQL via RDS Proxy IAM auth, and deletes the Lambda. Expected final line per file: `✓ SUCCESS`.

Run them in order on a fresh database. On subsequent environments, only apply the migrations you haven't run yet.

---

## Step 5 — Seed CRS data (properties, rooms, rates)

The CRS seed is large (50 properties × 365 days of availability) and the database lives in a private VPC, so we run it through a Lambda wrapper the same way migrations work:

```bash
python3 scripts/run_seed_data.py \
  --stack anycompany-booking \
  --db-name anycompany --db-user anycompany_admin \
  --profile $AWS_PROFILE --region $AWS_REGION
```

This creates **50 properties** across 10 regions, 3–6 room types each, a default BAR rate plan, **365 days of availability**, and three promo codes (`ANYCOMPANY10`, `SUMMER25`, `WELCOME`). It takes about 5 minutes inside the Lambda; the wrapper waits synchronously and reports back when done.

---

## Step 6 — Seed Cognito users and loyalty data

Get one property ID to assign property-scoped staff to:

```bash
API_URL=$(aws cloudformation describe-stacks \
  --stack-name anycompany-booking \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)

PROPERTY_ID=$(curl -s "$API_URL/properties?limit=1" | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['data'][0]['propertyId'])")
```

Create the demo users (8 guests + 6 staff):

```bash
python3 scripts/seed_cognito_users.py \
  --user-pool-id $USER_POOL_ID \
  --property-id $PROPERTY_ID \
  --profile $AWS_PROFILE --region $AWS_REGION
```

Seed loyalty profiles and a few historical stays:

```bash
python3 scripts/run_seed_pms.py \
  --stack anycompany-booking \
  --user-pool-id $USER_POOL_ID \
  --profile $AWS_PROFILE --region $AWS_REGION
```

All demo credentials are listed in **[DEMO_GUIDE.md](./DEMO_GUIDE.md)**.

### Activity simulator (optional — OFF by default)

The activity simulator is **not deployed by default.** It is gated behind the
`DeployActivitySimulator` stack parameter (default `false`). To include it, deploy
with the parameter set to `true`:

```bash
sam deploy --parameter-overrides Environment=dev DeployActivitySimulator=true ...
```

(A plain default deploy creates no simulator function, schedule, IAM role,
Cognito service user, or credentials secret — opt in with the parameter above,
or persist it via `sam deploy --guided`.)

### RDS Data API (optional — OFF by default)

The Aurora cluster's RDS Data API (HTTP endpoint) is gated behind the
`EnableDataApi` stack parameter (default `false`). When on, it provides an
HTTPS SQL path — `aws rds-data execute-statement` — convenient for ad-hoc
inspection without spinning up a VPC-attached Lambda.

It is **off by default for a reason**: the Data API runs as the database
**master user** and bypasses the per-function IAM-proxy access model the
application Lambdas use, so anyone with `rds-data` permissions plus the
cluster/secret ARNs can run arbitrary SQL. **Leave it off in production.** Turn
it on only for dev/demo:

```bash
sam deploy --parameter-overrides Environment=dev EnableDataApi=true ...
```

(A plain default deploy leaves the Data API disabled; opt in with the parameter
above, or persist it via `sam deploy --guided`.)

The steps below apply only when the simulator is deployed.

The simulator user is provisioned by CFN but lands in `FORCE_CHANGE_PASSWORD` state. Flip to `CONFIRMED`:

```bash
python3 scripts/finalize_simulator_user.py \
  --stack anycompany-booking \
  --profile $AWS_PROFILE --region $AWS_REGION
```

Seed the activity-simulator guest pool (200 guests with varied loyalty tiers):

```bash
# Requires: pip install faker (in a venv recommended)
python3 scripts/seed_simulator_guests.py \
  --stack anycompany-booking \
  --user-pool-id $USER_POOL_ID \
  --profile $AWS_PROFILE --region $AWS_REGION \
  --count 200
```

> **How much activity you see depends on this pool.** The simulator books *only*
> against these dedicated `simguest-*` profiles — never the 8 demo guests or the
> staff users from Step 6. So:
> - **Skip this step → the simulator runs but books nothing** (empty pool).
> - **Want more activity / variety?** Re-run with a larger `--count` (e.g.
>   `--count 500`). It's idempotent, so you can grow the pool at any time — run it
>   again later with a higher count to add more guests without disturbing existing
>   ones. A bigger pool also avoids saturation: at the default 30 reservations per
>   4-hour run over a 30-day forward window, a pool below ~500 can fill up the
>   available booking slots, after which runs increasingly "skip" (logged as
>   `overlap_skips`). For a lively demo, 500+ is a good target; 200 is fine for a
>   light feed.

The simulator runs every 4 hours via EventBridge. To trigger immediately:

```bash
aws lambda invoke \
  --function-name anycompany-pms-simulator-dev \
  --payload '{}' --cli-binary-format raw-in-base64-out \
  /tmp/sim.json --profile $AWS_PROFILE --region $AWS_REGION
cat /tmp/sim.json | python3 -m json.tool
```

Logs: `/aws/lambda/anycompany-pms-simulator-dev` (JSON-structured, every line tagged with `run_id`).

---

## Step 7 — Configure the Stripe webhook

```bash
echo "Webhook URL: ${API_URL}/webhooks/stripe"
```

1. Go to <https://dashboard.stripe.com/test/webhooks> → **Add endpoint**.
2. Endpoint URL: `${API_URL}/webhooks/stripe`.
3. Select events: `payment_intent.succeeded`, `payment_intent.payment_failed`, `charge.refunded`.
4. Copy the signing secret (`whsec_...`).
5. Update the Secrets Manager entry:

```bash
aws secretsmanager update-secret \
  --secret-id anycompany-booking-stripe-dev \
  --secret-string '{"api_key":"sk_test_YOUR_SECRET","webhook_secret":"whsec_REAL_SECRET"}'
```

---

## Step 8 — Deploy the CRS frontend

The publishable Stripe key must be in your shell before `setup-env.sh` runs, or the build embeds the placeholder and every card is rejected.

```bash
export STRIPE_PUBLISHABLE_KEY="pk_test_YOUR_PUBLISHABLE_KEY"

./scripts/setup-env.sh dev        # writes frontend/.env.dev + .env.local
./scripts/deploy-frontend.sh dev  # npm ci → build → S3 sync → invalidate
```

Verify the published key landed in the env file:

```bash
grep STRIPE frontend/.env.dev
# VITE_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

---

## Step 9 — Deploy the PMS frontend

```bash
./scripts/setup-pms-env.sh dev
./scripts/deploy-pms-frontend.sh dev
```

No Stripe key needed — the PMS doesn't take payments directly; its checkout flow goes through the `CheckoutBilling` Step Functions workflow.

---

## Step 10 — Verify

Print the URLs:

```bash
aws cloudformation describe-stacks --stack-name anycompany-booking \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl' || OutputKey=='PmsCloudFrontUrl'].[OutputKey,OutputValue]" \
  --output table
```

Run the smoke test below. It exercises CRS → EventBridge → PMS → Step Functions → loyalty:

1. Sign into CRS as `sarah.chen@example.com` / `AnyCompany2026!`.
2. Search a property, pick a room, apply promo `ANYCOMPANY10`, pay with card `4242 4242 4242 4242` (any future expiry, any CVC).
3. See the confirmation page (`RES-XXXXXX`).
4. Open the PMS at the `PmsCloudFrontUrl`, sign in as `admin@anycompanyhotels.com` / `AnyCompanyAdmin2026!`.
5. Go to **Stays** — the reservation should appear within a few seconds. A folio was created in parallel (check **Billing**).
6. Go to **Stays** as `frontdesk@anycompanyhotels.com` / `AnyCompanyFD2026!` (scoped to the property you seeded) and click **Check In** → **Check Out** on the reservation.
7. Back in Billing, the folio should now be `PAID` with a tax line and a payment record. Loyalty points appear under the guest's profile.

If any step fails, see **Troubleshooting** below.

---

## Environment reference

### Shell env vars

| Var | When | Purpose |
|---|---|---|
| `AWS_PROFILE` | Always | Which AWS profile to use |
| `AWS_REGION` | Optional | Defaults to `us-east-1` |
| `STRIPE_PUBLISHABLE_KEY` | Before `setup-env.sh` | Baked into CRS frontend build |

### Secrets Manager

| Name | Contents |
|---|---|
| `anycompany-booking-stripe-dev` | `{"api_key":"sk_test_...","webhook_secret":"whsec_..."}` |

### Frontend `.env` files (not committed)

| File | Generated by |
|---|---|
| `frontend/.env.dev` + `.env.local` | `./scripts/setup-env.sh dev` |
| `pms-frontend/.env` | `./scripts/setup-pms-env.sh dev` |

---

## Demo logins + URLs

The seeded users and passwords (identical in every deployment) live in
**[DEMO_GUIDE.md](./DEMO_GUIDE.md)**, along with the commands to print **your own**
deployment's CloudFront/API URLs and Cognito pool ID from your stack outputs.

---

## Redeployment

After backend code changes:

```bash
sam build && sam deploy
```

After CRS frontend changes:

```bash
export STRIPE_PUBLISHABLE_KEY="pk_test_YOUR_KEY"
./scripts/setup-env.sh dev
./scripts/deploy-frontend.sh dev
```

After PMS frontend changes:

```bash
./scripts/setup-pms-env.sh dev
./scripts/deploy-pms-frontend.sh dev
```

After adding a new SQL migration: run `scripts/run_migration.py` with the new file.

---

## Troubleshooting

### Frontend shows `Invalid API Key provided: pk_test_*******lder`

The frontend was built without a real Stripe key. Set `STRIPE_PUBLISHABLE_KEY`, rerun `setup-env.sh`, then `deploy-frontend.sh`.

### `Stack update failed — S3 bucket already exists`

Orphaned bucket from a prior failed deploy. Find and delete:

```bash
aws s3 ls | grep anycompany
aws s3 rb s3://<bucket-name> --force
```

Rerun `sam deploy`.

### Cognito user creation fails with `Attributes did not conform to the schema`

The pool is missing the custom attributes. On a current fresh deploy the schema includes them, so redeploy `auth.yaml`. If you're on an older pre-schema pool, run the `add-custom-attributes` CLI command shown in the Step 3 legacy-pool callout.

### PMS dashboard shows zero rooms for a property-scoped user

The ID token is missing `custom:property_id`. Either:
1. The user has no `custom:property_id` attribute — set it via `aws cognito-idp admin-update-user-attributes`.
2. The SPA client's `ReadAttributes` doesn't include `custom:property_id` — redeploy `auth.yaml`. (The current template includes it.)

Sign out and back in after fixing, so the ID token is refreshed.

### `BILLING_STATE_MACHINE_ARN not configured` in billing consumer logs

The `CheckoutBillingStateMachine` wasn't deployed. Confirm it exists:

```bash
aws stepfunctions list-state-machines --query "stateMachines[].name"
```

If missing, redeploy; the root `template.yaml` defines both `CheckoutBillingStateMachine` and `HousekeepingDispatchStateMachine`.

### Events arrive but no folio is created

Check the reservation.created payload. The consumers (`src/pms/billing/process_event.py` and `src/pms/housekeeping/process_event.py`) accept both `camelCase` and `snake_case` keys, but the canonical schema is camelCase (`reservationId`, `propertyId`, `guestId`, `checkInDate`, `checkOutDate`, `totalAfterTax`). Check the CloudWatch logs of the consumer Lambda for the skipped record.

### Migration fails: `IAM authentication failed for the role anycompany_admin`

RDS Proxy uses IAM auth, not password. The `run_migration.py` helper handles this automatically — make sure you're not pointing at the direct Aurora endpoint. Use `DBProxyHost` only.

### SQS consumer errors: `does not have permissions to call ReceiveMessage`

Each SQS consumer Lambda has its own IAM role in `template.yaml` with an `SqsConsume` policy scoped to that consumer's specific queue ARN (there is no shared consumer role). Redeploy if a consumer role is out of date.

---

## Teardown

> **Destructive.** Teardown permanently deletes the database, user pool, and all
> stored objects. Only run it against an environment you intend to discard.

This sample ships with **clean-teardown defaults**: the S3 buckets, the Cognito
user pool, and the Aurora cluster all carry `DeletionPolicy: Delete`, and Aurora
`DeletionProtection` defaults to `false`. So `sam delete` removes essentially
everything — with one catch: **S3 will not delete a non-empty bucket**, and the
buckets here are versioned, so their object *versions and delete markers* must be
purged first (a plain `aws s3 rm` leaves those behind and the stack delete fails
with `DELETE_FAILED`).

> **Production note:** if you changed the deletion policies back to `Retain` /
> `Snapshot` and re-enabled `DeletionProtection` for production (recommended —
> see the comments in `stacks/database.yaml`, `stacks/auth.yaml`,
> `stacks/frontend.yaml`, `stacks/analytics.yaml`), then those resources will
> survive `sam delete` by design and you'll clean them up deliberately instead.

### Option A — the teardown script (recommended)

`scripts/teardown.sh` does the whole sequence in the right order: empties every
stack-owned bucket (objects **+ versions + delete markers**), disables Aurora
deletion protection if it's still on, runs `sam delete`, and sweeps the two
secrets that are created out-of-band (so they aren't part of the stack):
`anycompany-booking-stripe-<env>` and `anycompany-booking-testsuite-creds-<env>`.

It is **dry-run by default** — it prints exactly what it would do and changes
nothing. Add `--yes` to execute.

```bash
# Preview (read-only):
scripts/teardown.sh --profile <your-profile> --region us-east-1

# Execute:
scripts/teardown.sh --profile <your-profile> --region us-east-1 --yes
```

Defaults: `--stack anycompany-booking`, `--region us-east-1`, `--profile default`.

### Option B — manual steps

If you'd rather do it by hand, the same sequence is:

```bash
export AWS_PROFILE=<your-profile>
export AWS_REGION=us-east-1

# 1. Empty every stack bucket, INCLUDING versions + delete markers.
#    Find them first:
aws s3 ls | grep -E 'anycompany|pmsfrontend'
#    For each bucket, purge current objects then versions/markers:
aws s3 rm "s3://<BUCKET>" --recursive
aws s3api delete-objects --bucket "<BUCKET>" \
  --delete "$(aws s3api list-object-versions --bucket "<BUCKET>" \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)"
aws s3api delete-objects --bucket "<BUCKET>" \
  --delete "$(aws s3api list-object-versions --bucket "<BUCKET>" \
    --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json)"

# 2. Disable Aurora deletion protection ONLY if it's on (sample default is off):
aws rds describe-db-clusters \
  --query "DBClusters[?starts_with(DBClusterIdentifier,'anycompany')].[DBClusterIdentifier,DeletionProtection]" \
  --output table
aws rds modify-db-cluster --db-cluster-identifier <CLUSTER_ID> \
  --no-deletion-protection --apply-immediately   # only if it showed true

# 3. Delete the stack (also removes the SAM artifacts bucket):
sam delete --stack-name anycompany-booking --region us-east-1   # add --no-prompts for CI

# 4. Sweep the out-of-band secrets (NOT part of the stack):
aws secretsmanager delete-secret --secret-id anycompany-booking-stripe-dev \
  --force-delete-without-recovery
aws secretsmanager delete-secret --secret-id anycompany-booking-testsuite-creds-dev \
  --force-delete-without-recovery
```

`sam delete` removes both the CloudFormation stack and the SAM artifacts S3
bucket (the one named `aws-sam-cli-managed-default-…` or referenced by
`samconfig.toml`).

### Verify it's gone

```bash
aws cloudformation describe-stacks --stack-name anycompany-booking   # should error: stack not found
aws s3 ls | grep anycompany                                          # should be empty
aws rds describe-db-clusters \
  --query "DBClusters[?starts_with(DBClusterIdentifier,'anycompany')]"  # should be []
```

---

## Architecture quick reference

| Component | Tech | Output key |
|---|---|---|
| CRS backend | Lambda + REST API Gateway | `ApiUrl` |
| CRS frontend | React 18 + Vite → S3 + CloudFront | `CloudFrontUrl` |
| PMS backend | Lambda + REST API Gateway | `PmsApiUrl` |
| PMS frontend | React 18 + Vite → S3 + CloudFront | `PmsCloudFrontUrl` |
| Database | Aurora Serverless v2 PostgreSQL + RDS Proxy | `DBProxyHost` |
| Auth | Cognito User Pool | `UserPoolId`, `UserPoolClientId` |
| Events | EventBridge + 4 SQS queues + DLQs | — |
| Workflows | 2 Step Functions state machines (billing, housekeeping) | — |
| Analytics | Firehose → S3 Parquet → Athena | — |
| Activity simulator (opt-in, `DeployActivitySimulator=true`) | Scheduled (every 4h) Lambda — drives 7 phases against CRS + PMS as a dedicated Admin service user | — |

Full architecture: **[HOSPITALITY_PLATFORM_ARCHITECTURE.md](./HOSPITALITY_PLATFORM_ARCHITECTURE.md)**.
