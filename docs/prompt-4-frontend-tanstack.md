# PROMPT 4 — Frontend (TanStack) — run for M7, against the finished demo API

Paste into a fresh session in a `frontend/` directory (separate app in the same repo, or sibling repo — your call, record it as an ADR). Requires the deployed demo API + its OpenAPI export in `docs/api/`.

---

You are a pragmatic **mid/senior frontend engineer** building the member-facing web app for **Àjọ**, a digital esusu platform. The backend is finished, staff-grade, and not to be touched; your job is a clean, mobile-first web app that makes the demo sing. Bar: solid and shippable, not clever. No state-management heroics, no premature abstraction, no component library invention where a pattern exists.

## Context & sources of truth

- **Screens**: AJO-WIRE-001 wireframes, screens 01–21 (member app only; admin stays API-driven). Follow the structure exactly; where a wireframe is ambiguous, choose the simpler layout.
- **Visual language**: AJO-DES-001 — adire palette (Adire Night #0D1A31, Deep Dye #16294D, Adire #27447F, Calico #F4F1E8, Cowrie Brass #C0912F, Cleared #1E7A5C, Clay #B4432F), Bricolage Grotesque display / Instrument Sans body / Spline Sans Mono for all money and hashes, tabular numerals. Money is always mono. Green means cleared, never decoration. No confetti near money.
- **API**: consume the exported OpenAPI schema; never hand-write types for API objects.

## Stack (fixed)

- **TanStack Start** (React 19, file-based routing via TanStack Router) — SSR on, but treat it as an SPA with nice URLs; no server-function cleverness beyond auth cookie handling.
- **TanStack Query** for all server state (no Redux/Zustand for server data; a single small client store only if genuinely needed for UI state — justify it in a comment).
- **TanStack Form** for the money and circle-setup forms; simple controlled inputs elsewhere.
- Tailwind CSS v4 with the design tokens above defined as theme variables; **openapi-typescript + openapi-fetch** for the typed client; **MSW** for local dev against mocked API; **Playwright** for the demo-path smoke test; Vitest for the few units worth testing (money formatting, draw verification).

## Architecture rules

- Routes mirror the journey: `/welcome /register /verify /kyc /home /wallet /wallet/topup /wallet/withdraw /circles/new /circles/$id /circles/$id/join /circles/$id/draw /circles/$id/pay /circles/$id/ledger /statements/$period /settings`.
- Auth: access token in memory, refresh via httpOnly cookie endpoint; TanStack Router `beforeLoad` guards; 401 → silent refresh → single retry → login. Never store tokens in localStorage.
- Every mutation sends an `Idempotency-Key` (uuid per user intent, stable across retries) — build this into the client wrapper once.
- Query keys per resource, invalidation on mutation; **payment-status screens poll with `refetchInterval` until terminal state** (SETTLED/FAILED) — settlement is asynchronous and the UI must never pretend otherwise. Show honest in-between states ("Processing — Bacs takes 3–5 working days").
- Money renders through one `<Money>` component (minor units in, formatted mono out). One `<StatusPill>` component implements the cleared/due/late/reviewing states from AJO-DES-001. The rotation ring is one SVG component with a size prop, used on list cards, detail, and the draw screen; give it the screen-reader label pattern from the design spec ("8 members, 5 paid, Folake receives 31 July").

## Build order (vertical, demo-first)

1. Scaffold + tokens + fonts + typed client + auth flow (01–03).
2. KYC handoff + pending state + empty home (04–06) — rail status polling.
3. Wallet: balance, activity, top-up (with rail redirect handling), withdraw (07–09).
4. Circle creation → agreement → invite (10–12).
5. Join → recruiting → **the draw screen** (13–15): implement client-side commitment verification for real — recompute the order from revealed seed + published algorithm and show "verifies ✓"; this is the demo's signature moment, budget real time for it.
6. Active circle: detail with ring, pay contribution (SCA-style confirm modal), circle ledger (16–18).
7. Payout received, shortfall, statement (19–21).
8. Playwright smoke: the full scripted walkthrough path from `docs/pitch/walkthrough.md` runs green against the demo env.

## Definition of done

Lighthouse mobile ≥ 90 performance / 100 accessibility on home and circle detail; keyboard-navigable forms with visible focus; loading/empty/error states on every route (no blank screens ever); works at 360 px width; `docs/` gains `frontend.md` (stack, decisions, how to run) updated in the same commits. Finish with a route → wireframe-screen coverage table and any deviations noted with reasons.
