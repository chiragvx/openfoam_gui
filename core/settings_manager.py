import json
import logging
from pathlib import Path
import config

log = logging.getLogger(__name__)

class SettingsManager:
    _SETTINGS_FILE = config.APP_DIR / "settings.json"
    
    DEFAULT_SETTINGS = {
        "theme": "dark",
        "units": "m",  # m, cm, mm, in, ft
    }

    @classmethod
    def load(cls) -> dict:
        if not cls._SETTINGS_FILE.exists():
            return cls.DEFAULT_SETTINGS.copy()
        
        try:
            data = json.loads(cls._SETTINGS_FILE.read_text(encoding="utf-8"))
            # Merge with defaults to ensure all keys exist
            settings = cls.DEFAULT_SETTINGS.copy()
            settings.update(data)
            return settings
        except Exception as e:
            log.error(f"Failed to load settings: {e}")
            return cls.DEFAULT_SETTINGS.copy()

    @classmethod
    def save(cls, settings: dict):
        try:
            cls._SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except Exception as e:
            log.error(f"Failed to save settings: {e}")

    @classmethod
    def get(cls, key: str):
        return cls.load().get(key, cls.DEFAULT_SETTINGS.get(key))

    @classmethod
    def set(cls, key: str, value):
        settings = cls.load()
        settings[key] = value
        cls.save(settings)
