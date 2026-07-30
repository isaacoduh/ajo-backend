# M2 circle lifetime demo
#
# Prerequisites:
# - API is running locally.
# - Database is migrated: `uv run alembic upgrade head`
# - Use a fresh run_id for each replay.
#
# This story creates an 8-member circle, invites all members, records all
# agreements, locks the circle, reveals a deterministic payout order, collects
# 64 due contribution obligations, pays all 8 cycles, injects one late failure,
# checks arrears/shortfall, reads ledger/statement views, and completes the
# circle idempotently.
#
# Hurl cannot compute the commit-reveal SHA-256 value from captured member IDs.
# Minimal helper workflow:
# 1. Run this file until the draw commit with `--very-verbose` and capture:
#    circle_id plus owner_member_id and member2_id ... member8_id.
# 2. Compute:
#    sha256("{circle_id}:{sorted_member_ids_csv}:{draw_salt}")
# 3. Replay the full file with `commitment_hash` set to that value.
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
  "start_date": "2020-01-31"
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

GET {{base_url}}/auth/me
Authorization: Bearer {{member2_token}}
HTTP 200
[Captures]
member2_id: jsonpath "$.member.id"

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

GET {{base_url}}/auth/me
Authorization: Bearer {{member3_token}}
HTTP 200
[Captures]
member3_id: jsonpath "$.member.id"

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

POST {{base_url}}/auth/register
Idempotency-Key: m2-register-member-4-{{run_id}}
Content-Type: application/json
{"email":"m2.member4.{{run_id}}@example.com","password":"correct horse battery staple","display_name":"M2 Member 4"}
HTTP 201
[Captures]
member4_token: jsonpath "$.access_token"

GET {{base_url}}/auth/me
Authorization: Bearer {{member4_token}}
HTTP 200
[Captures]
member4_id: jsonpath "$.member.id"

POST {{base_url}}/circles/{{circle_id}}/invites
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-invite-member-4-{{run_id}}
Content-Type: application/json
{"email":"m2.member4.{{run_id}}@example.com"}
HTTP 201
[Captures]
member4_invite: jsonpath "$.token"

POST {{base_url}}/circles/{{circle_id}}/join
Authorization: Bearer {{member4_token}}
Idempotency-Key: m2-join-member-4-{{run_id}}
Content-Type: application/json
{"token":"{{member4_invite}}"}
HTTP 200

POST {{base_url}}/auth/register
Idempotency-Key: m2-register-member-5-{{run_id}}
Content-Type: application/json
{"email":"m2.member5.{{run_id}}@example.com","password":"correct horse battery staple","display_name":"M2 Member 5"}
HTTP 201
[Captures]
member5_token: jsonpath "$.access_token"

GET {{base_url}}/auth/me
Authorization: Bearer {{member5_token}}
HTTP 200
[Captures]
member5_id: jsonpath "$.member.id"

POST {{base_url}}/circles/{{circle_id}}/invites
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-invite-member-5-{{run_id}}
Content-Type: application/json
{"email":"m2.member5.{{run_id}}@example.com"}
HTTP 201
[Captures]
member5_invite: jsonpath "$.token"

POST {{base_url}}/circles/{{circle_id}}/join
Authorization: Bearer {{member5_token}}
Idempotency-Key: m2-join-member-5-{{run_id}}
Content-Type: application/json
{"token":"{{member5_invite}}"}
HTTP 200

POST {{base_url}}/auth/register
Idempotency-Key: m2-register-member-6-{{run_id}}
Content-Type: application/json
{"email":"m2.member6.{{run_id}}@example.com","password":"correct horse battery staple","display_name":"M2 Member 6"}
HTTP 201
[Captures]
member6_token: jsonpath "$.access_token"

GET {{base_url}}/auth/me
Authorization: Bearer {{member6_token}}
HTTP 200
[Captures]
member6_id: jsonpath "$.member.id"

