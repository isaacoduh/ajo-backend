# M1 wallet demo
#
# Prerequisites:
# - API is running locally.
# - Database is migrated: `uv run alembic upgrade head`
# - M1 seed exists: `make seed`
#
# Example:
# hurl --test \
#   --variable base_url=http://localhost:8000 \
#   --variable run_id=local-001 \
#   --variable statement_period=2026-07 \
#   docs/api/demos/m1_wallet.hurl
#
# Use a fresh run_id for each replay so registration gets a fresh email address.
# The money commands below use fixed service-level idempotency keys, so rerunning
# the story does not duplicate the seeded member's top-up or withdrawal.

# 1. Register a fresh demo actor.
# Registration runs screening, creates the member profile, and provisions wallet
# accounts for the new user.
POST {{base_url}}/auth/register
Idempotency-Key: m1-register-{{run_id}}
Content-Type: application/json
{
  "email": "m1.hurl.{{run_id}}@example.com",
  "password": "correct horse battery staple"
}
HTTP 201
[Captures]
registered_access_token: jsonpath "$.access_token"
[Asserts]
jsonpath "$.token_type" == "bearer"
jsonpath "$.user.email" == "m1.hurl.{{run_id}}@example.com"

# 2. Prove the newly registered member has a wallet.
GET {{base_url}}/wallet/balance
Authorization: Bearer {{registered_access_token}}
HTTP 200
[Asserts]
jsonpath "$.currency" == "GBP"
jsonpath "$.available_minor" == 0
jsonpath "$.pending_minor" == 0

# 3. Login as the seeded verified member with available wallet history.
# The seeded member is used for withdrawal because M1 has no public settlement
# endpoint yet; `make seed` creates settled available balance for this account.
POST {{base_url}}/auth/login
Idempotency-Key: m1-login-seeded-{{run_id}}
Content-Type: application/json
{
  "email": "m1.verified.member@example.com",
  "password": "correct horse battery staple"
}
HTTP 200
[Captures]
seeded_access_token: jsonpath "$.access_token"
[Asserts]
jsonpath "$.token_type" == "bearer"
jsonpath "$.user.email" == "m1.verified.member@example.com"

# 4. Read the seeded wallet balance.
GET {{base_url}}/wallet/balance
Authorization: Bearer {{seeded_access_token}}
HTTP 200
[Asserts]
jsonpath "$.currency" == "GBP"

# 5. Create a top-up through FakeRail.
POST {{base_url}}/wallet/topups
Authorization: Bearer {{seeded_access_token}}
Idempotency-Key: m1-wallet-topup-demo
Content-Type: application/json
{
  "amount_minor": 500,
  "currency": "GBP"
}
HTTP 201
[Captures]
topup_id: jsonpath "$.id"
[Asserts]
jsonpath "$.amount_minor" == 500
jsonpath "$.currency" == "GBP"
jsonpath "$.state" == "initiated"

# 6. Withdraw from the seeded available balance through FakeRail.
POST {{base_url}}/wallet/withdrawals
Authorization: Bearer {{seeded_access_token}}
Idempotency-Key: m1-wallet-withdrawal-demo
Content-Type: application/json
{
  "amount_minor": 1000,
  "currency": "GBP"
}
HTTP 201
[Captures]
withdrawal_id: jsonpath "$.id"
[Asserts]
jsonpath "$.amount_minor" == 1000
jsonpath "$.currency" == "GBP"
jsonpath "$.state" == "initiated"

# 7. Show wallet activity after the money commands.
GET {{base_url}}/wallet/activity?limit=10
Authorization: Bearer {{seeded_access_token}}
HTTP 200
[Asserts]
jsonpath "$.items[0].currency" == "GBP"
jsonpath "$.items[0].journal_entry_id" exists

# 8. Show the member statement for the requested period.
GET {{base_url}}/statements/{{statement_period}}
Authorization: Bearer {{seeded_access_token}}
HTTP 200
[Asserts]
jsonpath "$.period" == "{{statement_period}}"
jsonpath "$.currency" == "GBP"
jsonpath "$.journal_entry_ids[0]" exists
