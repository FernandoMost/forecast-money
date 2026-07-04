"""
categorizer/description_cleaner.py

Rule-based cleaner that maps raw bank descriptions to short human-friendly labels.
Rules are loaded from config/clean_description_rules.yaml.
If the config file is not found, falls back to built-in defaults.

Order matters — first match wins.
Returns None if no rule matches (AI can fill it if enabled).

To customize: edit config/clean_description_rules.yaml and run POST /api/v1/recategorize.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CleanRule:
    label: str
    patterns: list[re.Pattern]


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _find_config() -> Path | None:
    candidates = [
        Path(__file__).parent.parent.parent / "config" / "clean_description_rules.yaml",
        Path(__file__).parent.parent / "config" / "clean_description_rules.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_rules() -> list[CleanRule]:
    config_path = _find_config()
    if config_path is None:
        logger.warning("clean_description_rules.yaml not found — using built-in defaults.")
        return _builtin_rules()

    try:
        with config_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
        rules = [
            CleanRule(
                label=entry["label"],
                patterns=[re.compile(p, re.IGNORECASE) for p in entry.get("patterns", [])],
            )
            for entry in raw
            if entry.get("label")
        ]
        logger.debug("Loaded %d clean_description rules from %s", len(rules), config_path)
        return rules
    except Exception as exc:
        logger.error("Failed to load clean_description_rules.yaml (%s) — using built-in defaults.", exc)
        return _builtin_rules()


def _builtin_rules() -> list[CleanRule]:
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
    """Reload rules from YAML. Returns the number of rules loaded."""
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
