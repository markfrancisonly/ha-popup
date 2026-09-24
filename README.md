# Popup

Show a Lovelace card as a popup on every connected browser, from an automation
or script. A small replacement for browser_mod popups: one integration, two
actions, no browser registration.

## Install

Copy `custom_components/popup/` into `<config>/custom_components/` (or add this
repository to HACS), restart, then add the **Popup** integration from
Settings › Devices & services. There is nothing to configure. The frontend
module registers itself as a dashboard resource.

## Actions

`popup.open`

| field | |
|---|---|
| `id` | name of the popup; opening the same id again replaces it, `close` needs it |
| `card` | a card configuration to render (no Jinja: Home Assistant renders templates in action data, so cards with templates go via `view`) |
| `view` | a dashboard view to render instead, e.g. `/lovelace/keypad`; resolved in the browser, so templates inside its cards work |
| `message` | text only, shown as a small banner at the bottom (a toast), 5 s by default |
| `title` | optional heading |
| `dismissable` | shows an X in the header; tap outside or Escape closes it too (default `true`) |
| `timeout` | close by itself after this many seconds |
| `close_on_tap` | any tap inside the card closes the popup after the tap's action (menus of one-shot buttons) |
| `width` | CSS length for the box, e.g. `400px` or `50vw`; default is the full width of the screen |
| `users` | only browsers signed in as these Home Assistant users, by name or id; omit for everyone. Kiosks each signed in as their own user are addressed this way |
| `areas` | only kiosks in these areas, by name or id. A browser has no area of its own, so a kiosk's user is matched to a device with the same name (the kiosk app's device, say), and that device's area counts. Combines with `users` |

`popup.close` with an optional `id` closes it everywhere, or only for `users` / `areas`.

```yaml
action: popup.open
data:
  id: keypad
  view: /lovelace/keypad
  dismissable: false
```

```yaml
action: popup.open
data:
  id: garage
  message: Closing garage doors
  timeout: 13
  users: [Kitchen wallpanel]
```

### Local popups from a dashboard

A tap action can open a popup in that browser only, with no round trip:

```yaml
tap_action:
  action: fire-dom-event
  popup:
    id: lights
    title: Lights upstairs
    card:
      type: entities
      entities: [light.bedroom, light.hall]
```

`popup: close` in a tap action closes it.

## How it works

The overlay is mounted inside Home Assistant's own element tree and cards are
created the way dashboard views create them, so their tap actions and more-info
dialogs work. Open and close travel as bus events forwarded to each frontend
over a websocket subscription that does not require an admin user. A browser
that connects later sees nothing; nothing is stored.

The `Popup` diagnostic sensor shows the loaded version and, as an attribute,
how many browsers are subscribed.