POST {{base_url}}/circles/{{circle_id}}/invites
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-invite-member-6-{{run_id}}
Content-Type: application/json
{"email":"m2.member6.{{run_id}}@example.com"}
HTTP 201
[Captures]
member6_invite: jsonpath "$.token"

POST {{base_url}}/circles/{{circle_id}}/join
Authorization: Bearer {{member6_token}}
Idempotency-Key: m2-join-member-6-{{run_id}}
Content-Type: application/json
{"token":"{{member6_invite}}"}
HTTP 200

POST {{base_url}}/auth/register
Idempotency-Key: m2-register-member-7-{{run_id}}
Content-Type: application/json
{"email":"m2.member7.{{run_id}}@example.com","password":"correct horse battery staple","display_name":"M2 Member 7"}
HTTP 201
[Captures]
member7_token: jsonpath "$.access_token"

GET {{base_url}}/auth/me
Authorization: Bearer {{member7_token}}
HTTP 200
[Captures]
member7_id: jsonpath "$.member.id"

POST {{base_url}}/circles/{{circle_id}}/invites
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-invite-member-7-{{run_id}}
Content-Type: application/json
{"email":"m2.member7.{{run_id}}@example.com"}
HTTP 201
[Captures]
member7_invite: jsonpath "$.token"

POST {{base_url}}/circles/{{circle_id}}/join
Authorization: Bearer {{member7_token}}
Idempotency-Key: m2-join-member-7-{{run_id}}
Content-Type: application/json
{"token":"{{member7_invite}}"}
HTTP 200

POST {{base_url}}/auth/register
Idempotency-Key: m2-register-member-8-{{run_id}}
Content-Type: application/json
{"email":"m2.member8.{{run_id}}@example.com","password":"correct horse battery staple","display_name":"M2 Member 8"}
HTTP 201
[Captures]
member8_token: jsonpath "$.access_token"

GET {{base_url}}/auth/me
Authorization: Bearer {{member8_token}}
HTTP 200
[Captures]
member8_id: jsonpath "$.member.id"

POST {{base_url}}/circles/{{circle_id}}/invites
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-invite-member-8-{{run_id}}
Content-Type: application/json
{"email":"m2.member8.{{run_id}}@example.com"}
HTTP 201
[Captures]
member8_invite: jsonpath "$.token"

