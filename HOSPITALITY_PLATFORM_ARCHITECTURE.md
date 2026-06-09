# Hospitality Technology Platform — Foundation Architecture

> **Purpose**: This document defines the complete architecture for a foundational hospitality technology platform. It exposes APIs for every core hotel system — CRS, PMS, Loyalty, Payments, and more — so that teams can build full websites, agentic AI use-cases, and custom demos on top of a shared, reusable foundation.
>
> **Fictitious Brand**: AnyCompany Hotels & Resorts
>
> **Payment Provider**: Stripe

> **Scope note (design vision vs. what's built):** This document describes the *complete* foundation
> design. Not every component here is implemented — the built systems are CRS, PMS (check-in/out,
> room ops), Housekeeping, Folio/Billing, Loyalty, Guest Profiles, Payments (Stripe), Night Audit,
> Reporting, and Notifications. Components such as Channel Manager, POS, Key/Access Management,
> Group Blocks, Vouchers, and Rate/Revenue Management are **design-only** (API contracts and data
> models, no code). Where a section describes something not yet built, it is marked _design-only_.
> For the authoritative list of implemented events and enums, see the *Implemented Event Catalog*
> in Section 4 and the enum annotations in Section 5; `src/layers/common/models/enums.py` is ground truth.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Real-World Guest Journey](#2-real-world-guest-journey)
3. [Component Breakdown](#3-component-breakdown)
   - 3.1 [Guest Channels](#31-guest-channels)
   - 3.2 [Distribution & Access Layer](#32-distribution--access-layer)
   - 3.3 [Core Hotel Systems](#33-core-hotel-systems)
   - 3.4 [Operational Systems](#34-operational-systems)
   - 3.5 [Finance & Guest Intelligence](#35-finance--guest-intelligence)
   - 3.6 [Infrastructure](#36-infrastructure)
4. [Event Bus & Event Catalog](#4-event-bus--event-catalog)
5. [Data Models](#5-data-models)
6. [API Contracts (per component)](#6-api-contracts-per-component)
7. [Build Order & Dependencies](#7-build-order--dependencies)
8. [Agentic AI Use-Cases](#8-agentic-ai-use-cases)

---

## 1. System Architecture Overview

The platform is organized into **six fundamental layers**, connected by a central **async event bus**. Each layer contains independent services that expose RESTful APIs through a unified API Gateway.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GUEST CHANNELS                                    │
│  Website/App  │  OTAs (Expedia/Booking)  │  GDS/Travel  │  Walk-in/Kiosk  │
└──────┬────────┴────────────┬─────────────┴──────┬───────┴────────┬────────┘
       │                     │                    │                │
┌──────▼─────────────────────▼────────────────────▼────────────────▼────────┐
│                     DISTRIBUTION & ACCESS LAYER                           │
│  Booking Engine  │  Channel Manager  │  API Gateway  │  Webhooks          │
│  Search|Cart|    │  OTA Sync|Inv     │  Auth|Rate    │  Stripe Events|    │
│  Promos|Upsells  │  Push|Mapping     │  Limit|Route  │  OTA Notifs        │
└──────┬───────────┴────────┬──────────┴───────┬──────┴────────────────────┘
       │                    │                  │
┌──────▼────────────────────▼──────────────────▼──────────────────────────┐
│                        CORE HOTEL SYSTEMS                               │
│                                                                         │
│  ┌──────────────────┐   ┌───────────────────┐   ┌──────────────────┐   │
│  │ CRS              │──▶│ PMS               │◀──│ Rate/Revenue     │   │
│  │ (Central Reserv.) │   │ (Property Mgmt)   │   │ Management       │   │
│  │                  │   │                   │   │                  │   │
│  │ Availability     │   │ Check-in/out      │   │ Rate Plans       │   │
│  │ Inventory        │   │ Room Assignment   │   │ Dynamic Pricing  │   │
│  │ Group Blocks     │   │ Night Audit       │   │ Restrictions     │   │
│  │ Overbooking Ctrl │   │ Room Status       │   │ Packages         │   │
│  └────────┬─────────┘   └─────────┬─────────┘   └──────────────────┘   │
└───────────┼─────────────────────── ┼────────────────────────────────────┘
            │                        │
┌───────────▼────────────────────────▼────────────────────────────────────┐
│  Async Event Bus                                                        │
│  reservation.* │ guest.* │ room.* │ charge.* │ payment.*                │
└──┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬─────────────┘
   │      │      │      │      │      │      │      │      │
   ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼
┌──────────────────────────┐  ┌──────────────────────────────────────────┐
│  OPERATIONAL SYSTEMS     │  │  FINANCE & GUEST INTELLIGENCE            │
│                          │  │                                          │
│  Housekeeping            │  │  Folio / Billing ──▶ Stripe Payments     │
│  Tasks|Room Status|Sched │  │  Charges|Taxes|      Pre-auth|Capture|   │
│                          │  │  Split Folios        Refunds             │
│  POS (Point of Sale)  ───┼──┼──▶                                      │
│  Restaurant|Spa|Minibar  │  │  CRM / Guest     ──▶ Loyalty System      │
│                          │  │  Profiles             Points|Tiers|      │
│  Guest Messaging         │  │  Prefs|History|       Redemptions        │
│  Email|SMS|Push          │  │  De-dup                                  │
│                          │  │                                          │
│  Key / Access Mgmt       │  │                                          │
│  Digital Key|Logs        │  │                                          │
└──────────────────────────┘  └──────────────────────────────────────────┘
                         │                    │
┌────────────────────────▼────────────────────▼──────────────────────────┐
│                          INFRASTRUCTURE                                │
│  Auth Service    │  Data Lake       │  Analytics      │  Search      │ │
│  Guest + Staff   │  Event Archive   │  Dashboards     │  Guest       │ │
│  Pools           │                  │  Occ|RevPAR     │  Lookup      │ │
│                  │                  │  ADR             │  Logs        │ │
│                                     Cache                              │
│                                     Availability | Sessions            │
└────────────────────────────────────────────────────────────────────────┘
```

> **Visual Diagram**: A rendered architecture diagram of the implemented platform lives at
> [`docs/img/architecture.png`](./docs/img/architecture.png) (also embedded in the README). The
> ASCII diagram above shows the full conceptual six-layer design, including components that are
> design-only.

---

## 2. Real-World Guest Journey

This traces every system that fires when a guest interacts with AnyCompany Hotel, from discovery through post-stay.

### Step 1 — Discovery & Booking

Sarah finds AnyCompany Hotel on Expedia. Expedia sends a booking request to the **Channel Manager**, which acts as the traffic controller for all third-party distribution. The Channel Manager queries the **CRS** to check real-time availability and rates. The CRS confirms a Deluxe King is available at $249/night — a rate pulled from the **Rate/Revenue Management** system, which set it dynamically based on demand, day-of-week, and competitor pricing. The reservation is confirmed and the CRS pushes it to the **PMS**.

Meanwhile, another guest books directly on anycompanyhotels.com. That request flows through the **Booking Engine** (the direct channel), which also queries the CRS. Direct bookings bypass the Channel Manager — this is why both systems exist: they serve different distribution paths but share the same inventory source.

### Step 2 — Pre-Arrival

Once the reservation lands in the PMS, the **Guest Messaging** system sends a confirmation email. Two days before arrival, it sends a pre-check-in link. The **CRM/Guest Profile** system checks if Sarah has stayed before — she has, and prefers high floors and extra pillows. These preferences are flagged for the front desk. The **Auth service** handles her login to the guest portal.

### Step 3 — Check-In & Room Assignment

Sarah arrives. The PMS handles check-in: assigns room 1204 (high floor, per her profile), triggers **Key/Access Management** to generate a digital key, and notifies **Housekeeping** that 1204 is now "occupied." If the room wasn't ready, Housekeeping would have flagged it as "dirty" or "in-progress," and the PMS would offer a different room.

### Step 4 — During the Stay

Sarah orders room service and visits the spa. Each charge goes through the **POS** — restaurant POS posts $45 dinner, spa POS posts $120 treatment. Both charges flow into the **Folio/Billing** system, which aggregates everything tied to her stay: room charges, taxes, POS charges, minibar, parking.

### Step 5 — Check-Out & Payment

At checkout, the PMS presents the final folio. Sarah confirms. Folio/Billing sends the total to **Stripe Payments**, which processes her card using a PaymentIntent (capturing the pre-authorized hold from check-in). Stripe confirms, the folio is settled, the PMS marks the room as "checked out," and Housekeeping is notified to clean 1204.

### Step 6 — Post-Stay

The **Loyalty** system awards 1,500 points. The **CRM** updates her profile with this visit's preferences and spend. Guest Messaging sends a thank-you email with a feedback survey. All data flows into **Analytics** for revenue analysis.

The **event bus** glues all async communications — when PMS checks someone in, it publishes `checkinout.checked_in`, which Notifications (and, in the full design, Housekeeping, Loyalty, and Key Management) subscribe to independently.

---

## 3. Component Breakdown

### 3.1 Guest Channels

These are the touchpoints where guests interact with your hotel. They are consumers of your APIs, not systems you build from scratch (except the website).

| Component | Description | Why It Matters |
|-----------|-------------|----------------|
| **Website / Mobile App** | Branded direct booking experience. Consumes Booking Engine APIs. | Direct bookings avoid 15-25% OTA commissions. AI concierge/chatbot lives here. |
| **OTAs** (Expedia, Booking.com) | Third-party distribution. Your system speaks their ARI (Availability, Rates, Inventory) format. | Drives discovery. Simulated as external callers hitting Channel Manager APIs. |
| **GDS / Travel Agents** | Global Distribution System used by corporate and travel agent bookings. | Corporate/group business. Feeds through Channel Manager. |
| **Walk-in / Phone** | Front desk and reservations agents create bookings manually. | Bypasses Booking Engine and Channel Manager — goes through API Gateway directly to CRS/PMS. |
| **Self-Service Kiosk** | Lobby kiosk for self-check-in/check-out. | Calls Auth for ID, PMS for check-in, Key API for digital key, Folio for express checkout. |

### 3.2 Distribution & Access Layer

These systems control how bookings reach your core hotel systems and how external consumers access your APIs.

#### Booking Engine

- **What it does**: Powers direct bookings on your website/app. Handles search -> availability -> rate selection -> reservation creation.
- **Key functions**: Room search, availability queries, promo code validation, package bundling, upsell offers, shopping cart, conversion tracking.
- **Why it's separate from CRS**: Booking Engine handles UX concerns (cart, promos, upsells). CRS handles inventory truth. Think of Booking Engine as the "shopping cart" and CRS as the "warehouse."
- **Key APIs**:
  - `POST /search` — Search available rooms by date, guests, room type
  - `GET /availability` — Real-time availability for specific dates
  - `POST /cart` — Add room to cart, apply promo codes
  - `POST /book` — Create reservation from cart
  - `GET /packages` — List available packages and upsells
- **Data model entities**: SearchRequest, SearchResult, Cart, CartItem, PromoCode, Package

#### Channel Manager

- **What it does**: Synchronizes room inventory and rates across all OTAs simultaneously. When a room is booked on Expedia, it immediately reduces availability on Booking.com and all other channels.
- **Key functions**: ARI push/pull, OTA room type mapping, rate plan mapping, booking confirmation relay, inventory sync state tracking.
- **Why it's critical**: Without it, you manually update each OTA — leading to double-bookings. It's the single point that prevents overbooking across distribution channels.
- **Key APIs**:
  - `POST /channels` — Register a new OTA channel
  - `PUT /channels/{id}/mapping` — Map internal room types to OTA room types
  - `POST /channels/{id}/sync` — Trigger inventory sync
  - `GET /channels/{id}/status` — Check sync health
- **Data model entities**: Channel, ChannelMapping, SyncState, ARIUpdate

#### API Gateway

- **What it does**: Unified entry point for ALL API consumers — website, mobile app, third-party integrations, internal tools, AI agents.
- **Key functions**: Authentication (JWT validation), rate limiting, request validation, API versioning, request routing to downstream services.
- **Why it matters for your use-case**: Every new demo or AI agent your team builds just needs an API key — they hit the gateway and access any hotel system.

#### Webhooks / Callbacks

- **What it does**: Receives asynchronous notifications from external systems — Stripe payment confirmations, OTA booking modifications, dispute alerts.
- **Key functions**: Webhook signature validation, idempotent event processing, dead letter queue for failed deliveries, retry logic.
- **Key endpoints**:
  - `POST /webhooks/stripe` — Stripe payment events
  - `POST /webhooks/ota/{channelId}` — OTA booking notifications
- **Data model entities**: WebhookEvent, WebhookDelivery, DeadLetterEntry

### 3.3 Core Hotel Systems

These three systems are the operational backbone. Everything else integrates with them.

#### CRS (Central Reservation System)

- **What it does**: Single source of truth for room inventory, availability, and reservations. Answers the fundamental question: "Is there a room available?"
- **Key functions**:
  - **Availability Engine** — Calculates real-time availability by cross-referencing inventory, existing reservations, group blocks, and out-of-order rooms
  - **Inventory Management** — Room types (Deluxe King, Standard Double, Suite), physical rooms (room 1204), floor plans, connecting rooms
  - **Group Blocks** — Hold 20 rooms for a conference with cutoff dates and pickup tracking
  - **Overbooking Control** — Configurable overbooking percentage per room type based on historical no-show rates
  - **Reservation Lifecycle** — Create, modify, cancel with full audit trail
- **Key APIs**:
  - **Availability**:
    - `GET /availability?checkIn=&checkOut=&adults=&roomType=` — Check availability
  - **Reservations**:
    - `POST /reservations` — Create reservation (includes rate snapshot, currency, channel, loyalty reference, guest count)
    - `GET /reservations/{id}` — Get reservation details (returns full snapshot + FK-resolved references)
    - `PUT /reservations/{id}` — Modify reservation
    - `DELETE /reservations/{id}` — Cancel reservation (accepts cancellationReason, cancellationComment)
    - `GET /reservations?status=&guestId=&checkIn=&channel=` — Search reservations
  - **Reservation add-on services**:
    - `GET /reservations/{id}/services` — List booked add-on services
    - `POST /reservations/{id}/services` — Add service to reservation (e.g., spa, breakfast, airport transfer)
    - `DELETE /reservations/{id}/services/{serviceIdx}` — Remove add-on service
  - **Room inventory**:
    - `POST /inventory/rooms` — Add room to inventory
    - `GET /inventory/roomTypes` — List room types
    - `GET /inventory/roomTypes/{id}` — Get room type details (includes accessibility, smoking, capacity)
    - `PUT /inventory/roomTypes/{id}` — Update room type
  - **Group blocks**:
    - `POST /groups` — Create group block
    - `GET /groups/{id}/pickup` — Track group pickup
- **Data model entities**: Reservation, RoomType, Room, RoomInventory, AvailabilityRecord, GroupBlock, GroupPickup
- **Key events published** (implemented): `reservation.created`, `reservation.modified`, `reservation.cancelled` (source `anycompany.reservations`). _Designed-only: `inventory.updated`, `group.created`._

#### PMS (Property Management System)

- **What it does**: Operational command center for the hotel. Handles everything from the moment a guest arrives until they leave.
- **Key functions**:
  - **Check-in / Check-out** — Guest arrival workflows, ID verification, room assignment, key generation trigger, departure workflows, express checkout
  - **Room Assignment** — Intelligent assignment based on guest preferences (high floor, quiet room, connecting), room status, and optimization
  - **Night Audit** — Daily batch process that: rolls the business date, posts room charges and taxes to folios, reconciles the day's transactions, generates daily reports
  - **Room Status** — Tracks each room's current state: Clean, Dirty, Inspected, Out-of-Order, Out-of-Inventory
  - **Stay Management** — The in-house guest record linking reservation -> room -> folio
- **Key APIs**:
  - **Check-in / Check-out**:
    - `POST /stays/{reservationId}/checkin` — Check in a guest (assigns room, issues digital key, records check-in actuals)
    - `POST /stays/{stayId}/checkout` — Check out a guest
    - `GET /stays/{stayId}` — Get stay details (includes digitalKeyIssued, roomKeysIssued, userSelectedRoom)
    - `GET /stays?guestId=&status=&hotelCode=` — Search stays
  - **Room management**:
    - `PUT /stays/{stayId}/room` — Change room assignment
    - `GET /rooms/{roomNumber}/status` — Get room status
    - `PUT /rooms/{roomNumber}/status` — Update room status
  - **Night audit**:
    - `POST /nightaudit/run` — Trigger night audit
    - `GET /nightaudit/report/{date}` — Get night audit report
  - **Dashboard**:
    - `GET /dashboard/occupancy` — Real-time occupancy
- **Data model entities**: Stay, RoomStatus, NightAuditRun, NightAuditReport, RoomAssignment
- **Key events published** (implemented): `checkinout.checked_in`, `checkinout.checked_out` (source `anycompany.pms`); `audit.night_completed` (source `anycompany.audit`). _Designed-only: `room.status_changed`, `room.assigned`._

#### Rate / Revenue Management

- **What it does**: Controls all pricing strategy — what rate is shown to which guest, on which date, through which channel.
- **Key functions**:
  - **Rate Plans** — BAR (Best Available Rate), corporate negotiated, AAA discount, loyalty member rate, package rates
  - **Dynamic Pricing** — Adjust rates based on occupancy, demand, day-of-week, seasonality, competitor pricing
  - **Restrictions** — Minimum length of stay, maximum stay, closed-to-arrival (CTA), closed-to-departure (CTD)
  - **Packages** — Bundled offerings (room + breakfast, room + spa credit)
  - **Rate Calendar** — Date-level rate overrides and seasonal adjustments
- **Key APIs**:
  - `GET /rates?roomType=&checkIn=&checkOut=&ratePlan=` — Get applicable rate
  - `POST /ratePlans` — Create rate plan
  - `PUT /ratePlans/{id}` — Update rate plan
  - `POST /ratePlans/{id}/overrides` — Set date-level rate overrides
  - `GET /ratePlans/{id}/calendar` — View rate calendar
  - `POST /restrictions` — Set booking restrictions
  - `POST /packages` — Create package
- **Data model entities**: RatePlan, RateOverride, RateRestriction, Package, SeasonalRule, DynamicPricingRule

### 3.4 Operational Systems

These systems handle day-to-day hotel operations, all coordinated by the PMS via the event bus.

#### Housekeeping

- **What it does**: Manages room cleanliness status and cleaning assignments. Without it, the front desk is calling housekeeping on walkie-talkies.
- **Key functions**: Task creation and assignment, room status tracking (Dirty -> Cleaning -> Inspected -> Clean), housekeeper scheduling, priority queue (VIP rooms, early arrivals), supply tracking.
- **Key APIs**:
  - `GET /tasks?status=&assignee=&floor=` — List cleaning tasks
  - `POST /tasks` — Create cleaning task
  - `PUT /tasks/{id}/status` — Update task status
  - `PUT /tasks/{id}/assign` — Assign to housekeeper
  - `GET /schedule/{date}` — View daily schedule
  - `GET /rooms/status/summary` — Room status dashboard
- **Data model entities**: CleaningTask, HousekeeperSchedule, RoomCleaningStatus, SupplyRequest
- **Subscribes to events** (implemented, via SQS consumer): `checkinout.checked_out`, `reservation.created`/`reservation.confirmed`, `reservation.cancelled`

#### POS (Point of Sale)

- **What it does**: Handles all non-room revenue — restaurant, bar, spa, gift shop, parking, minibar. Ancillary revenue can be 30-50% of total hotel revenue.
- **Key functions**: Outlet management, menu/service catalog, charge creation, room charge posting (post to guest folio), direct payment processing, tip handling.
- **Key APIs**:
  - `GET /outlets` — List POS outlets
  - `POST /outlets/{id}/charges` — Create charge
  - `POST /outlets/{id}/charges/{chargeId}/post-to-folio` — Post charge to guest folio
  - `GET /outlets/{id}/menu` — Get outlet menu/services
  - `POST /outlets/{id}/menu/items` — Add menu item
- **Data model entities**: Outlet, MenuItem, POSCharge, POSTransaction
- **Key events published**: `charge.posted` _(designed-only — POS is not implemented)_

#### Guest Messaging

- **What it does**: All guest communications — transactional (confirmation emails, check-in links) and engagement (surveys, marketing, loyalty offers).
- **Key functions**: Template management, multi-channel delivery (email, SMS, push notifications), delivery tracking, preference management (opt-in/opt-out), scheduled sends.
- **Key APIs**:
  - `POST /messages/send` — Send a message
  - `GET /templates` — List message templates
  - `POST /templates` — Create template
  - `GET /messages/{id}/status` — Check delivery status
  - `PUT /preferences/{guestId}` — Update communication preferences
- **Data model entities**: MessageTemplate, Message, DeliveryRecord, CommunicationPreference
- **Subscribes to events** (implemented, via SQS notifications consumer): `reservation.created`/`reservation.confirmed`, `checkinout.checked_in`, `billing.payment_processed`, `loyalty.tier_changed`

#### Key / Access Management

- **What it does**: Controls room access — digital keys (mobile BLE/NFC), traditional key card encoding, and access logging.
- **Key functions**: Key generation, key activation/deactivation tied to stay duration, access log recording, master key management, emergency access override.
- **Key APIs**:
  - `POST /keys/generate` — Generate key for a stay
  - `PUT /keys/{id}/activate` — Activate key
  - `PUT /keys/{id}/deactivate` — Deactivate key
  - `GET /keys/{stayId}` — Get active keys for a stay
  - `GET /access-log/{roomNumber}` — View access log
- **Data model entities**: Key, KeyActivation, AccessLogEntry
- **Subscribes to events**: `checkinout.checked_in`, `checkinout.checked_out`, `room.assigned` _(designed-only — Key/Access is not implemented)_

### 3.5 Finance & Guest Intelligence

#### Folio / Billing

- **What it does**: The financial ledger for each stay. Aggregates all charges and payments. What the guest sees at checkout and what the Stripe charge is based on.
- **Key functions**: Charge posting (room, tax, POS, fees), payment recording, split folios (business on A, personal on B), adjustments/corrections, folio transfer, tax calculation (city, state, tourism, resort fee).
- **Key APIs**:
  - `GET /folios/{stayId}` — Get all folios for a stay
  - `POST /folios/{folioId}/charges` — Post a charge
  - `POST /folios/{folioId}/payments` — Record a payment
  - `POST /folios/{folioId}/adjustments` — Post adjustment
  - `POST /folios/{stayId}/split` — Create split folio
  - `GET /folios/{folioId}/balance` — Get current balance
  - `POST /folios/{folioId}/settle` — Settle folio (triggers Stripe)
- **Data model entities**: Folio, `charges` (the line-item table — modeled below as FolioLineItem), ChargeType, TaxRule, Payment, Adjustment
- **Key events published** (implemented): `billing.payment_processed`, `billing.payment_failed` (source `anycompany.billing`, emitted by the CheckoutBilling state machine). _Designed-only: `folio.charge_posted`, `folio.settled`._
- **Subscribes to events** (implemented, via SQS consumer): `reservation.created`/`reservation.confirmed` (create folio), `reservation.modified`, `reservation.cancelled`, `checkinout.checked_out` (start CheckoutBilling state machine)

#### Stripe Payments

- **What it does**: Payment processing via Stripe. Hospitality payments are more complex than e-commerce.
- **Key functions**:
  - **Pre-authorization** — Authorize $500 hold at check-in (don't capture yet)
  - **Incremental authorization** — Guest extends stay, increase hold
  - **Partial capture** — Final bill was $380, capture only that amount
  - **Split payments** — Part on corporate card, part personal
  - **Refunds** — Early departure, service recovery
  - **Stored payment methods** — Stripe Customer objects for returning guests
- **Key APIs**:
  - **Payment operations**:
    - `POST /payments/authorize` — Pre-authorize card
    - `POST /payments/capture` — Capture authorized amount
    - `POST /payments/charge` — Direct charge
    - `POST /payments/refund` — Process refund
    - `GET /payments/{stayId}` — Get payment history for stay
  - **Stored payment methods**:
    - `POST /payment-methods/{guestId}` — Store payment method
    - `GET /payment-methods/{guestId}` — List stored payment methods for guest
    - `DELETE /payment-methods/{paymentMethodId}` — Remove stored payment method
  - **Vouchers & discount codes**:
    - `POST /vouchers` — Create voucher
    - `GET /vouchers/{id}` — Get voucher details
    - `PUT /vouchers/{id}` — Update voucher
    - `POST /vouchers/validate` — Validate voucher code (check validity, remaining uses, applicable dates)
    - `GET /vouchers?status=&code=` — Search vouchers
- **Data model entities**: PaymentAuthorization, PaymentCapture, PaymentRefund, StoredPaymentMethod, Voucher
- **Stripe objects used**: Customer, PaymentIntent, PaymentMethod, Refund, SetupIntent
- **Key events published** (implemented): `payment.captured`, `payment.refunded` (source `anycompany.payments`). _Designed-only: `payment.authorized`._

#### CRM / Guest Profiles

- **What it does**: Centralized guest database. Merges data from every touchpoint — reservations, stays, loyalty, messaging, POS spending. A guest might book under different emails or through different channels; the CRM de-duplicates into a golden profile.
- **Key functions**: Profile creation and merge, preference tracking (room type, pillow, dietary, floor), stay history aggregation, spend analysis, communication history, de-duplication logic, email/phone verification tracking, multi-line address management.
- **Key APIs**:
  - `GET /guests` — List guest directory (PMS API). Supports `?q=` (name/email search), `?tier=DIAMOND|GOLD|SILVER|NONE`, `?sort=name|recent`, `?page=`, `?limit=` (max 200). Returns guest + loyalty + last/next stay context per row.
  - `GET /guests/{id}` — Get guest profile (includes emailVerified, phoneVerified, full address)
  - `POST /guests` — Create guest profile
  - `PUT /guests/{id}` — Update profile
  - `PUT /guests/{id}/address` — Update guest address
  - `POST /guests/search` — Search guests
  - `POST /guests/merge` — Merge duplicate profiles
  - `GET /guests/{id}/history` — Get stay history
  - `GET /guests/{id}/preferences` — Get preferences
  - `PUT /guests/{id}/preferences` — Update preferences
- **Data model entities**: GuestProfile (with emailVerified, phoneVerified, multi-line address), GuestPreference, StayHistory, SpendSummary, MergeRecord
- **Events**: the Guest/CRM domain _publishes_ `guest.created`, `guest.updated` (source `anycompany.guest`). A dedicated CRM event consumer (subscribing to stay/payment events to aggregate history) is part of the design but not implemented.

#### Loyalty System

- **What it does**: Points, tiers, rewards, and redemptions. Drives repeat business and direct bookings. Supports multiple loyalty programs, paid membership billing, point transfers between programs, and tier-qualifying activity tracking.
- **Key functions**: Program management, points earning (base + bonus rules), tier management (Silver, Gold, Diamond — the `LoyaltyTier` enum is `NONE | SILVER | GOLD | DIAMOND`) with automatic upgrade/downgrade, redemption flows (free night, upgrade, experience), partner earning, point transfers between programs, member-exclusive rates, paid membership billing.
- **Key APIs**:
  - **Programs (master reference)**:
    - `GET /loyalty/programs` — List loyalty programs
    - `POST /loyalty/programs` — Create loyalty program
    - `GET /loyalty/programs/{programId}` — Get program details
    - `PUT /loyalty/programs/{programId}` — Update program
  - **Membership profiles**:
    - `GET /loyalty/{guestId}` — Get loyalty profile for a guest
    - `POST /loyalty/enroll` — Enroll guest in loyalty program
    - `PUT /loyalty/{loyaltyId}` — Update loyalty profile
    - `GET /loyalty/{loyaltyId}/expirations` — Get upcoming point expirations
  - **Transactions**:
    - `POST /loyalty/{loyaltyId}/earn` — Award points
    - `POST /loyalty/{loyaltyId}/redeem` — Redeem points
    - `GET /loyalty/{loyaltyId}/transactions` — Transaction history (filters: type, dateRange, category)
    - `POST /loyalty/{loyaltyId}/adjust` — Manual point adjustment
  - **Transfers**:
    - `POST /loyalty/transfers` — Transfer points between programs/members
    - `GET /loyalty/transfers/{transferId}` — Get transfer details
  - **Tiers & Rules**:
    - `GET /loyalty/programs/{programId}/tiers` — List tier definitions for a program
    - `POST /loyalty/programs/{programId}/tiers` — Create tier
    - `PUT /loyalty/programs/{programId}/tiers/{tierId}` — Update tier
    - `GET /loyalty/programs/{programId}/earning-rules` — List earning rules
    - `POST /loyalty/programs/{programId}/earning-rules` — Create earning rule
  - **Offers**:
    - `GET /loyalty/{loyaltyId}/offers` — Personalized offers
- **Data model entities**: LoyaltyProgram, LoyaltyProfile, LoyaltyTransaction, Tier, EarningRule, LoyaltyOffer, PointTransfer
- **Key events published** (implemented): `loyalty.points_earned`, `loyalty.points_redeemed`, `loyalty.points_adjusted`, `loyalty.tier_changed` (source `anycompany.loyalty`).
- **Subscribes to events** (implemented, via SQS consumer): `billing.payment_processed` (earn points on successful checkout payment)

### 3.6 Infrastructure

These are the cross-cutting concerns that every service depends on. The specific technology choices (managed services, open-source, etc.) should be decided at build time.

| Component | Purpose |
|-----------|---------|
| **Auth Service** | One Cognito user pool shared by guests and staff. Staff authorization is by Cognito group (Admin, Manager, RegionalManager, RevenueManager, FrontDesk, Housekeeping); guests have no staff group. Issues JWT tokens validated by a Cognito user-pool authorizer on each REST API. An M2M (client-credentials) app client also exists for service-to-service tokens. |
| **Event Bus** | Async pub/sub messaging that decouples all services. Each service publishes domain events; other services subscribe to the events they care about. |
| **Data Lake** | All events are archived for historical querying and analytics. |
| **Analytics / BI** | Business intelligence dashboards: Occupancy %, ADR (Average Daily Rate), RevPAR (Revenue Per Available Room), channel performance, guest satisfaction. |
| **Search** | Guest profile search (fuzzy name matching for de-duplication), reservation search, audit log search. |
| **Cache** | Availability cache (hot path for search), session management, rate cache for frequently accessed rate plans. |

---

## 4. Event Bus & Event Catalog

The event bus is the central nervous system. It decouples all services and makes the platform extensible — new use-cases just subscribe to events.

### Event Naming Convention

EventBridge events carry two distinct fields. The platform sets them as:

```
Source:     anycompany.{domain}     (e.g. anycompany.reservations, anycompany.pms)
DetailType: {entity}.{action}       (e.g. reservation.created, checkinout.checked_out)
```

Detail payloads are **camelCase** (e.g. `reservationId`, `propertyId`, `checkInDate`). The PMS
consumers also accept snake_case for backwards compatibility with older archived events.

### Implemented Event Catalog

These events are emitted by the current code (Python handlers via `utils.events.publish_event`,
plus the two Step Functions state machines). `Source` is the EventBridge source; `DetailType`
is the event name.

| DetailType | Source | Publisher | Payload (key fields) | Consumers (real) |
|------------|--------|-----------|----------------------|------------------|
| `reservation.created` | `anycompany.reservations` | CRS | reservationId, guestId, propertyId, roomTypeId, checkInDate, checkOutDate, totalAfterTax | Billing (create folio), Housekeeping (create task), Notifications (confirmation) |
| `reservation.modified` | `anycompany.reservations` | CRS | reservationId, changes | Billing |
| `reservation.cancelled` | `anycompany.reservations` | CRS | reservationId, guestId | Billing, Housekeeping |
| `checkinout.checked_in` | `anycompany.pms` | PMS | reservationId, guestId, propertyId, roomNumber | Notifications |
| `checkinout.checked_out` | `anycompany.pms` | PMS | reservationId, guestId, propertyId, roomId, roomNumber | Billing (CheckoutBilling SM), Housekeeping (HousekeepingDispatch SM) |
| `billing.payment_processed` | `anycompany.billing` | CheckoutBilling state machine | reservationId, folioId, guestId, propertyId, totalAmount | Loyalty (earn points), Notifications (receipt) |
| `billing.payment_failed` | `anycompany.billing` | CheckoutBilling state machine | reservationId, folioId, reason | (alarmed; no consumer) |
| `housekeeping.room_ready` | `anycompany.housekeeping` | HousekeepingDispatch state machine | roomId, roomNumber, propertyId | (Analytics archive) |
| `audit.night_completed` | `anycompany.audit` | PMS night audit | propertyId, auditDate, totalRevenue, roomsOccupied | (Analytics archive) |
| `guest.created` | `anycompany.guest` | Guest/CRM | guestId, email | (Analytics archive) |
| `guest.updated` | `anycompany.guest` | Guest/CRM | guestId | (Analytics archive) |
| `payment.captured` | `anycompany.payments` | Payment | paymentId, reservationId, capturedAmount, paymentIntentId | (Analytics archive) |
| `payment.refunded` | `anycompany.payments` | Payment | paymentId, refundAmount, reason | (Analytics archive) |
| `loyalty.points_earned` | `anycompany.loyalty` | Loyalty | guestId, points, balance | (Analytics archive) |
| `loyalty.points_redeemed` | `anycompany.loyalty` | Loyalty | guestId, points, redemptionType | (Analytics archive) |
| `loyalty.points_adjusted` | `anycompany.loyalty` | Loyalty | guestId, points, reason | (Analytics archive) |
| `loyalty.tier_changed` | `anycompany.loyalty` | Loyalty | guestId, previousTier, newTier | Notifications |

> All events also flow to the Firehose → S3 analytics archive via the event bus. "(Analytics
> archive)" means no domain consumer subscribes today — the event is emitted and archived.

### Designed (not yet emitted)

These events appear in the component sections above as part of the full design vision but are
**not emitted by the current code**. They belong to components that are designed-only (Channel
Manager, POS, Key/Access, Group Blocks) or to flows that were folded into the billing/housekeeping
state machines: `inventory.updated`, `group.created`, `room.status_changed`, `room.assigned`,
`charge.posted`, `folio.charge_posted`, `folio.settled`, `payment.authorized`.

---

## 5. Data Models

Below are the foundational data models for each system, derived from real-world standard hospitality objects
(AWS Connect Customer Profiles: Hotel Reservation, Hotel Stay Revenue, Loyalty, and Loyalty Transaction).
Each model is **normalized to its owning system** — no field is duplicated across systems. Cross-system
relationships use FK references. Where intentional denormalization is needed (e.g., the rate booked at
reservation time), these are marked as **[SNAPSHOT]** — a historical fact frozen at the time of the event.

> **Design pattern — Snapshot vs Reference:**
> - **SNAPSHOT fields** capture a point-in-time value that must never change (e.g., `bookedRatePlanCode` on a Reservation records what rate was booked, even if the RatePlan master record is later modified).
> - **FK references** always point to the live/current version in the owning system (e.g., `guestId → GuestProfile` always resolves to the guest's current profile).
> - **Source mapping**: Each field group notes which AWS standard object it was derived from: `[SRC: hotelReservation]`, `[SRC: hotelStayRevenue]`, `[SRC: loyalty]`, `[SRC: loyaltyTransaction]`.

### 5.1 Room Inventory (CRS)

```
RoomType
├── roomTypeId (PK)
├── code (e.g., "DLX_KING", "STD_DBL", "STE_PRES")          [SRC: hotelReservation → Room.TypeCode]
├── name (e.g., "Deluxe King")                                [SRC: hotelReservation → Room.TypeName]
├── description                                                [SRC: hotelReservation → Room.TypeDesc]
├── maxOccupancy                                               [SRC: hotelReservation → Room.Capacity]
├── bedConfiguration (e.g., "1 King" or "2 Queen")
├── baseRate
├── accessibilityType                                          [SRC: hotelReservation → Room.AccessibilityType]
├── smokingAllowed                                             [SRC: hotelReservation → Room.SmokingAllowed]
├── amenities[] (e.g., ["balcony", "ocean_view", "minibar"])
├── imageUrls[]
├── sortOrder
├── isActive
├── createdAt / updatedAt

Room
├── roomId (PK)
├── roomNumber (e.g., "1204")                                  [SRC: hotelReservation → Room.Number]
├── roomTypeId (FK → RoomType)
├── floor
├── wing (e.g., "North Tower")
├── status (CLEAN | DIRTY | INSPECTED | OUT_OF_ORDER | OUT_OF_INVENTORY)   ── base CRS inventory status (RoomStatus)
│        PMS operations use an extended set (PmsRoomStatus):
│        AVAILABLE | OCCUPIED | DIRTY | CLEANING | INSPECTING | OUT_OF_ORDER
├── isConnecting
├── connectingRoomId
├── features[] (e.g., ["high_floor", "corner", "ada_accessible"])
├── lastCleanedAt
├── createdAt / updatedAt

AvailabilityRecord
├── roomTypeId (PK)
├── date (SK)
├── totalInventory
├── sold
├── blocked (group blocks, out-of-order)
├── available (computed: totalInventory - sold - blocked)
├── overbookingAllowance
├── updatedAt
```

### 5.2 Reservation (CRS)

> Derived from `[SRC: hotelReservation]`. Guest contact info (phone, email) lives on GuestProfile.
> Loyalty info lives on Loyalty system. Payment details live on Payment system.
> Each is referenced via FK — not duplicated here.

```
Reservation
├── reservationId (PK)                                         [SRC: ReservationId]
├── confirmationNumber                                         [SRC: ConfirmationNumber]
├── guestId (FK → GuestProfile)                                [SRC: PreferenceRef → resolves to guest]
├── roomTypeId (FK → RoomType)                                 [SRC: Room.TypeCode → FK to master]
├── ratePlanId (FK → RatePlan)                                 [SRC: RatePlan.Code → FK to master]
├── loyaltyMembershipId (FK → LoyaltyProfile, nullable)        [SRC: Loyalty.MembershipId → FK, not duplicated]
├── paymentMethodId (FK → StoredPaymentMethod)                 [SRC: Payment → FK, not duplicated]
├── groupBlockId (FK → GroupBlock, nullable)                    [SRC: GroupId]
│
│   ── Booking Details ──
├── status (CONFIRMED | CHECKED_IN | CHECKED_OUT | CANCELLED | NO_SHOW)  [SRC: Status]
├── tripType (LEISURE | BUSINESS | GROUP | OTHER)              [SRC: TripType]
├── brandCode                                                  [SRC: BrandCode]
├── hotelCode                                                  [SRC: HotelCode]
├── numberOfNights                                             [SRC: NumberOfNights]
├── numberOfGuests                                             [SRC: NumberOfGuests]
├── adults                                                     [SRC: Guests.Adults]
├── children                                                   [SRC: Guests.Children]
├── sameDayBooking                                             [SRC: SameDayRate]
├── reserver                                                   [SRC: Reserver — flag: is this profile the reserver?]
├── additionalNotes                                            [SRC: AdditionalNote]
│
│   ── Rate Snapshot [SNAPSHOT — frozen at booking time] ──
├── bookedRatePlanCode                                         [SRC: RatePlan.Code — SNAPSHOT]
├── bookedRatePlanName                                         [SRC: RatePlan.Name — SNAPSHOT]
├── bookedRatePlanDescription                                  [SRC: RatePlan.Description — SNAPSHOT]
├── amountPerNight                                             [SRC: AmountPerNight — SNAPSHOT]
├── totalAmountBeforeTax                                       [SRC: TotalAmountBeforeTax — SNAPSHOT]
├── totalAmountAfterTax                                        [SRC: TotalAmountAfterTax — SNAPSHOT]
├── depositAmount
├── refundable                                                 [SRC: Refundable]
├── guaranteeType (CREDIT_CARD | DEPOSIT | CORPORATE)
│
│   ── Currency [SNAPSHOT — booked currency] ──
├── currencyCode                                               [SRC: Currency.Code — SNAPSHOT]
├── currencyName                                               [SRC: Currency.Name — SNAPSHOT]
├── currencySymbol                                             [SRC: Currency.Symbol — SNAPSHOT]
│
│   ── Room Snapshot [SNAPSHOT — booked room type] ──
├── bookedRoomTypeCode                                         [SRC: Room.TypeCode — SNAPSHOT]
├── bookedRoomTypeName                                         [SRC: Room.TypeName — SNAPSHOT]
│
│   ── Loyalty Snapshot [SNAPSHOT — tier at booking time] ──
├── bookedLoyaltyTier                                          [SRC: Loyalty.Tier — SNAPSHOT of tier when booked]
├── bookedLoyaltyProgramName                                   [SRC: Loyalty.ProgramName — SNAPSHOT]
│
│   ── Check-In / Check-Out Preferences ──
├── checkInDate                                                [SRC: CheckIn.Date]
├── earlyCheckInRequested                                      [SRC: CheckIn.Early]
├── lateCheckInRequested                                       [SRC: CheckIn.Late]
├── checkOutDate                                               [SRC: Checkout.Date]
├── earlyCheckOutRequested                                     [SRC: Checkout.Early]
├── lateCheckOutRequested                                      [SRC: Checkout.Late]
├── selfCheckOutRequested                                      [SRC: Checkout.Self]
│
│   ── Channel ──
├── channel
│   ├── creationChannelId                                      [SRC: Channel.CreationChannelId]
│   ├── lastUpdatedChannelId                                   [SRC: Channel.LastUpdatedChannelId]
│   └── method (WEB | MOBILE_APP | PHONE | GDS | OTA | WALKIN) [SRC: Channel.Method]
├── channelReservationId (OTA's confirmation number)
│
│   ── Cancellation ──
├── cancellationReason                                         [SRC: Cancellation.Reason]
├── cancellationComment                                        [SRC: Cancellation.Comment]
├── cancellationCharge                                         [SRC: CancellationCharge]
├── cancelledAt
│
│   ── Add-On Services (booked at reservation time) ──
├── services[]                                                 [SRC: Services list]
│   ├── serviceType (e.g., "spa", "breakfast", "airport_transfer") [SRC: Service.ServiceType]
│   ├── description                                            [SRC: Service.Description]
│   └── cost                                                   [SRC: Service.Cost]
│
│   ── Audit ──
├── contextId                                                  [SRC: ContextId — trace to booking source]
├── transactionId                                              [SRC: TransactionId — payment txn ref]
├── agentId                                                    [SRC: AgentId]
├── processedDate                                              [SRC: ProcessedDate]
├── createdAt                                                  [SRC: CreatedDate]
├── createdBy                                                  [SRC: CreatedBy]
├── updatedAt                                                  [SRC: UpdatedDate]
├── updatedBy                                                  [SRC: UpdatedBy]
├── attributes {}                                              [SRC: Attributes — extensible key-value]
```

> **Normalization notes for Reservation:**
> - `Phone / Email` → NOT stored here. Always resolve via `guestId → GuestProfile.phone / email`.
> - `Payment (card, CVV, etc.)` → NOT stored here. Always resolve via `paymentMethodId → StoredPaymentMethod`.
> - `Loyalty (points, balance)` → NOT stored here. Only a snapshot of tier at booking time is kept. Live loyalty data resolves via `loyaltyMembershipId → LoyaltyProfile`.
> - `Room.Number` → NOT stored here. Assigned at check-in by PMS on the Stay record.
> - `CheckIn.DigitalKey / RoomKeys / UserSelectedRoom` → Operational PMS fields, stored on Stay (see 5.4).

### 5.3 Rate Plans (Rate/Revenue)

> Master rate plan data. The Reservation holds a [SNAPSHOT] of the booked rate — the master record
> here may evolve independently.

```
RatePlan
├── ratePlanId (PK)
├── code (e.g., "BAR", "CORP_ACME", "AAA", "LOYALTY_GOLD")    [SRC: hotelReservation → RatePlan.Code]
├── name                                                       [SRC: hotelReservation → RatePlan.Name]
├── description                                                [SRC: hotelReservation → RatePlan.Description]
├── type (PUBLIC | NEGOTIATED | LOYALTY | PACKAGE | PROMOTIONAL)
├── discountType (PERCENTAGE | FIXED_AMOUNT | ABSOLUTE)
├── discountValue
├── validFrom / validTo
├── restrictions
│   ├── minLengthOfStay
│   ├── maxLengthOfStay
│   ├── closedToArrival (dates[])
│   ├── closedToDeparture (dates[])
│   ├── advancePurchaseDays
│   └── applicableRoomTypes[] (FK → RoomType)
├── cancellationPolicy (FLEXIBLE | MODERATE | STRICT | NON_REFUNDABLE)
├── isActive
├── createdAt / updatedAt

RateOverride
├── ratePlanId (PK)
├── date (SK)
├── roomTypeId
├── overrideAmount (absolute rate for this date)
├── reason (e.g., "holiday_surge", "low_demand_discount")
├── createdBy / createdAt

Package
├── packageId (PK)
├── name (e.g., "Romance Package", "Business Traveler")
├── description
├── ratePlanId (FK → RatePlan)
├── inclusions[] (e.g., ["breakfast_daily", "spa_credit_50", "late_checkout"])
├── inclusionValues{} (e.g., {"spa_credit": 50})
├── imageUrl
├── isActive
├── validFrom / validTo
```

### 5.4 Stay & Folio (PMS)

> **Implementation note:** There is no separate `stays` table. A "stay" is the reservation
> itself once it reaches the PMS — `stayId` is the `reservationId`, and check-in/out actuals
> (room assignment, key flags, actual times) are columns added to `reservations` by the PMS
> integration migrations. The Stay model below is the logical view of those reservation columns.
> Revenue line items are derived from `[SRC: hotelStayRevenue]`.

```
Stay  (logical view over reservations + PMS columns; stayId == reservationId)
├── stayId (PK)                                                [== reservationId]
├── reservationId (FK → Reservation)                           [SRC: hotelStayRevenue → ReservationId]
├── guestId (FK → GuestProfile)                                [SRC: hotelStayRevenue → GuestId]
├── hotelCode                                                  [SRC: hotelStayRevenue → HotelCode]
├── roomNumber (FK → Room)                                     [SRC: hotelReservation → Room.Number — assigned at check-in]
├── startDate                                                  [SRC: hotelStayRevenue → StartDate]
├── checkInTime (actual)
├── checkOutTime (actual)
├── status (CONFIRMED | CHECKED_IN | CHECKED_OUT)              ── reservation status; CONFIRMED == pre-arrival in-house view
├── nightsStayed (computed)
│
│   ── Check-In Actuals (operational PMS data) ──
├── digitalKeyIssued                                           [SRC: hotelReservation → CheckIn.DigitalKey]
├── roomKeysIssued                                             [SRC: hotelReservation → CheckIn.RoomKeys]
├── userSelectedRoom                                           [SRC: hotelReservation → CheckIn.UserSelectedRoom]
│
│   ── Guest Context ──
├── isVIP
├── notes[]
├── createdAt / updatedAt                                      [SRC: hotelStayRevenue → CreatedOn / LastUpdatedOn]
├── createdBy                                                  [SRC: hotelStayRevenue → CreatedBy]
├── updatedBy                                                  [SRC: hotelStayRevenue → LastUpdatedBy]

Folio
├── folioId (PK)
├── stayId (FK → Stay)                                         [== reservationId]
├── folioType (MASTER | SPLIT_A | SPLIT_B | INCIDENTAL)        [DESIGN-ONLY — no folio_type column; split folios not implemented]
├── status (OPEN | PENDING_PAYMENT | PAID | VOID | PAYMENT_FAILED)   [FolioStatus]
├── currencyCode                                               [SRC: hotelStayRevenue → CurrencyCode]
├── currencyName                                               [SRC: hotelStayRevenue → CurrencyName]
├── currencySymbol                                             [SRC: hotelStayRevenue → CurrencySymbol]
├── totalCharges (computed)
├── totalPayments (computed)
├── balance (computed: totalCharges - totalPayments)
├── settledAt
├── createdAt / updatedAt

FolioLineItem  (physical table name: charges)
├── lineItemId (PK)                                            [SRC: hotelStayRevenue → StayRevenueId]
├── folioId (FK → Folio)
├── chargeType (ROOM_RATE | TAX | SERVICE | ADJUSTMENT)        [ChargeType — SRC: hotelStayRevenue → Type]
│              ── (the richer POS_*/PARKING/RESORT_FEE breakdown is design-only; POS is not built)
├── description                                                [SRC: hotelStayRevenue → Description]
├── amount (positive=charge, negative=payment/adjustment)      [SRC: hotelStayRevenue → Amount]
├── quantity
├── postingDate
├── processedDate                                              [SRC: hotelStayRevenue → ProcessedDate]
├── status (POSTED | VOID | ADJUSTED)                          [SRC: hotelStayRevenue → Status]
├── sourceSystem (PMS | POS | PAYMENT_SERVICE | MANUAL)
├── sourceReferenceId (e.g., POSCharge.chargeId or PaymentIntent.id)
├── postedBy
├── createdAt
├── attributes {}                                              [SRC: hotelStayRevenue → Attributes]

TaxRule
├── taxRuleId (PK)
├── name (e.g., "State Sales Tax", "City Hotel Tax", "Tourism Levy")
├── rate (percentage, e.g., 0.0825 for 8.25%)
├── applicableChargeTypes[] (e.g., ["ROOM", "RESORT_FEE"])
├── jurisdiction
├── isActive
├── effectiveFrom / effectiveTo
```

### 5.5 Guest Profile (CRM)

> Owns all guest identity and contact data. The Reservation and Loyalty sources both
> carry phone/email — in our normalized model these live here only, referenced via `guestId` FK.

```
GuestProfile
├── guestId (PK)
├── firstName / lastName
├── email (unique index)                                       [SRC: hotelReservation → EmailAddress, loyalty → EmailAddress]
├── emailVerified                                              [SRC: loyalty → EmailAddressVerified]
├── phone                                                      [SRC: hotelReservation → PhoneNumber, loyalty → PhoneNumber]
├── phoneVerified                                              [SRC: loyalty → PhoneNumberVerified]
├── dateOfBirth
├── nationality
├── language (e.g., "en", "es", "fr")
├── address                                                    [SRC: loyalty → BillingAddress]
│   ├── address1 / address2 / address3 / address4              [SRC: loyalty → BillingAddress.Address1-4]
│   ├── city                                                   [SRC: loyalty → BillingAddress.City]
│   ├── state                                                  [SRC: loyalty → BillingAddress.State]
│   ├── province                                               [SRC: loyalty → BillingAddress.Province]
│   ├── county                                                 [SRC: loyalty → BillingAddress.County]
│   ├── postalCode                                             [SRC: loyalty → BillingAddress.PostalCode]
│   └── country                                                [SRC: loyalty → BillingAddress.Country]
├── identityDocuments[]
│   ├── type (PASSPORT | DRIVERS_LICENSE | ID_CARD)
│   ├── number (encrypted)
│   ├── issuingCountry
│   ├── expiryDate
├── preferences
│   ├── roomType
│   ├── floorPreference (HIGH | LOW | ANY)
│   ├── pillowType (FIRM | SOFT | HYPOALLERGENIC)
│   ├── dietaryRestrictions[]
│   ├── smokingPreference (NON_SMOKING | SMOKING)
│   ├── specialNeeds[]
│   └── customPreferences{}
├── communicationPreferences
│   ├── emailOptIn
│   ├── smsOptIn
│   ├── pushOptIn
│   └── marketingOptIn
├── loyaltyId (FK → LoyaltyProfile)
├── stripeCustomerId
├── totalStays
├── totalSpend
├── lastStayDate
├── vipLevel (NONE | SILVER | GOLD | PLATINUM)
├── tags[] (e.g., ["business_traveler", "anniversary_celebrated", "complaint_history"])
├── mergedFromIds[] (previous duplicate profile IDs)
├── createdAt / updatedAt
```

### 5.6 Loyalty

> Derived from `[SRC: loyalty]` and `[SRC: loyaltyTransaction]`.
> Guest contact info (email, phone, address) is NOT stored here — it lives on GuestProfile.
> Payment info is NOT stored here — it lives on StoredPaymentMethod.

```
LoyaltyProgram (master reference data)
├── programId (PK)                                             [SRC: loyalty → ProgramId]
├── programName                                                [SRC: loyalty → ProgramName]
├── group                                                      [SRC: loyalty → Group]
├── isActive
├── createdAt / updatedAt

LoyaltyProfile
├── loyaltyId (PK)                                             [SRC: loyalty → LoyaltyId]
├── programId (FK → LoyaltyProgram)                            [SRC: loyalty → ProgramId]
├── guestId (FK → GuestProfile)
├── membershipId (e.g., "ANY-1234567")                         [SRC: loyalty → MembershipId]
├── paymentMethodId (FK → StoredPaymentMethod, nullable)       [SRC: loyalty → Payment — FK, not duplicated]
│
│   ── Tier ──
├── currentTier                                                [SRC: loyalty → Tier.CurrentTier]
├── nextTier                                                   [SRC: loyalty → Tier.NextTier]
├── pointsToNextTier                                           [SRC: loyalty → Tier.PointsToNextTier]
├── tierExpiryDate
├── lastUpgradeDate                                            [SRC: loyalty → UpgradeDate]
│
│   ── Points ──
├── pointsUnit                                                 [SRC: loyalty → Points.Unit]
├── pointsBalance                                              [SRC: loyalty → Points.Balance]
├── lifetimePoints                                             [SRC: loyalty → Points.Lifetime]
├── pointsRedeemed                                             [SRC: loyalty → Points.Redeemed]
├── lifetimeNights
├── lifetimeSpend
│
│   ── Point Expirations ──
├── pointExpirations[]                                         [SRC: loyalty → PointExpirations]
│   ├── points                                                 [SRC: PointExpiration.Points]
│   └── expirationDate                                         [SRC: PointExpiration.Date]
│
│   ── Membership Dates ──
├── enrollmentDate                                             [SRC: loyalty → EnrollmentDate]
├── enrollmentChannel                                          [SRC: loyalty → Channel]
├── renewalDate                                                [SRC: loyalty → RenewalDate]
│
│   ── Billing (for paid loyalty programs) ──
├── billing
│   ├── schedule                                               [SRC: loyalty → PaymentInformation.Schedule]
│   ├── lastPaymentDate                                        [SRC: loyalty → PaymentInformation.LastPaymentDate]
│   ├── nextPaymentDate                                        [SRC: loyalty → PaymentInformation.NextPaymentDate]
│   ├── nextBillAmount                                         [SRC: loyalty → PaymentInformation.NextBillAmount]
│   ├── currencyCode                                           [SRC: loyalty → PaymentInformation.CurrencyCode]
│   ├── currencyName                                           [SRC: loyalty → PaymentInformation.CurrencyName]
│   └── currencySymbol                                         [SRC: loyalty → PaymentInformation.CurrencySymbol]
│
│   ── Status & Audit ──
├── status (ACTIVE | SUSPENDED | CLOSED)                       [SRC: loyalty → Status]
├── additionalInformation                                      [SRC: loyalty → AdditionalInformation]
├── createdAt                                                  [SRC: loyalty → CreatedDate]
├── createdBy                                                  [SRC: loyalty → CreatedBy]
├── updatedAt                                                  [SRC: loyalty → UpdatedDate]
├── updatedBy                                                  [SRC: loyalty → LastUpdatedBy]
├── attributes {}                                              [SRC: loyalty → Attributes]

LoyaltyTransaction
├── transactionId (PK)                                         [SRC: loyaltyTransaction → TransactionId]
├── loyaltyId (FK → LoyaltyProfile)                            [SRC: loyaltyTransaction → MembershipRef]
├── programId (FK → LoyaltyProgram)                            [SRC: loyaltyTransaction → ProgramRef]
├── promotionRef                                               [SRC: loyaltyTransaction → PromotionRef]
│
│   ── Transaction Details ──
├── transactionName                                            [SRC: loyaltyTransaction → TransactionName]
├── transactionType (EARN_STAY | REDEEM_NIGHT | ADJUSTMENT)    [LoyaltyTransactionType — SRC: loyaltyTransaction → TransactionType]
├── transactionDate                                            [SRC: loyaltyTransaction → TransactionDate]
├── accrualType (MANUAL | AUTOMATED | PARTNER)                 [SRC: loyaltyTransaction → AccrualType]
├── category (FLIGHT | HOTEL_STAY | DINING | SPA | PARTNER | PROMO) [SRC: loyaltyTransaction → Category]
├── channel                                                    [SRC: loyaltyTransaction → Channel]
├── industry                                                   [SRC: loyaltyTransaction → Industry]
├── location                                                   [SRC: loyaltyTransaction → Location]
├── brand                                                      [SRC: loyaltyTransaction → Brand]
├── productId                                                  [SRC: loyaltyTransaction → ProductId]
├── description                                                [SRC: loyaltyTransaction → Description]
│
│   ── Points ──
├── pointsEarned                                               [SRC: loyaltyTransaction → PointsEarned]
├── pointOffset                                                [SRC: loyaltyTransaction → PointOffset]
├── qualifyingPointsEarned                                     [SRC: loyaltyTransaction → QualifyingPointsEarned]
├── balanceAfter
│
│   ── Monetary Value ──
├── amount                                                     [SRC: loyaltyTransaction → Amount]
├── originValue                                                [SRC: loyaltyTransaction → OriginValue]
├── originValueCurrency                                        [SRC: loyaltyTransaction → OriginValueCurrency]
├── originValueOffset                                          [SRC: loyaltyTransaction → OriginValueOffset]
├── paymentMethod                                              [SRC: loyaltyTransaction → PaymentMethod]
│
│   ── Tier Impact ──
├── tierBefore                                                 [SRC: loyaltyTransaction → TierBefore]
├── tierAfter                                                  [SRC: loyaltyTransaction → TierAfter]
│
│   ── Point Transfer (nullable — only for TRANSFER type) ──
├── pointTransfer                                              [SRC: loyaltyTransaction → PointTransfer]
│   ├── transferId                                             [SRC: PointTransfer.TransferId]
│   ├── sourceProgramId                                        [SRC: PointTransfer.SourceProgramId]
│   ├── destinationProgramId                                   [SRC: PointTransfer.DestinationProgrmId]
│   ├── sourceMembershipId                                     [SRC: PointTransfer.SourceMembershipId]
│   ├── destinationMembershipId                                [SRC: PointTransfer.DestinationMembershipId]
│   ├── pointsTransferred                                      [SRC: PointTransfer.PointsTransferred]
│   └── pointsReceived                                         [SRC: PointTransfer.PointsReceived]
│
│   ── Audit ──
├── status                                                     [SRC: loyaltyTransaction → Status]
├── additionalInformation                                      [SRC: loyaltyTransaction → AdditionalInformation]
├── createdAt                                                  [SRC: loyaltyTransaction → CreatedDate]
├── createdBy                                                  [SRC: loyaltyTransaction → CreatedBy]
├── updatedAt                                                  [SRC: loyaltyTransaction → UpdatedDate]
├── updatedBy                                                  [SRC: loyaltyTransaction → UpdatedBy]
├── attributes {}                                              [SRC: loyaltyTransaction → Attributes]

Tier (master reference data — defines program tier structure)
├── tierId (PK)
├── programId (FK → LoyaltyProgram)
├── name (NONE | SILVER | GOLD | DIAMOND)                       [LoyaltyTier]
├── qualifyingNights (e.g., 0, 10, 25, 50)
├── qualifyingPoints (alternative qualification)
├── benefits[]
│   ├── type (UPGRADE | LATE_CHECKOUT | BREAKFAST | LOUNGE_ACCESS | BONUS_POINTS_MULTIPLIER)
│   ├── description
│   └── value
├── earningMultiplier (e.g., 1.0, 1.25, 1.5, 2.0)
├── sortOrder

EarningRule
├── ruleId (PK)
├── programId (FK → LoyaltyProgram)
├── name
├── source (STAY | DINING | SPA | PROMOTION)
├── pointsPerDollar (e.g., 10)
├── bonusPoints (flat bonus, e.g., 500 for first stay)
├── conditions{}
├── isActive
├── validFrom / validTo
```

### 5.7 Payments (Stripe Integration)

> Owns all payment instrument data. The Reservation and Loyalty sources both embed
> payment card details — in our normalized model these live here only, referenced via
> `paymentMethodId` FK from Reservation and LoyaltyProfile.

```
StoredPaymentMethod
├── paymentMethodId (PK)
├── guestId (FK → GuestProfile)
├── stripePaymentMethodId
├── stripeCustomerId
├── type (CARD | BANK_ACCOUNT | VOUCHER)                       [SRC: hotelReservation → Payment.Type, loyalty → Payment.Type]
├── last4
├── brand                                                      [SRC: hotelReservation → Payment.CreditCardType, loyalty → Payment.CreditCardType]
├── expiryMonth / expiryYear                                   [SRC: hotelReservation → Payment.CreditCardExpiration, loyalty → Payment.CreditCardExpiration]
├── nameOnCard                                                 [SRC: hotelReservation → Payment.NameOnCreditCard, loyalty → Payment.NameOnCreditCard]
├── isDefault
├── createdAt

PaymentAuthorization
├── authorizationId (PK)
├── stayId (FK → Stay)
├── guestId (FK → GuestProfile)
├── stripePaymentIntentId
├── stripeCustomerId
├── amount
├── currency
├── status (AUTHORIZED | CAPTURED | VOIDED | EXPIRED)
├── last4
├── cardBrand
├── expiresAt
├── createdAt / updatedAt

PaymentCapture
├── captureId (PK)
├── authorizationId (FK → PaymentAuthorization)
├── folioId (FK → Folio)
├── capturedAmount
├── stripeChargeId
├── receiptUrl
├── createdAt

PaymentRefund
├── refundId (PK)
├── captureId (FK → PaymentCapture)
├── stripeRefundId
├── amount
├── reason (EARLY_DEPARTURE | SERVICE_RECOVERY | BILLING_ERROR | CANCELLATION)
├── status (PENDING | SUCCEEDED | FAILED)
├── createdAt

Voucher
├── voucherId (PK)                                             [SRC: hotelReservation → Payment.VoucherId, loyalty → Payment.VoucherId]
├── guestId (FK → GuestProfile, nullable)
├── code
├── discountType (PERCENTAGE | FIXED_AMOUNT)
├── discountValue                                              [SRC: hotelReservation → Payment.DiscountPercent]
├── discountCode                                               [SRC: hotelReservation → Payment.DiscountCode]
├── maxUses
├── usedCount
├── validFrom / validTo
├── isActive
├── createdAt
```

> **Normalization notes for Payments:**
> - `CreditCardToken, CVV, RoutingNumber, AccountNumber` from source models are sensitive PCI data.
>   In our system, Stripe tokenizes all of this. We store only `stripePaymentMethodId` — never raw card data.
>   The source fields `[SRC: hotelReservation → Payment.CreditCardToken/Cvv/RoutingNumber/AccountNumber]`
>   and `[SRC: loyalty → Payment.CreditCardToken/Cvv/RoutingNumber/AccountNumber]` are accounted for
>   by Stripe's tokenization layer and are NOT stored in our database.

### 5.8 Housekeeping

```
CleaningTask  (physical table name: housekeeping_tasks)
├── taskId (PK)
├── roomNumber (FK → Room)
├── type (CHECKOUT | PRE_ARRIVAL | MAINTENANCE)                          [TaskType]
├── status (PENDING | ASSIGNED | CLEANING | COMPLETED | INSPECTING | INSPECTED | FAILED)  [TaskStatus]
├── priority (HIGH | NORMAL | LOW)                                       [TaskPriority]
├── assignedTo (housekeeperId)
├── assignedAt
├── startedAt
├── completedAt
├── inspectedBy
├── inspectedAt
├── notes
├── createdAt / updatedAt

HousekeeperSchedule
├── scheduleId (PK)
├── housekeeperId
├── date
├── shift (MORNING | AFTERNOON | EVENING)
├── assignedFloors[]
├── assignedRooms[]
├── status (SCHEDULED | ON_DUTY | OFF_DUTY)
```

### 5.9 POS

```
Outlet
├── outletId (PK)
├── name (e.g., "AnyCompany Restaurant", "Serenity Spa")
├── type (RESTAURANT | BAR | SPA | GIFT_SHOP | PARKING | MINIBAR)
├── location
├── operatingHours
├── isActive

MenuItem
├── menuItemId (PK)
├── outletId (FK → Outlet)
├── name
├── description
├── price
├── category
├── isActive

POSCharge
├── chargeId (PK)
├── outletId (FK → Outlet)
├── stayId (FK → Stay, nullable — walk-in guests pay directly)
├── guestId (FK → GuestProfile)
├── items[]
│   ├── menuItemId
│   ├── quantity
│   ├── unitPrice
│   ├── amount
├── subtotal
├── tax
├── tip
├── total
├── paymentMethod (ROOM_CHARGE | CREDIT_CARD | CASH)
├── folioLineItemId (FK → FolioLineItem, if posted to folio)
├── status (OPEN | POSTED | SETTLED | VOID)
├── createdAt
```

### 5.10 Field Provenance — Complete Source-to-System Mapping

> This table ensures **every field** from the 4 AWS Connect Customer Profiles standard objects
> is accounted for in our normalized model. No field is lost.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ SOURCE: hotelReservation                                                        │
├──────────────────────────────┬──────────────────────────────────────────────────┤
│ Source Field                 │ Normalized Location                              │
├──────────────────────────────┼──────────────────────────────────────────────────┤
│ ReservationId                │ Reservation.reservationId                        │
│ ConfirmationNumber           │ Reservation.confirmationNumber                   │
│ PreferenceRef                │ Reservation.guestId (FK → GuestProfile)          │
│ Status                       │ Reservation.status                               │
│ TripType                     │ Reservation.tripType                             │
│ BrandCode                    │ Reservation.brandCode                            │
│ HotelCode                    │ Reservation.hotelCode                            │
│ PhoneNumber                  │ GuestProfile.phone (via guestId FK)              │
│ EmailAddress                 │ GuestProfile.email (via guestId FK)              │
│ GroupId                      │ Reservation.groupBlockId                         │
│ ContextId                    │ Reservation.contextId                            │
│ ProcessedDate                │ Reservation.processedDate                        │
│ CreatedDate                  │ Reservation.createdAt                            │
│ CreatedBy                    │ Reservation.createdBy                            │
│ UpdatedDate                  │ Reservation.updatedAt                            │
│ UpdatedBy                    │ Reservation.updatedBy                            │
│ AgentId                      │ Reservation.agentId                              │
│ Reserver                     │ Reservation.reserver                             │
│ SameDayRate                  │ Reservation.sameDayBooking                       │
│ Refundable                   │ Reservation.refundable                           │
│ CancellationCharge           │ Reservation.cancellationCharge                   │
│ TransactionId                │ Reservation.transactionId                        │
│ AmountPerNight               │ Reservation.amountPerNight [SNAPSHOT]            │
│ AdditionalNote               │ Reservation.additionalNotes                      │
│ NumberOfNights               │ Reservation.numberOfNights                       │
│ NumberOfGuests               │ Reservation.numberOfGuests                       │
│ TotalAmountBeforeTax         │ Reservation.totalAmountBeforeTax [SNAPSHOT]      │
│ TotalAmountAfterTax          │ Reservation.totalAmountAfterTax [SNAPSHOT]       │
│ Checkout.Early/Late/Self     │ Reservation.earlyCheckOut/lateCheckOut/selfCheckOut│
│ Checkout.Date                │ Reservation.checkOutDate                         │
│ Loyalty.ProgramName          │ Reservation.bookedLoyaltyProgramName [SNAPSHOT]  │
│ Loyalty.MembershipId         │ Reservation.loyaltyMembershipId (FK)             │
│ Loyalty.Tier                 │ Reservation.bookedLoyaltyTier [SNAPSHOT]         │
│ Room.TypeCode/Name/Desc      │ RoomType (master) + Reservation snapshots        │
│ Room.Number                  │ Stay.roomNumber (assigned at check-in)           │
│ Room.Capacity                │ RoomType.maxOccupancy                            │
│ Room.AccessibilityType       │ RoomType.accessibilityType                       │
│ Room.SmokingAllowed          │ RoomType.smokingAllowed                          │
│ CheckIn.Date                 │ Reservation.checkInDate                          │
│ CheckIn.DigitalKey           │ Stay.digitalKeyIssued                            │
│ CheckIn.Early/Late           │ Reservation.earlyCheckIn/lateCheckInRequested    │
│ CheckIn.RoomKeys             │ Stay.roomKeysIssued                              │
│ CheckIn.UserSelectedRoom     │ Stay.userSelectedRoom                            │
│ Payment.*                    │ StoredPaymentMethod (via paymentMethodId FK)      │
│ Payment.DiscountCode/Percent │ Voucher.discountCode / discountValue             │
│ Currency.*                   │ Reservation.currency* [SNAPSHOT]                 │
│ Cancellation.Reason/Comment  │ Reservation.cancellationReason/Comment           │
│ Channel.*                    │ Reservation.channel.*                            │
│ RatePlan.Code/Name/Desc      │ RatePlan (master) + Reservation snapshots        │
│ Guests.Adults/Children       │ Reservation.adults / children                    │
│ Services.*                   │ Reservation.services[]                           │
│ Attributes                   │ Reservation.attributes                           │
├──────────────────────────────┴──────────────────────────────────────────────────┤
│ SOURCE: hotelStayRevenue                                                        │
├──────────────────────────────┬──────────────────────────────────────────────────┤
│ StayRevenueId                │ FolioLineItem.lineItemId                         │
│ CurrencyCode/Name/Symbol     │ Folio.currencyCode/Name/Symbol                   │
│ ReservationId                │ Stay.reservationId (FK, via Folio→Stay)          │
│ GuestId                      │ Stay.guestId (FK)                                │
│ LastUpdatedOn/CreatedOn      │ Stay.updatedAt / createdAt                       │
│ CreatedBy/LastUpdatedBy      │ Stay.createdBy / updatedBy                       │
│ StartDate                    │ Stay.startDate                                   │
│ HotelCode                    │ Stay.hotelCode                                   │
│ Type                         │ FolioLineItem.chargeType                         │
│ Description                  │ FolioLineItem.description                        │
│ Amount                       │ FolioLineItem.amount                             │
│ ProcessedDate                │ FolioLineItem.processedDate                      │
│ Status                       │ FolioLineItem.status                             │
│ Attributes                   │ FolioLineItem.attributes                         │
├──────────────────────────────┴──────────────────────────────────────────────────┤
│ SOURCE: loyalty                                                                 │
├──────────────────────────────┬──────────────────────────────────────────────────┤
│ LoyaltyId                    │ LoyaltyProfile.loyaltyId                         │
│ ProgramId                    │ LoyaltyProgram.programId + LoyaltyProfile FK     │
│ MembershipId                 │ LoyaltyProfile.membershipId                      │
│ ProgramName                  │ LoyaltyProgram.programName                       │
│ Group                        │ LoyaltyProgram.group                             │
│ Channel                      │ LoyaltyProfile.enrollmentChannel                 │
│ CreatedDate/CreatedBy        │ LoyaltyProfile.createdAt / createdBy             │
│ EnrollmentDate               │ LoyaltyProfile.enrollmentDate                    │
│ UpdatedDate/LastUpdatedBy    │ LoyaltyProfile.updatedAt / updatedBy             │
│ UpgradeDate                  │ LoyaltyProfile.lastUpgradeDate                   │
│ RenewalDate                  │ LoyaltyProfile.renewalDate                       │
│ AdditionalInformation        │ LoyaltyProfile.additionalInformation             │
│ EmailAddress/Verified        │ GuestProfile.email / emailVerified (via guestId) │
│ PhoneNumber/Verified         │ GuestProfile.phone / phoneVerified (via guestId) │
│ Status                       │ LoyaltyProfile.status                            │
│ Tier.CurrentTier             │ LoyaltyProfile.currentTier                       │
│ Tier.NextTier                │ LoyaltyProfile.nextTier                          │
│ Tier.PointsToNextTier        │ LoyaltyProfile.pointsToNextTier                  │
│ Points.Unit                  │ LoyaltyProfile.pointsUnit                        │
│ Points.Lifetime              │ LoyaltyProfile.lifetimePoints                    │
│ Points.Balance               │ LoyaltyProfile.pointsBalance                     │
│ Points.Redeemed              │ LoyaltyProfile.pointsRedeemed                    │
│ PointExpirations.*           │ LoyaltyProfile.pointExpirations[]                │
│ Payment.*                    │ StoredPaymentMethod (via paymentMethodId FK)      │
│ PaymentInformation.*         │ LoyaltyProfile.billing.*                         │
│ BillingAddress.*             │ GuestProfile.address.* (via guestId FK)          │
│ Attributes                   │ LoyaltyProfile.attributes                        │
├──────────────────────────────┴──────────────────────────────────────────────────┤
│ SOURCE: loyaltyTransaction                                                      │
├──────────────────────────────┬──────────────────────────────────────────────────┤
│ TransactionId                │ LoyaltyTransaction.transactionId                 │
│ TransactionName              │ LoyaltyTransaction.transactionName               │
│ TransactionType              │ LoyaltyTransaction.transactionType               │
│ ProgramRef                   │ LoyaltyTransaction.programId (FK)                │
│ MembershipRef                │ LoyaltyTransaction.loyaltyId (FK)                │
│ PromotionRef                 │ LoyaltyTransaction.promotionRef                  │
│ CreatedDate/CreatedBy        │ LoyaltyTransaction.createdAt / createdBy         │
│ TransactionDate              │ LoyaltyTransaction.transactionDate               │
│ Industry                     │ LoyaltyTransaction.industry                      │
│ Location                     │ LoyaltyTransaction.location                      │
│ UpdatedDate/UpdatedBy        │ LoyaltyTransaction.updatedAt / updatedBy         │
│ Status                       │ LoyaltyTransaction.status                        │
│ AccrualType                  │ LoyaltyTransaction.accrualType                   │
│ Category                     │ LoyaltyTransaction.category                      │
│ Channel                      │ LoyaltyTransaction.channel                       │
│ ProductId                    │ LoyaltyTransaction.productId                     │
│ Amount                       │ LoyaltyTransaction.amount                        │
│ OriginValue/Currency/Offset  │ LoyaltyTransaction.originValue/Currency/Offset   │
│ PointsEarned                 │ LoyaltyTransaction.pointsEarned                  │
│ PointOffset                  │ LoyaltyTransaction.pointOffset                   │
│ QualifyingPointsEarned       │ LoyaltyTransaction.qualifyingPointsEarned        │
│ TierBefore / TierAfter       │ LoyaltyTransaction.tierBefore / tierAfter        │
│ Brand                        │ LoyaltyTransaction.brand                         │
│ Description                  │ LoyaltyTransaction.description                   │
│ AdditionalInformation        │ LoyaltyTransaction.additionalInformation         │
│ PaymentMethod                │ LoyaltyTransaction.paymentMethod                 │
│ PointTransfer.*              │ LoyaltyTransaction.pointTransfer.*               │
│ Attributes                   │ LoyaltyTransaction.attributes                    │
└──────────────────────────────┴──────────────────────────────────────────────────┘
```

---

## 6. API Contracts (per component)

All APIs follow these conventions:

```
Base URL: https://api.anycompanyhotels.com/v1

Authentication: Bearer JWT (issued by Auth Service)

Headers:
  Authorization: Bearer {token}
  Content-Type: application/json
  X-Property-Id: {propertyId}        # multi-property support
  X-Correlation-Id: {uuid}           # request tracing

Standard Response Envelope:
{
  "success": true,
  "data": { ... },
  "metadata": {
    "requestId": "uuid",
    "timestamp": "ISO8601",
    "pagination": { "page": 1, "limit": 50, "total": 150, "totalPages": 3 }
  }
}

Error Response:
{
  "success": false,
  "error": {
    "code": "ROOM_NOT_AVAILABLE",
    "message": "No rooms available for the requested dates",
    "details": { ... }
  }
}

Standard Error Codes:
  400 — Bad Request (validation errors)
  401 — Unauthorized (missing/invalid token)
  403 — Forbidden (insufficient permissions)
  404 — Not Found
  409 — Conflict (e.g., double-booking)
  422 — Unprocessable Entity (business rule violation)
  429 — Rate Limited
  500 — Internal Server Error
```

> Detailed OpenAPI specs for each component should be generated as you build them. The API signatures listed in Section 3 serve as the starting contracts.

---

## 7. Build Order & Dependencies

Build components in this order. Each phase depends on the previous one.

### Phase 1 — Foundation (build first)

| # | Component | Reason |
|---|-----------|--------|
| 1 | **Auth Service** | Everything needs authentication. Set up Guest and Staff user pools. |
| 2 | **API Gateway** | Unified entry point. Configure routes, authorizers, and CORS. |
| 3 | **Event Bus** | Set up the async messaging backbone. All components will publish/subscribe to it. |

### Phase 2 — Core (the heart)

| # | Component | Depends On | Reason |
|---|-----------|------------|--------|
| 4 | **Room Inventory** (part of CRS) | Auth, API GW | You need rooms before you can sell them. |
| 5 | **Rate Plans** (Rate Manager) | Room Inventory | You need pricing before availability makes sense. |
| 6 | **CRS (Availability + Reservations)** | Room Inventory, Rate Plans | Now you can search, check availability, and create reservations. |
| 7 | **Guest Profile (CRM)** | Auth | Guest records are referenced by everything. |
| 8 | **PMS (Stay + Room Status)** | CRS, Guest Profile | Convert reservations into stays. Check-in/check-out. |
| 9 | **Folio / Billing** | PMS | Attach financial ledger to stays. |
| 10 | **Stripe Payments** | Folio | Process payments. Pre-auth at check-in, capture at checkout. |

### Phase 3 — Operations

| # | Component | Depends On | Reason |
|---|-----------|------------|--------|
| 11 | **Housekeeping** | PMS, Event Bus | Subscribe to check-out events, manage room cleaning. |
| 12 | **POS** | Folio, Guest Profile | Post charges to guest folios. |
| 13 | **Guest Messaging** | CRM, Event Bus | Send transactional emails/SMS on reservation and stay events. |
| 14 | **Key / Access** | PMS, Event Bus | Generate keys on check-in. |

### Phase 4 — Distribution & Intelligence

| # | Component | Depends On | Reason |
|---|-----------|------------|--------|
| 15 | **Booking Engine** | CRS, Rate Manager | Powers direct website bookings. |
| 16 | **Channel Manager** | CRS, Rate Manager | Distributes inventory to OTAs. |
| 17 | **Loyalty** | CRM, Folio, Stripe Payments, Event Bus | Program setup, enrollment, point earning/redemption, tier management, transfers, voucher integration. |
| 18 | **Webhooks** | Stripe, Channel Manager | Receive async callbacks. |

### Phase 5 — Analytics & Optimization

| # | Component | Depends On | Reason |
|---|-----------|------------|--------|
| 19 | **Data Lake** | Event Bus | Archive all events for historical querying. |
| 20 | **Analytics / Reports** | Data Lake | Dashboards and KPIs. |
| 21 | **Night Audit** | PMS, Folio, Rate Manager | Automate daily batch processing. |

---

## 8. Agentic AI Use-Cases

Once the foundation is in place, these AI-powered use-cases become API calls away:

### Conversational Booking Agent
- **Uses**: Booking Engine APIs, CRS APIs, Rate Manager APIs
- **Flow**: Guest says "I need a room for 2 nights next Friday" → Agent calls `/search` → presents options → calls `/book` → confirms via Guest Messaging
- **Value**: 24/7 booking capability, natural language interface

### AI Concierge (In-Stay)
- **Uses**: PMS APIs (stay context), POS APIs (restaurant/spa), Guest Messaging, CRM (preferences)
- **Flow**: Guest texts "Can I get late checkout?" → Agent checks PMS occupancy for tomorrow → approves/denies → updates stay → sends confirmation
- **Value**: Reduces front desk calls, instant guest service

### Revenue Optimization Agent
- **Uses**: Analytics (demand data), Rate Manager APIs, Channel Manager (competitor monitoring)
- **Flow**: Agent detects low occupancy for next Tuesday → adjusts BAR down 15% → pushes new rate to all channels → monitors booking velocity → adjusts again
- **Value**: Dynamic revenue management without manual intervention

### Automated Night Audit Agent
- **Uses**: PMS APIs, Folio APIs, Rate Manager, Analytics
- **Flow**: At 3am, agent runs night audit → posts room charges → calculates taxes → reconciles → generates report → flags discrepancies for human review
- **Value**: Eliminates manual night audit process

### Guest Recovery Agent
- **Uses**: Guest Messaging (survey responses), CRM, Loyalty, Folio
- **Flow**: Detects negative survey response → reads CRM for guest history → determines appropriate recovery (loyalty points, folio credit, or personal outreach) → executes compensation → logs in CRM
- **Value**: Automated service recovery, improved guest satisfaction

### Predictive Housekeeping Agent
- **Uses**: PMS (checkout patterns), Housekeeping APIs, Analytics (historical patterns)
- **Flow**: Predicts which rooms will check out early based on flight data and history → pre-assigns housekeepers → optimizes cleaning sequence → reduces room turnaround time
- **Value**: Faster room availability, better guest experience for early arrivals

---

## Appendix: Quick Reference

### Hotel Industry KPIs (for Analytics)
- **Occupancy Rate** = Rooms Sold / Total Available Rooms
- **ADR** (Average Daily Rate) = Room Revenue / Rooms Sold
- **RevPAR** (Revenue Per Available Room) = Room Revenue / Total Available Rooms (or ADR x Occupancy)
- **GOPPAR** (Gross Operating Profit Per Available Room)
- **TRevPAR** (Total Revenue Per Available Room, includes POS)
- **ALOS** (Average Length of Stay)

### Stripe Integration Cheat Sheet
| Hotel Action | Stripe API | Notes |
|-------------|-----------|-------|
| Check-in pre-auth | `PaymentIntents.create` with `capture_method: 'manual'` | Hold funds without charging |
| Guest extends stay | `PaymentIntents.update` with increased `amount` | Incremental auth |
| Checkout capture | `PaymentIntents.capture` with `amount_to_capture` | Partial capture supported |
| Refund | `Refunds.create` | Can be partial |
| Store card for returning guest | `SetupIntents.create` + `PaymentMethods.attach` to Customer | For faster future stays |
| Recurring / no-show charge | `PaymentIntents.create` with `off_session: true` | Using stored PaymentMethod |

---

> **Next Steps**: Start with Phase 1 (Auth, API Gateway, Event Bus), then work through Phase 2 component by component. Each component should be built as an independent service with its own data store and API routes. Use the event bus for all inter-service communication. Technology choices (database, compute, messaging infrastructure) should be made at build time based on your team's preferences and constraints.
