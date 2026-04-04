"""
Internationalization (i18n) module

Lightweight translation system using YAML locale files.
Supports dot-notation keys (e.g., "cmd.low_risk") and {variable} interpolation.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml

from src.config.settings import DEFAULT_CONFIG_DIR

logger = logging.getLogger(__name__)

# Locale file search paths
_LOCALE_DIR = DEFAULT_CONFIG_DIR / "locales"

# Loaded translations: {lang: {flat_key: value}}
_translations: dict[str, dict[str, str]] = {}
_current_lang: str = "en"
_fallback_lang: str = "en"


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    """Flatten nested dict to dot-notation keys: {"a": {"b": "c"}} -> {"a.b": "c"}"""
    result: dict[str, str] = {}
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, key))
        else:
            result[key] = str(v)
    return result


def _load_locale(lang: str) -> dict[str, str]:
    """Load a locale file and return flattened translations."""
    if lang in _translations:
        return _translations[lang]

    locale_file = _LOCALE_DIR / f"{lang}.yaml"
    if not locale_file.exists():
        logger.debug("Locale file not found: %s", locale_file)
        return {}

    try:
        with open(locale_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        flat = _flatten(data)
        _translations[lang] = flat
        logger.debug("Loaded locale '%s' with %d keys", lang, len(flat))
        return flat
    except Exception:
        logger.exception("Failed to load locale: %s", locale_file)
        return {}


def _detect_system_lang() -> str:
    """Detect language from system locale (LANG, LC_ALL, LC_MESSAGES)."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.getenv(var, "")
        if val:
            # e.g., "zh_CN.UTF-8" -> "zh", "ko_KR.UTF-8" -> "ko", "en_US" -> "en"
            code = val.split(".")[0].split("_")[0].lower()
            if code and (_LOCALE_DIR / f"{code}.yaml").exists():
                return code
    return _fallback_lang


def init_i18n(lang: Optional[str] = None) -> None:
    """
    Initialize i18n with the specified language.

    Language detection priority:
    1. Explicit lang parameter
    2. CSOPS_LANG environment variable ("auto" = detect from system locale)
    3. Default: "auto" (detect from system locale)
    """
    global _current_lang

    raw = lang or os.getenv("CSOPS_LANG", "auto").strip().lower()
    _current_lang = _detect_system_lang() if raw == "auto" else raw

    # Pre-load current language and fallback
    _load_locale(_fallback_lang)
    if _current_lang != _fallback_lang:
        _load_locale(_current_lang)

    logger.debug("i18n initialized: lang=%s", _current_lang)


def set_lang(lang: str) -> None:
    """Switch language at runtime."""
    global _current_lang
    _current_lang = lang.strip().lower()
    _load_locale(_current_lang)
    logger.debug("i18n language switched to: %s", _current_lang)


def t(key: str, **kwargs: Any) -> str:
    """
    Translate a message key.

    Args:
        key: Dot-notation key (e.g., "cmd.low_risk")
        **kwargs: Variables for interpolation (e.g., host="web-01")

    Returns:
        Translated string with variables substituted.
        Falls back to English if key not found in current locale.
        Returns the key itself if not found in any locale.
    """
    # Try current language
    translations = _load_locale(_current_lang)
    text = translations.get(key)

    # Fallback to English
    if text is None and _current_lang != _fallback_lang:
        fallback = _load_locale(_fallback_lang)
        text = fallback.get(key)

    # Key not found anywhere
    if text is None:
        return key

    # Variable interpolation
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return text


def get_current_lang() -> str:
    """Return the current language code."""
    return _current_lang


def available_languages() -> list[str]:
    """List available locale files."""
    if not _LOCALE_DIR.exists():
        return []
    return sorted(
        p.stem for p in _LOCALE_DIR.glob("*.yaml")
    )
