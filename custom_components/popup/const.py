"""Constants for the Popup integration."""

from typing import Final

DOMAIN: Final = "popup"
CARD_FILENAME: Final = "popup.js"
CARD_URL: Final = f"/{DOMAIN}/{CARD_FILENAME}"
EVENT_OPEN: Final = f"{DOMAIN}_open"
EVENT_CLOSE: Final = f"{DOMAIN}_close"
SERVICE_OPEN: Final = "open"
SERVICE_CLOSE: Final = "close"
