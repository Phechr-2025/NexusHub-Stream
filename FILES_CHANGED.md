# Files changed in this revision

## Core runtime / menu

- `menuwed.py`
  - Rebuilt the main CLI
  - Added terminal input bindings to improve Backspace/Delete handling in interactive prompts
  - Reworked the web-info view to print the requested URL/status block with IP URL / Domain URL labels
  - Added best-effort firewall detection for the displayed status block
  - Added reverse-proxy setup for domain binding with nginx on 80/443 when sudo is available
  - Added the missing nginx path constants (`NGINX_SITE_AVAILABLE`, `NGINX_SITE_ENABLED`, `NGINX_SSL_DIR`) so domain binding can create certificates and site configs without a NameError
  - Added automatic certificate issuance via certbot / Let's Encrypt only; no self-signed fallback
  - Added automatic renewal setup for Let's Encrypt certificates
  - Added separate domain reachability vs. TLS-trust checks so the status block can tell the difference between “site is up” and “browser will trust the certificate”
  - Added local and domain health checks so the status block can detect Cloudflare / origin failures more accurately
  - Improved web startup to use the launcher script and verify the local health endpoint
  - Improved status output so it can detect a live server even when the PID file is missing or stale
  - Added root menu items:
    - uninstall
    - update latest
    - update specific tag / URL
    - update libraries
    - manage web
    - manage config
  - Added background web process management with PID file
  - Added best-effort port opening for 80/443 plus the app port when a domain is bound
  - Added safer release updates that sync the release tree, preserve local state, and restart the web if it was running
  - Added no-menu mode for remote / cloud environments

- `menuwed_meta.py`
  - Centralized config helpers
  - Added runtime metadata helpers
  - Added `venv_dir` support
  - Added config generation / syncing helpers

- `menuwed_config.json`
  - Set version fallback to `latest`
  - Added `venv_dir`

## Installers

- `install.sh`
  - Better Linux bootstrap
  - Clearer download / extract / install progress messages
  - Best-effort system dependency check
  - Creates install path and runs `menuwed.py install`
  - Starts the web after install and prints the detailed status block
  - Creates PATH symlink
  - Shows web startup errors and status output instead of hiding them

- `install.ps1`
  - Windows bootstrap
  - Clearer download / extract / install progress messages
  - Downloads latest release
  - Copies files and runs `menuwed.py install`
  - Creates user PATH shim

## App / deploy

- `app.py`
  - Turnstile default changed to non-mandatory
  - This prevents startup crashes when keys are not configured

- `start.sh`
  - Uses the project venv first when available
  - Runs `gunicorn` through the venv Python
  - Falls back to the venv Python directly before system Python

## Environment

- `menuwed_config.json`
  - Expanded to include runtime keys used by the installer and launcher

## Documentation

- `README.md`
  - Rewritten installation and usage instructions

## Notes

- Existing responsive CSS / media playback improvements were kept and the watch page continues to support both video and audio playback.

- Added `import re` to `menuwed.py` to fix `NameError: re is not defined`.
- Improved domain binding to auto-start the web app before applying nginx reverse proxy, reducing `502 Bad Gateway` from an offline upstream.

- `menuwed.py`
  - Added automatic Let's Encrypt renewal setup after successful certificate issuance
  - Added renewal hooks to stop/restart nginx during certbot renew so standalone HTTP-01 can complete
  - Added certbot timer enablement with cron fallback when systemd timer is unavailable
  - Cleaned up proxy removal to delete renewal hooks and cron fallback entries


## OTP / Email / Account Recovery changes in v58 fixed revision

- `app.py`
  - Added `users.email` migration while preserving all existing users
  - Added OTP challenge storage with hashed OTP codes, expiry, attempt limits and server-side resend throttling
  - Added Brevo transactional email sending through `https://api.brevo.com/v3/smtp/email`
  - Added registration email verification flow when email enforcement is enabled
  - Added optional registration email when enforcement is disabled
  - Added account recovery flow: email -> OTP -> new password twice -> automatic redirect to login
  - Added add/change email flow for logged-in users using OTP
  - Added admin direct email viewing/editing without OTP
  - Added per-email account limit enforcement
  - Added admin settings for email enforcement, OTP resend interval, account recovery, email account limit and email-change service
  - Added backup/restore compatibility for the new email column
  - Added latest backup/restore history and automatic safety snapshot before replace-style restore

