# Future Work

This document tracks useful follow-ups that are not blockers for the current milestone. Items here may apply to any product area and should be promoted into milestone tickets when they become delivery priorities.

## Authentication And Accounts

- Add a real forgot-password flow with password reset tokens, email delivery, expiry, and single-use enforcement.
- Add email verification before higher-risk account or payment actions.
- Add update-email flow with re-authentication, verification of the new email, and audit logging.
- Add MFA/2FA or passkey support for stronger account protection.
- Add account closure/deactivation flow with ledger-safe retention rules.
- Add user-visible security/audit events for login, logout-all, password change, payout initiation, and sensitive profile changes.
- Add login history with timestamp, IP/request metadata, and approximate device/client details.
- Add KYC profile detail endpoints for regulated profile attributes such as phone, date of birth, residential address, and verification status provenance.
- Add notification preferences for account, payment, security, and circle lifecycle events.
- Add trusted-device management if MFA/passkeys are added.
- Add a confirm-password field on the register page to reduce user input mistakes.
- Consider moving browser auth storage from `localStorage` to httpOnly secure cookies before handling higher-risk account or payment actions.
- Add a shared frontend route guard so protected pages do not each need to implement their own session check and redirect behavior.
- Add richer auth form validation and password guidance before submit, while keeping backend validation authoritative.
- Add explicit account/session management UI, including log out of all devices.
- Add frontend tests for login, register, logout, expired-token refresh, and unauthenticated redirect behavior.
- Add deployed-environment smoke tests that verify CORS, login, register, and `/auth/me` from the production frontend origin.
