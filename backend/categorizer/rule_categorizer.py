"""
categorizer/rule_categorizer.py

Regex-based fallback categorizer.
Maps transaction descriptions to human-readable categories.
Order matters — first match wins.
No external calls, no IO, fully deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from categorizer.description_cleaner import clean_description as rule_clean


@dataclass
class CategoryRule:
    category: str
    subcategory: str
    patterns: list[re.Pattern]


# ---------------------------------------------------------------------------
# Rule table — order is significant (first match wins)
# ---------------------------------------------------------------------------

_RAW_RULES: list[tuple[str, str, list[str]]] = [
    # --- Income ---
    ("income", "payroll",        [r"NOMINA|SALARIO|SUELDO|CONCEPTO\s+Nomina"]),
    ("income", "transfer_in",    [r"^TRANSFERENCIA DE ", r"^TRANSFERENCIA INMEDIATA DE"]),
    ("income", "bizum_in",       [r"^BIZUM DE "]),
    ("income", "refund",         [r"^ANULACION", r"DEVOLUCION|REEMBOLSO|REFUND"]),
    ("income", "paypal_in",      [r"PAYPAL.*CONCEPTO YYW"]),

    # --- Housing ---
    ("housing", "rent",          [r"ALQUILER|ARRENDAMIENTO|CONCEPTO.*[Aa]lquiler"]),
    ("housing", "utilities_electricity", [r"ENDESA|IBERDROLA|NATURGY|REPSOL.*LUZ|ELECTRICIDAD|WASABI ENERGIA"]),
    ("housing", "utilities_water",       [r"VIAQUA|AGUAS|AGUA\b"]),
    ("housing", "utilities_heating",     [r"AGENCIA VILLAR|CALEFAC"]),
    ("housing", "internet_phone",        [r"PEPEPHONE|MOVISTAR|VODAFONE|ORANGE|YOIGO|DIGI\b|MASMOVIL"]),

    # --- Subscriptions ---
    ("subscriptions", "streaming",       [r"NETFLIX|SPOTIFY|HBO|DISNEY|PRIME VIDEO|APPLE.*TV|TWITCH"]),
    ("subscriptions", "gym",             [r"DREAMFIT|GIMNASIO|GYM\b|MCFIT|FITNESS"]),
    ("subscriptions", "sports_club",     [r"XESTION DE ACTIVIDADES DEPORTIVAS|DEPORTIV"]),
    ("subscriptions", "paypal_sub",      [r"^RECIBO PayPal"]),
    ("subscriptions", "pagatelia",       [r"PAGATELIA"]),
    ("subscriptions", "other_sub",       [r"^RECIBO "]),

    # --- Groceries ---
    ("groceries", "supermarket",         [r"LIDL|MERCADONA|CARREFOUR|ALCAMPO|ALDI|DIA\b|AHORRO|MERCAMAS|MERKASIA|MARKET SANTIAGO"]),
    ("groceries", "other_food_shop",     [r"AUTOSERVICIO|FRUTERIA|VERDULERIA|GRAN BAZAR"]),

    # --- Restaurants & Leisure ---
    ("restaurants", "fast_food",         [r"MC DONALDS|MCDONALDS|BURGER KING|BK\d|FIVE GUYS|KFC|POPEYES|KEBAB|GYROS|ROYAL DONNER"]),
    ("restaurants", "restaurant",        [r"RESTAURANTE|COMPOSTELA H\.|WOK TOWN|SUPERTROPICAL|VIPS|A FUEGO LENTO|SABORES|CAFE BAR|CAFE DALIA|ADELIA|MAMBARA|GINOS|LA MARIPEPA|LOS SECRETOS|LA NEGRA|VERMUTERIA|BAR AQUEVINO|PIK POLLO|COSTA VELLA|GALIA|SOU SHUSHI|SUSHI|PLAZA LENCE|ROYAL KEBAB|ASIAN POCKET|CAFE LA MORENA"]),
    ("restaurants", "cafe_bakery",       [r"CAFE\b|CAFETERIA|COFFEE|BOANDGO|FORNO|GRANIER|MOLLETE|TOSTA|BAKERY|CHURRERIA"]),
    ("restaurants", "bar_pub",           [r"PUB\b|BAR\b|CERVECERIA|CANTINA|GALURESA"]),

    # --- Transport ---
    ("transport", "parking",             [r"APARCAMIENTO|PARKING\b|PARKIA"]),
    ("transport", "fuel",                [r"PETROPRIX|PLENOIL|GASOLINERA|REPSOL.*GASOL|GALURESA|COMBUSTIBLE|CARBURANTE"]),
    ("transport", "rideshare",           [r"CABIFY|UBER\b|BOLT\b|FREE NOW"]),
    ("transport", "public_transit",      [r"RENFE|ALSA|AVE\b|BUS\b|METRO\b|CONCELLO DE SAN|TRAM\b"]),
    ("transport", "train_station",       [r"CHAMARTIN|ATOCHA|ESTACION"]),
    ("transport", "tyre_service",        [r"NEUMATICOS|RUEDAS"]),

    # --- Health ---
    ("health", "pharmacy",               [r"FARMACIA"]),
    ("health", "medical",                [r"CLINICA|MEDICO|DENTISTA|HOSPITAL|CENTRO.*MEDIC"]),

    # --- Shopping ---
    ("shopping", "online",               [r"AMAZON|ALIEXPRESS|WALLAPOP|VINTED|DECATHLON.*INTERNET|WWW\."]),
    ("shopping", "clothing",             [r"VINTED|ZARA\b|HM\b|MANGO\b|PRIMARK|SUPEREGALO|SUPERREGALO|IPO CONCEPT"]),
    ("shopping", "electronics",          [r"PCCOMPONENTES|MEDIAMARKT|FNAC"]),
    ("shopping", "general",              [r"PRIMAPRIX|DECATHLON|GRAN BAZAR"]),

    # --- Entertainment ---
    ("entertainment", "cinema",          [r"CINESA|CINE\b|WWW CINESA|FED.GALLEGA ATL|NYX.*HAPPY"]),
    ("entertainment", "events",          [r"ENTRADAS|TICKET|EVENTO"]),
    ("entertainment", "gaming",          [r"STEAM|PLAYSTATION|XBOX|NINTENDO|HAPPYGAMES"]),

    # --- Transfers / Bizum out ---
    ("transfers", "rent_contribution",   [r"CONCEPTO.*[Cc]asper"]),   # shared pet/cost
    ("transfers", "bizum_out",           [r"^BIZUM A FAVOR DE"]),
    ("transfers", "transfer_out",        [r"^TRANSFERENCIA A FAVOR DE"]),

    # --- Cash ---
    ("cash", "atm_withdrawal",           [r"RETIRADA DE EFECTIVO|CAJERO"]),

    # --- Taxes / Admin ---
    ("admin", "city_tax",                [r"PAGO RECIBO DE AY\."]),
    ("admin", "travel_tickets",          [r"BIZUM VENTA BILLETES|COMPRA BIZUM.*BILLETES"]),
]


_RULES: list[CategoryRule] = [
    CategoryRule(
        category=cat,
        subcategory=sub,
        patterns=[re.compile(p, re.IGNORECASE) for p in pats],
    )
    for cat, sub, pats in _RAW_RULES
]


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
    """Mutates (or returns a copy of) a normalized transaction with category fields filled."""
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
