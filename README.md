# InPost Paczki

Home Assistant integration for your incoming **InPost** parcels (Poland). It
reads the same account data as the InPost Mobile app: parcels on the way,
parcels waiting in a Paczkomat® or a PaczkoPunkt, pickup deadlines, and the
notifications the app shows.

It exposes this as sensors, a calendar of pickup windows and events. A
ready-made blueprint turns them into phone notifications.

**Requires Home Assistant 2024.11.0 or newer.**

> This is an unofficial integration, not affiliated with or endorsed by InPost.
> It uses the private API of the InPost Mobile app, which can change without
> notice. It only reads data; it never opens lockers or changes anything in
> your account.

## Installation

### HACS (custom repository)

1. HACS > three-dot menu > `Custom repositories`
2. URL: `https://github.com/Eales/inpost-paczki`, category: `Integration`
3. Install **InPost Paczki**, then restart Home Assistant

### Manual

Copy `custom_components/inpost_paczki` into your Home Assistant `config`
directory and restart.

## Configuration

InPost's login pages need a captcha, so the login cannot happen inside Home
Assistant. You log in in your browser and hand Home Assistant the result:

1. `Settings` > `Devices & Services` > `Add Integration` > `InPost Paczki`
2. Open the **InPost login page** link shown in the dialog and log in exactly as
   in the app: phone number, SMS code.
3. The browser lands on a blank or error page at
   `https://account.inpost-group.com/callback?code=...`. That is expected.
   Copy the whole address and paste it into the dialog. The code is valid for a
   short time only, so do it right away.

If the link lets you in without asking for anything, the browser is already
logged in to InPost. Open the link in a private window instead.

Home Assistant registers as one more device of your account, with its own
session, so the app on your phone stays logged in. The session renews itself;
if it ever expires (for example after you log out of all devices), Home
Assistant asks you to log in again.

### Options

Use the integration's `Configure` button to set:

- **Polling interval**: 1-60 minutes, default 5. Each poll makes two small
  requests.
- **Expose pickup codes**: off by default. The code opens the locker compartment,
  and entity attributes are stored in the Home Assistant database, so turn it on
  only if you want the code on a dashboard or in a notification.

## Entities

Each account creates one device.

| Entity | Type | Description |
| --- | --- | --- |
| `Parcels to collect` | sensor | Number of parcels waiting in a locker or a point; the list is in the `parcels` attribute. |
| `Parcels on the way` | sensor | Number of parcels announced or in transit; the list is in `parcels`. |
| `Pickup deadline` | sensor (`timestamp`) | The earliest deadline among parcels waiting to be collected. |
| `Parcel waiting` | binary sensor | `on` while at least one parcel waits to be collected. |
| `Parcel pickups` | calendar | Every waiting parcel as an event from its arrival to its pickup deadline. |
| `Parcel` | event | Fires when a parcel appears or its status changes, see below. |
| `Notification` | event | Fires for every new notification in the InPost app, with its text. |

### Parcel attributes

Every parcel (in the `parcels` lists, on `Pickup deadline`, `Parcel waiting` and
on `Parcel` events) is described by the same flat attributes:

| Attribute | Meaning |
| --- | --- |
| `shipment_number` | Tracking number |
| `sender` | Sender's name |
| `status` | `created`, `in_transit`, `out_for_delivery`, `ready_to_pickup`, `delivered`, `returned` or `other` |
| `status_title` | InPost's own wording of the latest step, e.g. `Gotowa do odbioru` |
| `point_name` | Locker or point code, e.g. `KRA01M` |
| `point_address` | Its address |
| `point_description` | Where exactly it is, as described by InPost |
| `expiry_date` | Pickup deadline |
| `tracking_url` | Link to the public tracking page |
| `open_code` | Pickup code; only with `Expose pickup codes` turned on |

### Events

`Parcel` fires one event per parcel and change, the most specific one:

| Event type | When |
| --- | --- |
| `ready_to_pickup` | The parcel arrived in a locker or a point. |
| `delivered` | The parcel was collected or delivered. |
| `new_parcel` | A parcel appeared in the account (not yet in a locker). |
| `status_changed` | Any other step, e.g. out for delivery or a pickup reminder. |

`Notification` carries `title`, `message`, `shipment_number`, `sender` and
`date`: the same text InPost pushes to your phone, e.g. `Twój Paczkomat: paczka
już na Ciebie czeka`.

What was already announced is remembered across restarts. A restart never
replays old events, and whatever happened while Home Assistant was down is
announced once it is back. When the integration is added, parcels already in the
account are taken as the starting point and not announced.

## Notifications on your phone

The blueprint
[`parcel_notifications.yaml`](blueprints/automation/inpost_paczki/parcel_notifications.yaml)
sends a notification through the Home Assistant Companion app:

- when a parcel is waiting to be collected (and optionally for new parcels,
  collected parcels and any other status change),
- a reminder before the pickup deadline if the parcel is still waiting
  (default: 6 hours before).

[![Import the blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FEales%2Finpost-paczki%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Finpost_paczki%2Fparcel_notifications.yaml)

Example notification:

```
📦 Paczka czeka do odbioru
Jan Kowalski: Gotowa do odbioru — KRA01M, Prosta 1, 30-001 Kraków. Odbierz do 26.09 09:16
```

### Your own automations

> **The entity IDs below are placeholders.** Copy your real ones from
> `Developer tools` > `States`, filtering by `inpost`.

Forward every InPost app notification as-is:

```yaml
automation:
  - alias: "InPost - powiadomienia z aplikacji"
    triggers:
      - trigger: state
        entity_id: event.REPLACE_ME_notification
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.from_state is not none
             and trigger.from_state.state != 'unavailable'
             and trigger.to_state.state not in ['unknown', 'unavailable'] }}
    actions:
      - action: notify.notify
        data:
          title: "{{ trigger.to_state.attributes.title }}"
          message: "{{ trigger.to_state.attributes.message }}"
```

Say it out loud when you get home and a parcel is waiting:

```yaml
automation:
  - alias: "InPost - paczka czeka, przypomnij w domu"
    triggers:
      - trigger: state
        entity_id: person.REPLACE_ME
        to: home
    conditions:
      - condition: state
        entity_id: binary_sensor.REPLACE_ME_parcel_waiting
        state: "on"
    actions:
      - action: tts.speak
        target:
          entity_id: tts.REPLACE_ME
        data:
          media_player_entity_id: media_player.REPLACE_ME
          message: >-
            Czeka na Ciebie paczka od
            {{ state_attr('binary_sensor.REPLACE_ME_parcel_waiting', 'sender') }}.
```

## Dashboard

A Markdown card with every parcel waiting to be collected:

```yaml
type: markdown
content: |
  {% set lista = state_attr('sensor.REPLACE_ME_parcels_to_collect', 'parcels') or [] %}
  ## 📦 Paczki do odbioru
  {% for p in lista %}
  **{{ p.sender or 'Nieznany nadawca' }}**, {{ p.point_name }}, {{ p.point_address }}
  odbierz do {{ as_timestamp(p.expiry_date) | timestamp_custom('%d.%m %H:%M') }}
  {% else %}
  Nic nie czeka.
  {% endfor %}
```

The standard **Calendar** card shows the pickup windows:

```yaml
type: calendar
entities:
  - calendar.REPLACE_ME_parcel_pickups
```

## Notes

- Only parcels addressed to your account (and parcels shared with you in the
  app) are visible; parcels you sent are not included.
- InPost keeps recently collected parcels in the list for a while. They count
  toward neither sensor.
- Diagnostics can be downloaded from the device page. Tokens, phone number,
  tracking numbers, senders, codes and locations are redacted.

## Licence

MIT - see [LICENSE](LICENSE).
