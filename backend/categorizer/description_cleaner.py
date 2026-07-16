"""
categorizer/description_cleaner.py

Rule-based cleaner that maps raw bank descriptions to short human-friendly labels.
Rules are loaded from the shared SQLite DB (data/shared.db → description_rules table).

Order matters — rules are applied in ascending position order; first match wins.
Returns None if no rule matches (AI can fill it if enabled).

To add/edit rules: use the API endpoints (GET/POST/PUT/DELETE /api/v1/description-rules)
or the /rules page in the frontend. Changes take effect immediately via reload_rules().
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CleanRule:
    label: str
    patterns: list[re.Pattern]


# ---------------------------------------------------------------------------
# Load rules from SharedStore
# ---------------------------------------------------------------------------

def _shared_db_path() -> Path:
    """Resolve the shared DB path using the same logic as Settings in deps.py."""
    import os
    from pathlib import Path
    # Honor env var override (same key as Settings.shared_db_path field)
    env = os.getenv("SHARED_DB_PATH")
    if env:
        return Path(env)
    # Relative to wherever the server is run from (backend/)
    return Path("data/shared.db")


def _load_rules() -> list[CleanRule]:
    """Load rules from shared.db. Falls back to built-in defaults if DB unavailable."""
    db_path = _shared_db_path()
    if not db_path.exists():
        logger.debug("shared.db not found at %s — using built-in defaults.", db_path)
        return _builtin_rules()

    try:
        from db.shared_store import SharedStore
        store = SharedStore(db_path)
        raw = store.get_all_rules()
        if not raw:
            logger.debug("description_rules table is empty — using built-in defaults.")
            return _builtin_rules()
        rules = [
            CleanRule(
                label=entry["label"],
                patterns=[re.compile(p, re.IGNORECASE) for p in entry["patterns"]],
            )
            for entry in raw
            if entry.get("label") and entry.get("patterns")
        ]
        logger.debug("Loaded %d clean_description rules from shared DB.", len(rules))
        return rules
    except Exception as exc:
        logger.error("Failed to load rules from shared DB (%s) — using built-in defaults.", exc)
        return _builtin_rules()


def _builtin_rules() -> list[CleanRule]:
    """Hardcoded fallback rules — used only if the shared DB is unavailable."""
    raw: list[tuple[str, list[str]]] = [
        ("Nómina",              [r"NOMINA|SALARIO|SUELDO"]),
        ("Devolución",          [r"^ANULACION|DEVOLUCION|REEMBOLSO|REFUND"]),
        ("Bizum recibido",      [r"^BIZUM DE "]),
        ("Transferencia recibida", [r"^TRANSFERENCIA (INMEDIATA )?DE "]),
        ("Ingreso PayPal",      [r"PAYPAL.*CONCEPTO YYW"]),
        ("Alquiler",            [r"ALQUILER|ARRENDAMIENTO"]),
        ("Luz",                 [r"ENDESA|IBERDROLA|NATURGY|ELECTRICIDAD|WASABI ENERGIA"]),
        ("Agua",                [r"VIAQUA|AGUAS\b|AGUA\b"]),
        ("Calefacción",         [r"AGENCIA VILLAR|CALEFAC"]),
        ("Teléfono / Internet", [r"PEPEPHONE|MOVISTAR|VODAFONE|ORANGE|YOIGO|DIGI\b|MASMOVIL"]),
        ("Netflix",             [r"NETFLIX"]),
        ("Spotify",             [r"SPOTIFY"]),
        ("HBO / Max",           [r"HBO|MAX\b"]),
        ("Disney+",             [r"DISNEY"]),
        ("Prime Video",         [r"PRIME VIDEO"]),
        ("Apple TV+",           [r"APPLE.*TV"]),
        ("Twitch",              [r"TWITCH"]),
        ("Gimnasio",            [r"DREAMFIT|GIMNASIO|GYM\b|MCFIT|FITNESS"]),
        ("Club deportivo",      [r"XESTION DE ACTIVIDADES DEPORTIVAS|DEPORTIV"]),
        ("PayPal (recibo)",     [r"^RECIBO PayPal"]),
        ("Pagatelia",           [r"PAGATELIA"]),
        ("Lidl",                [r"LIDL"]),
        ("Mercadona",           [r"MERCADONA"]),
        ("Carrefour",           [r"CARREFOUR"]),
        ("Alcampo",             [r"ALCAMPO"]),
        ("Aldi",                [r"ALDI"]),
        ("Dia",                 [r"\bDIA\b"]),
        ("Supermercado",        [r"AHORRO|MERCAMAS|MERKASIA|MARKET SANTIAGO|AUTOSERVICIO|FRUTERIA|VERDULERIA|GRAN BAZAR"]),
        ("McDonald's",          [r"MC DONALDS|MCDONALDS"]),
        ("Burger King",         [r"BURGER KING|BK\d"]),
        ("Five Guys",           [r"FIVE GUYS"]),
        ("KFC",                 [r"\bKFC\b|\bPOPEYES\b"]),
        ("Kebab",               [r"KEBAB|GYROS|ROYAL DONNER"]),
        ("Restaurante",         [r"RESTAURANTE|WOK TOWN|SUPERTROPICAL|VIPS|A FUEGO LENTO|SABORES|ADELIA|MAMBARA|GINOS|LA MARIPEPA|LOS SECRETOS|LA NEGRA|VERMUTERIA|PIK POLLO|COSTA VELLA|GALIA|SOU SHUSHI|SUSHI|ROYAL KEBAB|ASIAN POCKET"]),
        ("Cafetería",           [r"\bCAFE\b|\bCAFETERIA\b|COFFEE|BOANDGO|FORNO|GRANIER|MOLLETE|TOSTA|BAKERY|CHURRERIA"]),
        ("Bar",                 [r"\bPUB\b|\bBAR\b|CERVECERIA|CANTINA|GALURESA"]),
        ("Parking",             [r"APARCAMIENTO|PARKING\b|PARKIA"]),
        ("Gasolina",            [r"PETROPRIX|PLENOIL|GASOLINERA|REPSOL.*GASOL|COMBUSTIBLE|CARBURANTE"]),
        ("Cabify",              [r"CABIFY"]),
        ("Uber",                [r"\bUBER\b"]),
        ("Bolt",                [r"\bBOLT\b"]),
        ("Free Now",            [r"FREE NOW"]),
        ("Transporte público",  [r"RENFE|ALSA|\bAVE\b|\bBUS\b|\bMETRO\b|CONCELLO DE SAN|\bTRAM\b"]),
        ("Peajes",              [r"PEAJE|AUTOPISTA|VIA T|TELEPEAJE"]),
        ("Neumáticos",          [r"NEUMATICOS|RUEDAS"]),
        ("Farmacia",            [r"FARMACIA"]),
        ("Médico / Clínica",    [r"CLINICA|MEDICO|DENTISTA|HOSPITAL|CENTRO.*MEDIC"]),
        ("Amazon",              [r"AMAZON"]),
        ("AliExpress",          [r"ALIEXPRESS"]),
        ("Wallapop",            [r"WALLAPOP"]),
        ("Vinted",              [r"VINTED"]),
        ("Zara",                [r"\bZARA\b"]),
        ("H&M",                 [r"\bHM\b|\bH&M\b"]),
        ("Mango",               [r"\bMANGO\b"]),
        ("Primark",             [r"PRIMARK"]),
        ("Decathlon",           [r"DECATHLON"]),
        ("PC Componentes",      [r"PCCOMPONENTES"]),
        ("MediaMarkt",          [r"MEDIAMARKT"]),
        ("Fnac",                [r"\bFNAC\b"]),
        ("Tienda online",       [r"WWW\."]),
        ("Compra",              [r"PRIMAPRIX|SUPEREGALO|SUPERREGALO|IPO CONCEPT"]),
        ("Cine",                [r"CINESA|\bCINE\b|WWW CINESA"]),
        ("Entradas / Evento",   [r"ENTRADAS|TICKET|EVENTO"]),
        ("Steam",               [r"STEAM"]),
        ("PlayStation",         [r"PLAYSTATION"]),
        ("Xbox",                [r"\bXBOX\b"]),
        ("Nintendo",            [r"NINTENDO"]),
        ("Videojuegos",         [r"HAPPYGAMES"]),
        ("Bizum enviado",       [r"^BIZUM A FAVOR DE"]),
        ("Transferencia enviada", [r"^TRANSFERENCIA (INMEDIATA )?A FAVOR DE"]),
        ("Cajero",              [r"RETIRADA DE EFECTIVO|CAJERO"]),
        ("Impuesto municipal",  [r"PAGO RECIBO DE AY\."]),
        ("Billetes de viaje",   [r"BIZUM VENTA BILLETES|COMPRA BIZUM.*BILLETES"]),
    ]
    return [
        CleanRule(label=label, patterns=[re.compile(p, re.IGNORECASE) for p in pats])
        for label, pats in raw
    ]


# ---------------------------------------------------------------------------
# Module-level rules — loaded once at import time
# ---------------------------------------------------------------------------

_RULES: list[CleanRule] = _load_rules()


def reload_rules() -> int:
    """Reload rules from shared DB. Returns the number of rules loaded."""
    global _RULES
    _RULES = _load_rules()
    return len(_RULES)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_description(description: str) -> str | None:
    """
    Returns a short human-friendly label for a raw bank description.
    Returns None if no rule matches.
    """
    for rule in _RULES:
        for pattern in rule.patterns:
            if pattern.search(description):
                return rule.label
    return None


def clean_transaction(tx: dict) -> dict:
    """Returns the transaction dict with clean_description filled (or None if unmatched)."""
    label = clean_description(tx["description"])
    return {
        **tx,
        "clean_description": label,
        "clean_description_source": "rule" if label else None,
    }
