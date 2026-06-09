# Demo Guide — AnyCompany Hotel

Everything you need to poke at your deployment: how to find your URLs, the seeded logins for the CRS and PMS apps, and Stripe test cards.

> **Test data only.** All users are seeded with fixed passwords and none of this is tied to real identities. The Stripe account is in test mode — no real cards, no real charges.
>
> **Source of truth for passwords:** [`scripts/seed_cognito_users.py`](./scripts/seed_cognito_users.py). If anything below drifts from that file, treat the script as canonical.

## Find your deployment URLs

The CloudFront URLs, API Gateway URLs, and Cognito pool ID are unique to **your**
deployment. After `sam deploy` and seeding (see [DEPLOYMENT.md](./DEPLOYMENT.md)),
print them from your stack outputs:

```bash
aws cloudformation describe-stacks --stack-name anycompany-booking \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl' || OutputKey=='PmsCloudFrontUrl' || OutputKey=='ApiUrl' || OutputKey=='PmsApiUrl' || OutputKey=='UserPoolId'].[OutputKey,OutputValue]" \
  --output table --profile <your-profile> --region us-east-1
```

| Output key | What it is | Audience |
|---|---|---|
| `CloudFrontUrl` | CRS guest booking website | Guests |
| `PmsCloudFrontUrl` | PMS staff dashboard | Hotel staff |
| `ApiUrl` | CRS REST API base URL | Developers |
| `PmsApiUrl` | PMS REST API base URL | Developers |
| `UserPoolId` | Cognito user pool ID | Admin tasks |

Both frontends are hosted on CloudFront. Hard-reload (⌘⇧R or Ctrl+F5) if you see a stale build. Throughout this guide, `<CloudFrontUrl>` / `<PmsCloudFrontUrl>` etc. refer to the values above.

---

## Guest users — CRS website

Sign in at your `CloudFrontUrl`.

| Email | Password | Name | Tier | Points | Stays |
|---|---|---|---|---:|---:|
| `sarah.chen@example.com` | `AnyCompany2026!` | Sarah Chen | DIAMOND | 45,000 | 25 |
| `james.wilson@example.com` | `AnyCompany2026!` | James Wilson | GOLD | 22,000 | 14 |
| `maria.garcia@example.com` | `AnyCompany2026!` | Maria Garcia | GOLD | 15,500 | 11 |
| `david.park@example.com` | `AnyCompany2026!` | David Park | SILVER | 8,200 | 7 |
| `priya.patel@example.com` | `AnyCompany2026!` | Priya Patel | SILVER | 5,100 | 5 |
| `alex.johnson@example.com` | `AnyCompany2026!` | Alex Johnson | NONE | 1,200 | 2 |
| `emma.thompson@example.com` | `AnyCompany2026!` | Emma Thompson | NONE | 450 | 1 |
| `carlos.rivera@example.com` | `AnyCompany2026!` | Carlos Rivera | NONE | 0 | 0 |

Things to try:
- Sign in → search a property → book a room with Stripe test card below.
- View existing reservations under **My Account**.
- Apply promo codes `ANYCOMPANY10` (10% off), `SUMMER25` ($25 off), `WELCOME` (15% off).
- Cancel a reservation and watch the refund.

---

## Staff users — PMS dashboard

Sign in at your `PmsCloudFrontUrl`.

Chain-level users can pick any property from a dropdown on most pages, and use an "All properties (aggregate)" option on the dashboard. Property-scoped users are pinned to their property with no dropdown.

| Email | Password | Role | Scope |
|---|---|---|---|
| `admin@anycompanyhotels.com` | `AnyCompanyAdmin2026!` | Admin | Chain-wide (all 50 properties) |
| `gm.newyork@anycompanyhotels.com` | `AnyCompanyGM2026!` | Manager | The single seeded property |
| `frontdesk@anycompanyhotels.com` | `AnyCompanyFD2026!` | FrontDesk | The single seeded property |
| `housekeeping@anycompanyhotels.com` | `AnyCompanyHK2026!` | Housekeeping | The single seeded property |
| `regional.mgr@anycompanyhotels.com` | `AnyCompanyRegional2026!` | RegionalManager | Northeast region |
| `revenue.mgr@anycompanyhotels.com` | `AnyCompanyRevenue2026!` | RevenueManager | Chain-wide (reporting/analytics) |

