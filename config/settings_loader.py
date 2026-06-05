"""
config/settings_loader.py — Loads and validates bot_settings.json
"""

import json
import os
from pathlib import Path


_SETTINGS_PATH = Path(__file__).parent / "bot_settings.json"
_PROFILES_PATH = Path(__file__).parent / "strategy_profiles.json"


def load_settings() -> dict:
    with open(_SETTINGS_PATH) as f:
        settings = json.load(f)

    # Inject API keys from environment (never hardcode secrets)
    settings["data"]["polygon_api_key"] = os.getenv("POLYGON_API_KEY", "")
    settings["execution"]["alpaca_api_key"] = os.getenv("ALPACA_API_KEY", "")
    settings["execution"]["alpaca_secret_key"] = os.getenv("ALPACA_SECRET_KEY", "")

    return settings


def load_strategy_profiles() -> dict:
    with open(_PROFILES_PATH) as f:
        return json.load(f)