POST {{base_url}}/circles/{{circle_id}}/join
Authorization: Bearer {{member8_token}}
Idempotency-Key: m2-join-member-8-{{run_id}}
Content-Type: application/json
{"token":"{{member8_invite}}"}
HTTP 200
[Asserts]
jsonpath "$.member_count" == 8

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-owner-agreement-{{run_id}}
Content-Type: application/json
{"contribution_amount_minor":1000,"cadence":"monthly","start_date":"2020-01-31","payout_rules":{"rule":"commit_reveal_order"}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{member2_token}}
Idempotency-Key: m2-member-2-agreement-{{run_id}}
Content-Type: application/json
{"contribution_amount_minor":1000,"cadence":"monthly","start_date":"2020-01-31","payout_rules":{"rule":"commit_reveal_order"}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{member3_token}}
Idempotency-Key: m2-member-3-agreement-{{run_id}}
Content-Type: application/json
{"contribution_amount_minor":1000,"cadence":"monthly","start_date":"2020-01-31","payout_rules":{"rule":"commit_reveal_order"}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{member4_token}}
Idempotency-Key: m2-member-4-agreement-{{run_id}}
Content-Type: application/json
{"contribution_amount_minor":1000,"cadence":"monthly","start_date":"2020-01-31","payout_rules":{"rule":"commit_reveal_order"}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{member5_token}}
Idempotency-Key: m2-member-5-agreement-{{run_id}}
Content-Type: application/json
{"contribution_amount_minor":1000,"cadence":"monthly","start_date":"2020-01-31","payout_rules":{"rule":"commit_reveal_order"}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{member6_token}}
Idempotency-Key: m2-member-6-agreement-{{run_id}}
Content-Type: application/json
{"contribution_amount_minor":1000,"cadence":"monthly","start_date":"2020-01-31","payout_rules":{"rule":"commit_reveal_order"}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{member7_token}}
Idempotency-Key: m2-member-7-agreement-{{run_id}}
Content-Type: application/json
{"contribution_amount_minor":1000,"cadence":"monthly","start_date":"2020-01-31","payout_rules":{"rule":"commit_reveal_order"}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/agreement
Authorization: Bearer {{member8_token}}
Idempotency-Key: m2-member-8-agreement-{{run_id}}
Content-Type: application/json
{"contribution_amount_minor":1000,"cadence":"monthly","start_date":"2020-01-31","payout_rules":{"rule":"commit_reveal_order"}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/lock
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-lock-circle-{{run_id}}
HTTP 200
[Asserts]
jsonpath "$.state" == "draw_pending"

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
jsonpath "$.payout_order[7]" exists

GET {{base_url}}/circles/{{circle_id}}/contributions
Authorization: Bearer {{owner_token}}
HTTP 200
[Asserts]
jsonpath "$.items[63].id" exists

POST {{base_url}}/circles/{{circle_id}}/collect-due
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-collect-due-{{run_id}}
HTTP 200
[Captures]
cycle1_id: jsonpath "$.items[0].cycle_id"
cycle2_id: jsonpath "$.items[8].cycle_id"
cycle3_id: jsonpath "$.items[16].cycle_id"
cycle4_id: jsonpath "$.items[24].cycle_id"
cycle5_id: jsonpath "$.items[32].cycle_id"
cycle6_id: jsonpath "$.items[40].cycle_id"
cycle7_id: jsonpath "$.items[48].cycle_id"
cycle8_id: jsonpath "$.items[56].cycle_id"
late_failure_contribution_id: jsonpath "$.items[3].id"
[Asserts]
jsonpath "$.items[63].status" == "paid"

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle1_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-1-{{run_id}}
HTTP 200
[Asserts]
jsonpath "$.amount_minor" == 8000
jsonpath "$.status" == "paid"

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle2_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-2-{{run_id}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle3_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-3-{{run_id}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle4_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-4-{{run_id}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle5_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-5-{{run_id}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle6_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-6-{{run_id}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle7_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-7-{{run_id}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/cycles/{{cycle8_id}}/payout
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-payout-cycle-8-{{run_id}}
HTTP 200

POST {{base_url}}/circles/{{circle_id}}/contributions/{{late_failure_contribution_id}}/fail-late
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-fail-late-{{run_id}}
HTTP 200
[Asserts]
jsonpath "$.items[3].status" == "late_failed"

GET {{base_url}}/circles/{{circle_id}}/records
Authorization: Bearer {{owner_token}}
HTTP 200
[Asserts]
jsonpath "$.arrears_count" == 1
jsonpath "$.shortfall_count" == 1
jsonpath "$.arrears_minor" == 1000
jsonpath "$.shortfall_minor" == 1000

GET {{base_url}}/circles/{{circle_id}}/ledger
Authorization: Bearer {{owner_token}}
HTTP 200
[Asserts]
jsonpath "$.items[0].journal_entry_id" exists

GET {{base_url}}/circles/{{circle_id}}/statements/2020-01
Authorization: Bearer {{owner_token}}
HTTP 200
[Asserts]
jsonpath "$.currency" == "GBP"
jsonpath "$.journal_entry_ids[0]" exists

POST {{base_url}}/circles/{{circle_id}}/complete
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-complete-{{run_id}}
HTTP 200
[Asserts]
jsonpath "$.state" == "completed"

POST {{base_url}}/circles/{{circle_id}}/complete
Authorization: Bearer {{owner_token}}
Idempotency-Key: m2-complete-again-{{run_id}}
HTTP 200
[Asserts]
jsonpath "$.state" == "completed"
