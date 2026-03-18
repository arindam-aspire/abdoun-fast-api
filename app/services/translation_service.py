"""Translation service for property title/description/address (en, ar, esp, fr); translate_text and get_* for API."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.property_normalized import PropertyNormalized, PropertyTranslation
from app.utils.constants import Defaults

# Supported language codes (CSV/default is English)
SUPPORTED_LANGUAGE_CODES = ("en", "ar", "esp", "fr")
DEFAULT_LANGUAGE = "en"

# Map our codes to Google Translate / deep-translator codes (esp -> es for Spanish)
_LANG_TO_GOOGLE = {"en": "en", "ar": "ar", "esp": "es", "fr": "fr"}


def _find_translation_for_lang(
    translations: list[PropertyTranslation],
    language_code: str,
) -> Optional[PropertyTranslation]:
    return next((t for t in translations if t.language_code == language_code), None)


def _resolve_translation_sources(
    db: Session,
    property_id,
    source_lang: str,
    source_title: Optional[str],
    source_description: Optional[str],
    source_address: Optional[str],
) -> Optional[tuple[str, str, str]]:
    if source_title is not None and source_description is not None and source_address is not None:
        return source_title, source_description, source_address

    prop = db.get(PropertyNormalized, property_id)
    if not prop:
        return None

    translations = getattr(prop, "translations", None) or []
    trans = _find_translation_for_lang(translations, source_lang)

    resolved_title = source_title if source_title is not None else (trans and trans.title) or prop.title or ""
    resolved_description = (
        source_description
        if source_description is not None
        else (trans and trans.description) or (prop.description or "") or ""
    )
    resolved_address = (
        source_address
        if source_address is not None
        else (trans and trans.address) or (getattr(prop, "location_name", None) or "") or ""
    )
    return resolved_title, resolved_description, resolved_address


def _normalize_supported_lang(lang: Optional[str]) -> str:
    lang_normalized = (lang or DEFAULT_LANGUAGE).strip().lower()
    if lang_normalized not in SUPPORTED_LANGUAGE_CODES:
        return DEFAULT_LANGUAGE
    return lang_normalized


def _translation_title_description(
    trans: PropertyTranslation,
    prop: PropertyNormalized,
) -> Optional[tuple[str, Optional[str]]]:
    title = (trans.title or "").strip()
    desc = (trans.description or "").strip()
    if not title and not desc:
        return None
    return (title or prop.title or "", desc or prop.description)


def translate_text(
    text: str,
    target_lang: str,
    source_lang: str = DEFAULT_LANGUAGE,
) -> str:
    """
    Translate a single text string to the target language.

    Uses deep_translator (Google Translate) when available for ar, esp, fr.
    Otherwise returns source text. Can be replaced with AWS Translate.

    Args:
        text: Source text (e.g. title or description).
        target_lang: Target language code (en, ar, esp, fr).
        source_lang: Source language code (default en).

    Returns:
        Translated text, or original if target equals source or translation unavailable.
    """
    if not text or not text.strip():
        return text or ""
    if target_lang == source_lang:
        return text
    target_lang = (target_lang or "").strip().lower()
    if target_lang not in SUPPORTED_LANGUAGE_CODES:
        return text
    try:
        from deep_translator import GoogleTranslator
        src = _LANG_TO_GOOGLE.get(source_lang, "en")
        tgt = _LANG_TO_GOOGLE.get(target_lang, target_lang)
        if src == tgt:
            return text
        # GoogleTranslator has a 5000 char limit per request
        if len(text) > 4500:
            return text  # skip very long text or chunk; for now return as-is
        translated = GoogleTranslator(source=src, target=tgt).translate(text)
        return translated or text
    except Exception:
        return text


def get_or_create_translation(
    db: Session,
    property_id,
    language_code: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    address: Optional[str] = None,
) -> PropertyTranslation:
    """
    Get existing translation row for (property_id, language_code) or create one.

    Args:
        db: Database session.
        property_id: Property UUID.
        language_code: One of en, ar, esp, fr.
        title: Title for this language (optional on create).
        description: Description for this language (optional on create).
        address: Address for this language (optional on create).

    Returns:
        PropertyTranslation instance.
    """
    language_code = (language_code or DEFAULT_LANGUAGE).strip().lower()
    if language_code not in SUPPORTED_LANGUAGE_CODES:
        language_code = DEFAULT_LANGUAGE

    existing = db.execute(
        select(PropertyTranslation).where(
            PropertyTranslation.property_id == property_id,
            PropertyTranslation.language_code == language_code,
        )
    ).scalar_one_or_none()

    if existing:
        if title is not None:
            existing.title = title
        if description is not None:
            existing.description = description
        if address is not None:
            existing.address = address
        db.flush()
        return existing

    row = PropertyTranslation(
        property_id=property_id,
        language_code=language_code,
        title=title,
        description=description,
        address=address,
    )
    db.add(row)
    db.flush()
    return row


def translate_property_to_language(
    db: Session,
    property_id,
    target_lang: str,
    source_lang: str = DEFAULT_LANGUAGE,
    source_title: Optional[str] = None,
    source_description: Optional[str] = None,
    source_address: Optional[str] = None,
) -> Optional[PropertyTranslation]:
    """
    Translate a property's title and description to target language and persist.

    If source_title/source_description/source_address are not provided, reads from existing
    translation for source_lang or from PropertyNormalized.title/description.

    Args:
        db: Database session.
        property_id: Property UUID.
        target_lang: Target language code (ar, esp, fr, en).
        source_lang: Source language (default en).
        source_title: Override source title; if None, loaded from DB.
        source_description: Override source description; if None, loaded from DB.
        source_address: Override source address; if None, loaded from DB.

    Returns:
        PropertyTranslation for target_lang, or None if target_lang invalid.
    """
    target_lang = (target_lang or "").strip().lower()
    if target_lang not in SUPPORTED_LANGUAGE_CODES or target_lang == source_lang:
        return None

    sources = _resolve_translation_sources(
        db,
        property_id,
        source_lang,
        source_title,
        source_description,
        source_address,
    )
    if not sources:
        return None
    source_title, source_description, source_address = sources

    translated_title = translate_text(source_title, target_lang, source_lang)
    translated_description = translate_text(source_description, target_lang, source_lang)
    translated_address = translate_text(source_address, target_lang, source_lang) if source_address else ""
    return get_or_create_translation(
        db,
        property_id=property_id,
        language_code=target_lang,
        title=translated_title or source_title,
        description=translated_description or source_description,
        address=translated_address or source_address,
    )


def get_title_description_for_language(
    prop: PropertyNormalized,
    lang: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """
    Get (title, description) for a property in the requested language.

    Uses property_translations when available; falls back to PropertyNormalized.title
    and .description (legacy/default English).

    Args:
        prop: PropertyNormalized instance (translations loaded, e.g. via selectinload).
        lang: Language code (en, ar, esp, fr). If None, uses default/English fallback.

    Returns:
        (title, description) for the requested language.
    """
    lang = _normalize_supported_lang(lang)

    translations = getattr(prop, "translations", None) or []
    trans = _find_translation_for_lang(translations, lang)
    if trans:
        translated = _translation_title_description(trans, prop)
        if translated:
            return translated

    return (prop.title or "", prop.description)


def get_title_description_all_languages(
    prop: "PropertyNormalized",
) -> tuple[dict[str, str], dict[str, Optional[str]]]:
    """
    Get title and description for all supported languages as dicts for API response.

    Returns (title_by_lang, description_by_lang) with keys en, ar, esp, fr.
    Uses property_translations when available; falls back to property.title/description for en.
    """
    fallback_title = (prop.title or "").strip() or ""
    if not fallback_title:
        fallback_title = Defaults.UNTITLED_PROPERTY_FALLBACK
    fallback_desc = (prop.description or "").strip() if getattr(prop, "description", None) else None

    title_by_lang: dict[str, str] = {}
    description_by_lang: dict[str, Optional[str]] = {}

    translations = getattr(prop, "translations", None) or []
    for lang in SUPPORTED_LANGUAGE_CODES:
        trans = next((t for t in translations if t.language_code == lang), None)
        if trans:
            t_val = (trans.title or "").strip() or fallback_title
            d_val = (trans.description or "").strip() if (trans.description or "").strip() else fallback_desc
        else:
            t_val = fallback_title if lang == DEFAULT_LANGUAGE else ""
            d_val = fallback_desc if lang == DEFAULT_LANGUAGE else None
        title_by_lang[lang] = t_val or fallback_title
        description_by_lang[lang] = d_val

    return (title_by_lang, description_by_lang)


def get_address_all_languages(
    prop_or_address: "PropertyNormalized | str | None",
    source_lang: str = DEFAULT_LANGUAGE,
) -> dict[str, str]:
    """
    Translate a plain address string to all supported languages for API responses.

    Args:
        prop_or_address: PropertyNormalized instance (preferred) or plain address text.
        source_lang: Source language code, default is "en".

    Returns:
        Dict with keys from SUPPORTED_LANGUAGE_CODES.
        If translation is unavailable, falls back to source text.
    """
    if isinstance(prop_or_address, PropertyNormalized):
        prop = prop_or_address
        fallback = (getattr(prop, "location_name", None) or "").strip()
        translations = getattr(prop, "translations", None) or []
        out: dict[str, str] = {}
        for lang in SUPPORTED_LANGUAGE_CODES:
            trans = next((t for t in translations if t.language_code == lang), None)
            if trans and (trans.address or "").strip():
                out[lang] = (trans.address or "").strip()
                continue
            if not fallback:
                out[lang] = ""
                continue
            if lang == source_lang:
                out[lang] = fallback
            else:
                translated = translate_text(fallback, lang, source_lang)
                out[lang] = (translated or fallback).strip() or fallback
        return out

    source_text = (prop_or_address or "").strip()
    if not source_text:
        return dict.fromkeys(SUPPORTED_LANGUAGE_CODES, "")

    out: dict[str, str] = {}
    for lang in SUPPORTED_LANGUAGE_CODES:
        if lang == source_lang:
            out[lang] = source_text
            continue
        translated = translate_text(source_text, lang, source_lang)
        out[lang] = (translated or source_text).strip() or source_text
    return out
