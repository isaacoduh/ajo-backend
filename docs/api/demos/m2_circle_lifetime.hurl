# M2 circle lifetime demo
#
# Prerequisites:
# - API is running locally.
# - Database is migrated: `uv run alembic upgrade head`
# - Use a fresh run_id for each replay.
#
# This story creates an 8-member circle, invites members, records agreements,
# locks the circle, reveals a deterministic payout order, collects the first
# cycle, pays the recipient, injects a late failure, and verifies arrears plus
# shortfall records.
#
# Hurl cannot compute the commit-reveal SHA-256 value from captured member IDs.
# Run once through step 17 with a placeholder commitment if you want to inspect
# member IDs, then compute:
#
#   sha256("{circle_id}:{sorted_member_ids_csv}:{draw_salt}")
#
# Example:
# hurl --test \
#   --variable base_url=http://localhost:8000 \
#   --variable run_id=local-001 \
#   --variable draw_salt=m2-demo-salt \
#   --variable commitment_hash=<sha256> \
#   docs/api/demos/m2_circle_lifetime.hurl

POST {{base_url}}/auth/register
Idempotency-Key: m2-register-owner-{{run_id}}
Content-Type: application/json
{
  "email": "m2.owner.{{run_id}}@example.com",
  "password": "correct horse battery staple",
  "display_name": "M2 Owner"
}
HTTP 201
[Captures]
owner_token: jsonpath "$.access_token"

GET {{base_url}}/auth/me
Authorization: Bearer {{owner_token}}
HTTP 200
[Captures]
owner_member_id: jsonpath "$.member.id"

POST {{base_url}}/circles
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-create-circle-{{run_id}}
Content-Type: application/json
{
  "name": "M2 Lifetime Circle {{run_id}}",
  "contribution_amount_minor": 1000,
  "member_count_target": 8,
  "cycle_count": 8,
  "cadence": "monthly",
  "start_date": "2026-07-30"
}
HTTP 201
[Captures]
circle_id: jsonpath "$.id"
[Asserts]
jsonpath "$.state" == "recruiting"

POST {{base_url}}/auth/register
Idempotency-Key: m2-register-member-2-{{run_id}}
Content-Type: application/json
{"email":"m2.member2.{{run_id}}@example.com","password":"correct horse battery staple","display_name":"M2 Member 2"}
HTTP 201
[Captures]
member2_token: jsonpath "$.access_token"

POST {{base_url}}/circles/{{circle_id}}/invites
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-invite-member-2-{{run_id}}
Content-Type: application/json
{"email":"m2.member2.{{run_id}}@example.com"}
HTTP 201
[Captures]
member2_invite: jsonpath "$.token"

POST {{base_url}}/circles/{{circle_id}}/join
Authorization: Bearer {{member2_token}}
Idempotency-Key: m2-join-member-2-{{run_id}}
Content-Type: application/json
{"token":"{{member2_invite}}"}
HTTP 200

POST {{base_url}}/auth/register
Idempotency-Key: m2-register-member-3-{{run_id}}
Content-Type: application/json
{"email":"m2.member3.{{run_id}}@example.com","password":"correct horse battery staple","display_name":"M2 Member 3"}
HTTP 201
[Captures]
member3_token: jsonpath "$.access_token"

POST {{base_url}}/circles/{{circle_id}}/invites
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-invite-member-3-{{run_id}}
Content-Type: application/json
{"email":"m2.member3.{{run_id}}@example.com"}
HTTP 201
[Captures]
member3_invite: jsonpath "$.token"

POST {{base_url}}/circles/{{circle_id}}/join
Authorization: Bearer {{member3_token}}
Idempotency-Key: m2-join-member-3-{{run_id}}
Content-Type: application/json
{"token":"{{member3_invite}}"}
HTTP 200

# Repeat register/invite/join for members 4-8 in the same shape for a manual
# demo, or use the automated test `test_circle_lifecycle_collects_pays_out...`
# for the full 8-member replay.

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-owner-agreement-{{run_id}}
Content-Type: application/json
{
  "contribution_amount_minor": 1000,
  "cadence": "monthly",
  "start_date": "2026-07-30",
  "payout_rules": {"rule":"commit_reveal_order"}
}
HTTP 200

# After all eight members have joined and agreed:
POST {{base_url}}/circles/{{circle_id}}/lock
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-lock-circle-{{run_id}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/draw/commit
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-draw-commit-{{run_id}}
Content-Type: application/json
{"commitment_hash":"{{commitment_hash}}"}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/draw/reveal
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-draw-reveal-{{run_id}}
Content-Type: application/json
{"salt":"{{draw_salt}}"}
HTTP 200
[Asserts]
jsonpath "$.payout_order[0]" exists

POST {{base_url}}/circles/{{circle_id}}/collect-due
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-collect-due-{{run_id}}
HTTP 200
[Captures]
cycle_id: jsonpath "$.items[0].cycle_id"
late_failure_contribution_id: jsonpath "$.items[3].id"

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-{{run_id}}
HTTP 200
[Asserts]
jsonpath "$.status" == "paid"

POST {{base_url}}/circles/{{circle_id}}/contributions/{{late_failure_contribution_id}}/fail-late
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-fail-late-{{run_id}}
HTTP 200

GET {{base_url}}/circles/{{circle_id}}/records
Authorization: Bearer {{owner_token}}
HTTP 200
[Asserts]
jsonpath "$.arrears_count" == 1
jsonpath "$.shortfall_count" == 1

GET {{base_url}}/circles/{{circle_id}}/ledger
Authorization: Bearer {{owner_token}}
HTTP 200
[Asserts]
jsonpath "$.items[0].journal_entry_id" exists
