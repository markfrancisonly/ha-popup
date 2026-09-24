"""Popup: show a Lovelace card as an overlay on every connected browser.

A lightweight replacement for browser_mod popups. ``popup.open`` fires a bus
event that authenticated frontends receive over ``popup/subscribe``; the
frontend module renders the card in an overlay mounted inside Home Assistant's
element tree, so the card's own tap actions work. ``popup.close`` removes it.
Nothing is stored; a browser that connects later sees nothing.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import voluptuous as vol
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import area_registry as ar, config_validation as cv, device_registry as dr
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_when_setup

from .const import (
    CARD_FILENAME,
    CARD_URL,
    DOMAIN,
    EVENT_CLOSE,
    EVENT_OPEN,
    SERVICE_CLOSE,
    SERVICE_OPEN,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
CARD_PATH = Path(__file__).parent / "www" / CARD_FILENAME
# Process-level state: the view and websocket command register once, and the
# subscription count lives here so it survives a reload of the entry.
DATA_HTTP = f"{DOMAIN}_http"

OPEN_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required("id"): cv.string,
            # one of: a card config (frontend-side data only; Home Assistant
            # renders Jinja in service data, so cards with templates go via view)
            vol.Optional("card"): dict,
            # a dashboard view to render, e.g. "/lovelace/keypad"
            vol.Optional("view"): cv.string,
            # or just a message: a small banner at the bottom (default 5 s)
            vol.Optional("message"): cv.string,
            vol.Optional("title"): cv.string,
            vol.Optional("dismissable", default=True): cv.boolean,
            vol.Optional("timeout"): vol.All(vol.Coerce(float), vol.Range(min=1, max=3600)),
            vol.Optional("close_on_tap", default=False): cv.boolean,
            # CSS length for the box, e.g. "360px" or "50vw" (default min(96vw, 720px))
            vol.Optional("width"): cv.string,
            # only browsers signed in as these users (id or name); default: all
            vol.Optional("users"): vol.All(cv.ensure_list, [cv.string]),
            # or the users of kiosks in these areas (area id or name); a kiosk's
            # user is matched to a device with the same name, and that device's
            # area is the kiosk's area
            vol.Optional("areas"): vol.All(cv.ensure_list, [cv.string]),
        }
    ),
    cv.has_at_least_one_key("card", "view", "message"),
)
CLOSE_SCHEMA = vol.Schema(
    {
        vol.Optional("id"): cv.string,
        vol.Optional("users"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("areas"): vol.All(cv.ensure_list, [cv.string]),
    }
)


async def _resolve_users(hass: HomeAssistant, wanted: list[str] | None) -> list[str] | None:
    """Turn user ids or names into user ids; unknown names are logged and dropped."""
    if not wanted:
        return None
    users = await hass.auth.async_get_users()
    by_key = {u.id: u.id for u in users}
    by_key.update({(u.name or "").casefold(): u.id for u in users if u.name})
    ids = []
    for item in wanted:
        uid = by_key.get(item) or by_key.get(item.casefold())
        if uid:
            ids.append(uid)
        else:
            _LOGGER.warning("popup: no user %r", item)
    return ids


def _users_in_areas(hass: HomeAssistant, users, wanted: list[str]) -> list[str]:
    """User ids of kiosks in the areas: a user named like a device in the area."""
    areas = ar.async_get(hass)
    area_ids: set[str] = set()
    for item in wanted:
        area = areas.async_get_area(item) or areas.async_get_area_by_name(item)
        if area:
            area_ids.add(area.id)
        else:
            _LOGGER.warning("popup: no area %r", item)
    if not area_ids:
        return []
    names = {
        (d.name_by_user or d.name or "").casefold()
        for d in dr.async_get(hass).devices.values()
        if d.area_id in area_ids
    }
    names.discard("")
    return [u.id for u in users if u.name and u.name.casefold() in names]


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@websocket_api.async_response
async def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Forward open/close events to an authenticated frontend (auth, not admin)."""

    @callback
    def forward(event: Event) -> None:
        targets = event.data.get("users")
        if targets and connection.user.id not in targets:
            return
        connection.send_message(
            websocket_api.event_message(
                msg["id"], {"event_type": event.event_type, "data": dict(event.data)}
            )
        )

    unsubs = (
        hass.bus.async_listen(EVENT_OPEN, forward),
        hass.bus.async_listen(EVENT_CLOSE, forward),
    )
    proc = hass.data[DATA_HTTP]
    proc["clients"] += 1
    proc["notify"]()

    @callback
    def unsub_all() -> None:
        for unsubscribe in unsubs:
            unsubscribe()
        proc["clients"] = max(0, proc["clients"] - 1)
        proc["notify"]()

    connection.subscriptions[msg["id"]] = unsub_all
    connection.send_result(msg["id"])


