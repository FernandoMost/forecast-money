"""
categorizer/rule_categorizer.py

Regex-based categorizer. Rules are loaded from config/category_rules.yaml.
If the config file is not found, falls back to built-in defaults.

Order matters — first match wins.
No external calls, no IO beyond the initial YAML load, fully deterministic.

To customize: edit config/category_rules.yaml and run POST /api/v1/recategorize.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from categorizer.description_cleaner import clean_description as rule_clean

logger = logging.getLogger(__name__)


@dataclass
class CategoryRule:
    category: str
    subcategory: str
    patterns: list[re.Pattern]


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _find_config() -> Path | None:
    """Locate category_rules.yaml by walking up from this file's directory."""
    candidates = [
        Path(__file__).parent.parent.parent / "config" / "category_rules.yaml",  # repo root
        Path(__file__).parent.parent / "config" / "category_rules.yaml",         # backend/
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_rules() -> list[CategoryRule]:
    config_path = _find_config()
    if config_path is None:
        logger.warning("category_rules.yaml not found — using built-in defaults.")
        return _builtin_rules()

    try:
        with config_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
        rules = [
            CategoryRule(
                category=entry["category"],
                subcategory=entry["subcategory"],
                patterns=[re.compile(p, re.IGNORECASE) for p in entry.get("patterns", [])],
            )
            for entry in raw
            if entry.get("category") and entry.get("subcategory")
        ]
        logger.debug("Loaded %d category rules from %s", len(rules), config_path)
        return rules
    except Exception as exc:
        logger.error("Failed to load category_rules.yaml (%s) — using built-in defaults.", exc)
        return _builtin_rules()


def _builtin_rules() -> list[CategoryRule]:
    """Hardcoded fallback — mirrors the YAML content."""
    raw: list[tuple[str, str, list[str]]] = [
        ("income", "payroll",        [r"NOMINA|SALARIO|SUELDO|CONCEPTO\s+Nomina"]),
        ("income", "transfer_in",    [r"^TRANSFERENCIA DE ", r"^TRANSFERENCIA INMEDIATA DE"]),
        ("income", "bizum_in",       [r"^BIZUM DE "]),
        ("income", "refund",         [r"^ANULACION", r"DEVOLUCION|REEMBOLSO|REFUND"]),
        ("income", "paypal_in",      [r"PAYPAL.*CONCEPTO YYW"]),
        ("housing", "rent",          [r"ALQUILER|ARRENDAMIENTO|CONCEPTO.*[Aa]lquiler"]),
        ("housing", "utilities_electricity", [r"ENDESA|IBERDROLA|NATURGY|REPSOL.*LUZ|ELECTRICIDAD|WASABI ENERGIA"]),
        ("housing", "utilities_water",       [r"VIAQUA|AGUAS|AGUA\b"]),
        ("housing", "utilities_heating",     [r"AGENCIA VILLAR|CALEFAC"]),
        ("housing", "internet_phone",        [r"PEPEPHONE|MOVISTAR|VODAFONE|ORANGE|YOIGO|DIGI\b|MASMOVIL"]),
        ("subscriptions", "streaming",       [r"NETFLIX|SPOTIFY|HBO|DISNEY|PRIME VIDEO|APPLE.*TV|TWITCH"]),
        ("subscriptions", "gym",             [r"DREAMFIT|GIMNASIO|GYM\b|MCFIT|FITNESS"]),
        ("subscriptions", "sports_club",     [r"XESTION DE ACTIVIDADES DEPORTIVAS|DEPORTIV"]),
        ("subscriptions", "paypal_sub",      [r"^RECIBO PayPal"]),
        ("subscriptions", "pagatelia",       [r"PAGATELIA"]),
        ("subscriptions", "other_sub",       [r"^RECIBO "]),
        ("groceries", "supermarket",         [r"LIDL|MERCADONA|CARREFOUR|ALCAMPO|ALDI|DIA\b|AHORRO|MERCAMAS|MERKASIA|MARKET SANTIAGO"]),
        ("groceries", "other_food_shop",     [r"AUTOSERVICIO|FRUTERIA|VERDULERIA|GRAN BAZAR"]),
        ("restaurants", "fast_food",         [r"MC DONALDS|MCDONALDS|BURGER KING|BK\d|FIVE GUYS|KFC|POPEYES|KEBAB|GYROS|ROYAL DONNER"]),
        ("restaurants", "restaurant",        [r"RESTAURANTE|COMPOSTELA H\.|WOK TOWN|SUPERTROPICAL|VIPS|A FUEGO LENTO|SABORES|CAFE BAR|CAFE DALIA|ADELIA|MAMBARA|GINOS|LA MARIPEPA|LOS SECRETOS|LA NEGRA|VERMUTERIA|BAR AQUEVINO|PIK POLLO|COSTA VELLA|GALIA|SOU SHUSHI|SUSHI|PLAZA LENCE|ROYAL KEBAB|ASIAN POCKET|CAFE LA MORENA"]),
        ("restaurants", "cafe_bakery",       [r"CAFE\b|CAFETERIA|COFFEE|BOANDGO|FORNO|GRANIER|MOLLETE|TOSTA|BAKERY|CHURRERIA"]),
        ("restaurants", "bar_pub",           [r"PUB\b|BAR\b|CERVECERIA|CANTINA|GALURESA"]),
        ("transport", "parking",             [r"APARCAMIENTO|PARKING\b|PARKIA"]),
        ("transport", "fuel",                [r"PETROPRIX|PLENOIL|GASOLINERA|REPSOL.*GASOL|GALURESA|COMBUSTIBLE|CARBURANTE"]),
        ("transport", "rideshare",           [r"CABIFY|UBER\b|BOLT\b|FREE NOW"]),
        ("transport", "public_transit",      [r"RENFE|ALSA|AVE\b|BUS\b|METRO\b|CONCELLO DE SAN|TRAM\b"]),
        ("transport", "train_station",       [r"CHAMARTIN|ATOCHA|ESTACION"]),
        ("transport", "tyre_service",        [r"NEUMATICOS|RUEDAS"]),
        ("health", "pharmacy",               [r"FARMACIA"]),
        ("health", "medical",                [r"CLINICA|MEDICO|DENTISTA|HOSPITAL|CENTRO.*MEDIC"]),
        ("shopping", "online",               [r"AMAZON|ALIEXPRESS|WALLAPOP|VINTED|DECATHLON.*INTERNET|WWW\."]),
        ("shopping", "clothing",             [r"VINTED|ZARA\b|HM\b|MANGO\b|PRIMARK|SUPEREGALO|SUPERREGALO|IPO CONCEPT"]),
        ("shopping", "electronics",          [r"PCCOMPONENTES|MEDIAMARKT|FNAC"]),
        ("shopping", "general",              [r"PRIMAPRIX|DECATHLON|GRAN BAZAR"]),
        ("entertainment", "cinema",          [r"CINESA|CINE\b|WWW CINESA|FED.GALLEGA ATL|NYX.*HAPPY"]),
        ("entertainment", "events",          [r"ENTRADAS|TICKET|EVENTO"]),
        ("entertainment", "gaming",          [r"STEAM|PLAYSTATION|XBOX|NINTENDO|HAPPYGAMES"]),
        ("transfers", "rent_contribution",   [r"CONCEPTO.*[Cc]asper"]),
        ("transfers", "bizum_out",           [r"^BIZUM A FAVOR DE"]),
        ("transfers", "transfer_out",        [r"^TRANSFERENCIA A FAVOR DE"]),
        ("cash", "atm_withdrawal",           [r"RETIRADA DE EFECTIVO|CAJERO"]),
        ("admin", "city_tax",                [r"PAGO RECIBO DE AY\."]),
        ("admin", "travel_tickets",          [r"BIZUM VENTA BILLETES|COMPRA BIZUM.*BILLETES"]),
    ]
    return [
        CategoryRule(
            category=cat,
            subcategory=sub,
            patterns=[re.compile(p, re.IGNORECASE) for p in pats],
        )
        for cat, sub, pats in raw
    ]


# ---------------------------------------------------------------------------
# Module-level rules — loaded once at import time
# Reload by calling reload_rules() after editing the YAML.
# ---------------------------------------------------------------------------

_RULES: list[CategoryRule] = _load_rules()


def reload_rules() -> int:
    """Reload rules from YAML. Returns the number of rules loaded."""
    global _RULES
    _RULES = _load_rules()
    return len(_RULES)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def categorize(description: str) -> tuple[str, str]:
    """
    Returns (category, subcategory) for a transaction description.
    Falls back to ('uncategorized', 'other') if no rule matches.
    """
    for rule in _RULES:
        for pattern in rule.patterns:
            if pattern.search(description):
                return rule.category, rule.subcategory
    return "uncategorized", "other"


def categorize_transaction(tx: dict) -> dict:
    """Returns the transaction dict with category and clean_description filled."""
    cat, sub = categorize(tx["description"])
    label = rule_clean(tx["description"])
    return {
        **tx,
        "category": cat,
        "subcategory": sub,
        "category_source": "rule",
        "clean_description": label,
        "clean_description_source": "rule" if label else None,
    }
