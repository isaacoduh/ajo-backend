# Future Work

This document tracks useful follow-ups that are not blockers for the current milestone. Items here may apply to any product area and should be promoted into milestone tickets when they become delivery priorities.

## Authentication And Accounts

- Add a real forgot-password flow with password reset tokens, email delivery, expiry, and single-use enforcement.
- Add a confirm-password field on the register page to reduce user input mistakes.
- Consider moving browser auth storage from `localStorage` to httpOnly secure cookies before handling higher-risk account or payment actions.
- Add a shared frontend route guard so protected pages do not each need to implement their own session check and redirect behavior.
- Add richer auth form validation and password guidance before submit, while keeping backend validation authoritative.
- Add explicit account/session management UI, including log out of all devices.
- Add frontend tests for login, register, logout, expired-token refresh, and unauthenticated redirect behavior.
- Add deployed-environment smoke tests that verify CORS, login, register, and `/auth/me` from the production frontend origin.