class CardView(HomeAssistantView):
    """Serve the frontend module captured at setup, with an ETag."""

    url = CARD_URL
    name = f"{DOMAIN}:card"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return the module, or 304 when the browser already has this build."""
        data = request.app["hass"].data.get(DOMAIN)
        if not data:
            return web.Response(status=404)
        card, etag = data["card"], data["etag"]
        if any(tag.value in ("*", etag) for tag in (request.if_none_match or ())):
            return web.Response(status=304, headers={"ETag": f'"{etag}"'})
        return web.Response(
            body=card,
            content_type="application/javascript",
            headers={"Cache-Control": "no-cache", "ETag": f'"{etag}"'},
        )


async def _async_init_resource(hass: HomeAssistant, url: str, version_tag: str) -> None:
    """Keep a versioned module entry for ``url`` in the Lovelace resources.

    The ``?v=`` tag changes with every build so cached module scripts (the
    companion app's service worker ignores no-cache) are refetched.
    """
    target = f"{url}?v={version_tag}"
    resources = getattr(hass.data.get("lovelace"), "resources", None)
    if not isinstance(resources, ResourceStorageCollection):
        _LOGGER.warning("Lovelace is in YAML mode; add '%s' as a module resource", target)
        return
    await resources.async_get_info()
    for item in resources.async_items():
        if item.get("url", "").split("?", 1)[0] != url:
            continue
        if item["url"] != target:
            await resources.async_update_item(item["id"], {"res_type": "module", "url": target})
        return
    await resources.async_create_item({"res_type": "module", "url": target})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the single Popup entry."""
    integration = await async_get_integration(hass, DOMAIN)
    card = await hass.async_add_executor_job(CARD_PATH.read_bytes)
    etag = f"{integration.version}-{hashlib.sha256(card).hexdigest()[:12]}"
    hass.data[DOMAIN] = {
        "entry_id": entry.entry_id,
        "version": str(integration.version),
        "card": card,
        "etag": etag,
    }

    if DATA_HTTP not in hass.data:
        hass.data[DATA_HTTP] = {"clients": 0, "notify": lambda: None}
        hass.http.register_view(CardView())
        websocket_api.async_register_command(hass, ws_subscribe)

    async def register_card(hass: HomeAssistant, _component: str) -> None:
        await _async_init_resource(hass, CARD_URL, etag)

    async_when_setup(hass, "lovelace", register_card)

    async def _fire(event_type: str, call: ServiceCall) -> None:
        data = dict(call.data)
        if "users" in data or "areas" in data:
            ids = await _resolve_users(hass, data.get("users")) or []
            if data.get("areas"):
                users = await hass.auth.async_get_users()
                ids += _users_in_areas(hass, users, data.pop("areas"))
            data["users"] = sorted(set(ids))
            if not data["users"]:
                _LOGGER.warning("popup: %s targets nobody", event_type)
                return
        hass.bus.async_fire(event_type, data)

    async def handle_open(call: ServiceCall) -> None:
        await _fire(EVENT_OPEN, call)

    async def handle_close(call: ServiceCall) -> None:
        await _fire(EVENT_CLOSE, call)

    hass.services.async_register(DOMAIN, SERVICE_OPEN, handle_open, OPEN_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLOSE, handle_close, CLOSE_SCHEMA)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the Popup entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.services.async_remove(DOMAIN, SERVICE_OPEN)
        hass.services.async_remove(DOMAIN, SERVICE_CLOSE)
        hass.data.pop(DOMAIN, None)
    return unload_ok