> The three property-scoped staff (Manager, FrontDesk, Housekeeping) are all pinned to the **same**
> property — the one passed to `seed_cognito_users.py --property-id`. The seed script does not create
> a second-property user; use `admin@` (chain-wide) to exercise other properties.

Things to try:
- **Dashboard** — occupancy, checked-in count, room status.
- **Stays** — Check In a CONFIRMED reservation, then Check Out a CHECKED_IN one. Closes the folio automatically via the `CheckoutBilling` state machine.
- **Billing** — after a check-out, the folio moves through `OPEN → PENDING_PAYMENT → PAID` with a tax line and a payment record.
- **Housekeeping** — progress a task through Assign → Complete → Pass inspection → room becomes AVAILABLE.
- **Guests** (Admin only) — inspect loyalty tier, points, recent transactions.
- **Reports** — daily operations summary per property, chain-wide occupancy table.
- **Night Audit** (Admin only) — trigger a nightly audit run; view the metrics snapshot.

### What each role can see

- **Admin** — everything, across all properties.
- **Manager** — their property plus reports.
- **FrontDesk** — stays, billing, guests, housekeeping for their property.
- **Housekeeping** — the housekeeping page for their property.
- **RegionalManager** — stays, reports, dashboard for properties in their region.
- **RevenueManager** — dashboard and reports only, chain-wide. No stay/folio edits.

Groups and property scoping are enforced on every backend call via JWT claims (`cognito:groups`, `custom:property_id`, `custom:region`).

---

## Stripe test cards

All in test mode; any future expiry date and any 3-digit CVC.

| Number | Outcome |
|---|---|
| `4242 4242 4242 4242` | Success |
| `4000 0000 0000 0002` | Declined |
| `4000 0000 0000 9995` | Insufficient funds |
| `4000 0025 0000 3155` | Requires 3D Secure authentication |

For the full list, see <https://docs.stripe.com/testing>.

---

## API endpoints (for curious developers)

Reachable with the Cognito ID token in `Authorization: Bearer <token>`. Both APIs return the envelope `{ "success": true, "data": {...} }`.

| API | Base URL |
|---|---|
| CRS | the `ApiUrl` stack output (e.g. `https://<id>.execute-api.us-east-1.amazonaws.com/dev`) |
| PMS | the `PmsApiUrl` stack output |

Public endpoints (no token): `/properties`, `/properties/{id}`, `/properties/{id}/room-types`, `/properties/{id}/room-types/{roomTypeId}`, `/availability`, `/booking/search`, `/booking/rates`, `/booking/cart` (POST), `/booking/cart/{cartId}` (PUT), `/booking/cart/{cartId}/promo` (POST), `/webhooks/stripe`. Everything else is authenticated — note `/booking/cart/{cartId}/book` **requires a token** (it creates the reservation).

---

## Reset your own password

If a demo password doesn't work, it's most often because someone rotated it. To reset as admin:

```bash
# Get your pool ID from the UserPoolId stack output (see "Find your
# deployment URLs" above), then:
aws cognito-idp admin-set-user-password \
  --user-pool-id <UserPoolId> \
  --username <email> \
  --password '<new-password>' \
  --permanent \
  --profile <aws-profile> --region us-east-1
```

To re-seed everyone from scratch, rerun `scripts/seed_cognito_users.py` with `--property-id <id>`. It's idempotent — existing users are skipped.

---

## Data scope — what "this property" means per user

| User | `custom:property_id` | Group | Region |
|---|---|---|---|
| `admin@` | *(none — chain)* | Admin | — |
| `gm.newyork@` | the seeded property's UUID | Manager | — |
| `frontdesk@` | the seeded property's UUID | FrontDesk | — |
| `housekeeping@` | the seeded property's UUID | Housekeeping | — |
| `regional.mgr@` | *(none — regional)* | RegionalManager | Northeast |
| `revenue.mgr@` | *(none — chain)* | RevenueManager | — |

The property name behind each UUID is whatever `properties.name` resolves to in the database; see `/properties` on the CRS API for the live list.