- `menuwed.py` / `menuwed_meta.py` / `menuwed_config.json`
  - Added Brevo API key, sender email and sender name to `6) จัดการ config`
  - Existing config files retain their values; new keys default to blank and do not expose secrets

- `templates/*`
  - Added Gmail/e-mail field and improved field ordering on registration
  - Added OTP verification and resend UI with countdown
  - Added recovery pages
  - Added add/change email pages
  - Added email display in user account and admin user management
  - Hid the recovery link when the admin disables account recovery

## OTP UX and reliability fixes (v59 - v61)

- `app.py`
  - `send_brevo_otp()`: redesigned the OTP email into a styled dark-themed HTML card (branded header,
    purpose label, expiry/warning notes, footer) instead of a plain unstyled message
  - `send_brevo_otp()`: fixed the OTP code display so it renders as one contiguous string with
    CSS `letter-spacing` only (no literal space characters, no per-digit `<div>`/`<td>` blocks) —
    this fixes two separate problems:
    - the code wrapping onto two lines in the Gmail app on narrow screens (was caused by real
      space characters between digits acting as line-break points)
    - the code splitting into one digit per line when copied to clipboard (was caused by each
      digit being wrapped in a block-level `<div>`)
  - Added `remaining_otp_cooldown_seconds()` helper that computes the *actual* remaining resend
    cooldown based on `last_sent_at`, instead of always showing the full configured cooldown
    (e.g. 60s) every time the OTP page reloads
  - `user_register()`, `recover_otp()`, `user_email_verify()`: now pass the real remaining
    cooldown to the template instead of the fixed base value
  - Added `cancel_url` to all three OTP render calls, and three new routes to support it:
    - `GET /register/cancel` — clears `register_otp_challenge` / `register_pending`
    - `GET /recover/cancel` — clears `recover_otp_challenge` / `recover_verified` / `recover_user_id`
    - `GET /account/email/cancel` — clears `email_otp_challenge` / `email_pending`
    - lets a user who entered the wrong email restart the flow instead of being stuck on the
      OTP screen until it expires

- `templates/verify_otp.html`
  - Fixed the main OTP submit form: it previously had no `action` attribute, so on the
    registration flow it self-submitted back to `/register` instead of `/register/verify`.
    Because `/register` checks for a pending OTP challenge *before* looking at the submitted
    form data, a correct OTP typed in was silently ignored and the same OTP page was
    re-rendered — this was the "entered the right code but it just stays on the same page" bug.
    The form now explicitly posts to the correct verify route per flow
    (`user_register_verify` / `recover_otp` / `user_email_verify`)
  - Added a "กรอกอีเมล/ข้อมูลผิด? ยกเลิกแล้วเริ่มใหม่" (cancel and restart) link that only
    appears when `cancel_url` is provided by the route

## Menu cleanup and OTP flow auto-cancel (v62)

- `templates/base.html`
  - Removed the "ฉันลืมรหัสผ่าน" (forgot password) link from the hamburger side menu.
    The equivalent link on the login page itself (`templates/user_login.html`) was left as-is.

- `app.py`
  - Added `auto_cancel_abandoned_otp_flows()`, a new `before_request` hook that clears a
    pending OTP challenge (register / recover / email-change) the moment the user visits any
    route outside that flow's own set of routes. This fixes two related complaints:
    - Starting registration, reaching the OTP step, then clicking "เข้าสู่ระบบ" (or any other
      menu link) and coming back to `/register` used to still show the OTP screen instead of
      the registration form, because the pending challenge in session never got cleared.
    - Leaving the OTP page for any other page and coming back used to leave the flow "stuck"
      (unable to complete, unable to restart cleanly). Now any navigation away from the
      flow's routes cancels it immediately, so returning to the flow's start always shows a
      fresh form.
  - Defined `REGISTER_FLOW_ENDPOINTS`, `RECOVER_FLOW_ENDPOINTS`, `EMAIL_FLOW_ENDPOINTS` — the
    routes considered part of each flow (start page, verify, resend, cancel, and for recovery
    also the post-verification reset-password page) so normal in-flow navigation (refreshing
    the OTP page, submitting the form, clicking resend) does not get treated as "leaving".
