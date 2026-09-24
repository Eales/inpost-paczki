# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-24

First release.

### Features

- Browser login to the InPost account (OAuth2 authorization code with PKCE, the
  same flow as the InPost Mobile app), because the login pages require a
  captcha. Home Assistant gets its own device session, so the phone app stays
  logged in. Expired sessions trigger re-authentication.
- Sensors for parcels to collect and parcels on the way, with the full lists in
  attributes, plus the earliest pickup deadline.
- Binary sensor that is `on` while a parcel waits to be collected.
- Calendar of pickup windows, from arrival in the locker to the deadline.
- `Parcel` event entity: `ready_to_pickup`, `delivered`, `new_parcel`,
  `status_changed`.
- `Notification` event entity mirroring the notifications of the InPost app,
  text included.
- Blueprint sending phone notifications when a parcel is ready and before the
  pickup deadline.
- Pickup codes are opt-in; polling interval 1-60 minutes (default 5).
- Polish and English translations; diagnostics with personal data redacted.

### Notes

Found while testing against a live account:

- Without `If-None-Match` the parcel list is complete; the app sends it and gets
  only what changed since, which would make the integration stateful.
- The first refresh runs before the event entities exist. Changes it detects
  (what happened while Home Assistant was down) are announced as soon as the
  entities are added, and several changes in one refresh produce separate
  events.

[0.1.0]: https://github.com/Eales/inpost-paczki/releases/tag/v0.1.0
