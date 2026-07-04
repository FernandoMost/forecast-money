"""
categorizer/description_cleaner.py

Rule-based cleaner that maps raw bank description strings to short, human-friendly labels.
Works the same way as rule_categorizer.py: ordered list, first match wins, no IO.

Examples:
  "COMPRA INTERNET EN AMAZON PAYMENTS"   → "Amazon"
  "PAGO MOVIL EN MERCADONA 0123"         → "Mercadona"
  "RETIRADA DE EFECTIVO CAJERO 001"      → "Cajero"
  "RECIBO NETFLIX"                       → "Netflix"
  "BIZUM A FAVOR DE JUAN GARCIA"         → "Bizum enviado"
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CleanRule:
    label: str
    patterns: list[re.Pattern]


# ---------------------------------------------------------------------------
# Rule table — order is significant (first match wins)
# ---------------------------------------------------------------------------

_RAW_RULES: list[tuple[str, list[str]]] = [
    # --- Income ---
    ("Nómina",              [r"NOMINA|SALARIO|SUELDO"]),
    ("Devolución",          [r"^ANULACION|DEVOLUCION|REEMBOLSO|REFUND"]),
    ("Bizum recibido",      [r"^BIZUM DE "]),
    ("Transferencia recibida", [r"^TRANSFERENCIA (INMEDIATA )?DE "]),
    ("Ingreso PayPal",      [r"PAYPAL.*CONCEPTO YYW"]),

    # --- Housing ---
    ("Alquiler",            [r"ALQUILER|ARRENDAMIENTO"]),
    ("Luz",                 [r"ENDESA|IBERDROLA|NATURGY|ELECTRICIDAD|WASABI ENERGIA"]),
    ("Agua",                [r"VIAQUA|AGUAS\b|AGUA\b"]),
    ("Calefacción",         [r"AGENCIA VILLAR|CALEFAC"]),
    ("Teléfono / Internet", [r"PEPEPHONE|MOVISTAR|VODAFONE|ORANGE|YOIGO|DIGI\b|MASMOVIL"]),

    # --- Subscriptions ---
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

    # --- Groceries ---
    ("Lidl",                [r"LIDL"]),
    ("Mercadona",           [r"MERCADONA"]),
    ("Carrefour",           [r"CARREFOUR"]),
    ("Alcampo",             [r"ALCAMPO"]),
    ("Aldi",                [r"ALDI"]),
    ("Dia",                 [r"\bDIA\b"]),
    ("Supermercado",        [r"AHORRO|MERCAMAS|MERKASIA|MARKET SANTIAGO|AUTOSERVICIO|FRUTERIA|VERDULERIA|GRAN BAZAR"]),

    # --- Restaurants & Leisure ---
    ("McDonald's",          [r"MC DONALDS|MCDONALDS"]),
    ("Burger King",         [r"BURGER KING|BK\d"]),
    ("Five Guys",           [r"FIVE GUYS"]),
    ("KFC",                 [r"\bKFC\b|\bPOPEYES\b"]),
    ("Kebab",               [r"KEBAB|GYROS|ROYAL DONNER"]),
    ("Restaurante",         [r"RESTAURANTE|WOK TOWN|SUPERTROPICAL|VIPS|A FUEGO LENTO|SABORES|ADELIA|MAMBARA|GINOS|LA MARIPEPA|LOS SECRETOS|LA NEGRA|VERMUTERIA|PIK POLLO|COSTA VELLA|GALIA|SOU SHUSHI|SUSHI|ROYAL KEBAB|ASIAN POCKET"]),
    ("Cafetería",           [r"\bCAFE\b|\bCAFETERIA\b|COFFEE|BOANDGO|FORNO|GRANIER|MOLLETE|TOSTA|BAKERY|CHURRERIA"]),
    ("Bar",                 [r"\bPUB\b|\bBAR\b|CERVECERIA|CANTINA|GALURESA"]),

    # --- Transport ---
    ("Parking",             [r"APARCAMIENTO|PARKING\b|PARKIA"]),
    ("Gasolina",            [r"PETROPRIX|PLENOIL|GASOLINERA|REPSOL.*GASOL|COMBUSTIBLE|CARBURANTE"]),
    ("Cabify",              [r"CABIFY"]),
    ("Uber",                [r"\bUBER\b"]),
    ("Bolt",                [r"\bBOLT\b"]),
    ("Free Now",            [r"FREE NOW"]),
    ("Transporte público",  [r"RENFE|ALSA|\bAVE\b|\bBUS\b|\bMETRO\b|CONCELLO DE SAN|\bTRAM\b"]),
    ("Peajes",              [r"PEAJE|AUTOPISTA|VIA T|TELEPEAJE"]),
    ("Neumáticos",          [r"NEUMATICOS|RUEDAS"]),

    # --- Health ---
    ("Farmacia",            [r"FARMACIA"]),
    ("Médico / Clínica",    [r"CLINICA|MEDICO|DENTISTA|HOSPITAL|CENTRO.*MEDIC"]),

    # --- Shopping ---
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

    # --- Entertainment ---
    ("Cine",                [r"CINESA|\bCINE\b|WWW CINESA"]),
    ("Entradas / Evento",   [r"ENTRADAS|TICKET|EVENTO"]),
    ("Steam",               [r"STEAM"]),
    ("PlayStation",         [r"PLAYSTATION"]),
    ("Xbox",                [r"\bXBOX\b"]),
    ("Nintendo",            [r"NINTENDO"]),
    ("Videojuegos",         [r"HAPPYGAMES"]),

    # --- Transfers / Bizum out ---
    ("Bizum enviado",       [r"^BIZUM A FAVOR DE"]),
    ("Transferencia enviada", [r"^TRANSFERENCIA (INMEDIATA )?A FAVOR DE"]),

    # --- Cash ---
    ("Cajero",              [r"RETIRADA DE EFECTIVO|CAJERO"]),

    # --- Taxes / Admin ---
    ("Impuesto municipal",  [r"PAGO RECIBO DE AY\."]),
    ("Billetes de viaje",   [r"BIZUM VENTA BILLETES|COMPRA BIZUM.*BILLETES"]),
]


_RULES: list[CleanRule] = [
    CleanRule(
        label=label,
        patterns=[re.compile(p, re.IGNORECASE) for p in pats],
    )
    for label, pats in _RAW_RULES
]


def clean_description(description: str) -> str | None:
    """
    Returns a short human-friendly label for a raw bank description.
    Returns None if no rule matches (caller decides what to do — e.g. use IA or keep raw).
    """
    for rule in _RULES:
        for pattern in rule.patterns:
            if pattern.search(description):
                return rule.label
    return None


def clean_transaction(tx: dict) -> dict:
    """
    Returns the transaction dict with clean_description filled (or None if unmatched).
    Source is always 'rule' here.
    """
    label = clean_description(tx["description"])
    return {
        **tx,
        "clean_description": label,
        "clean_description_source": "rule" if label else None,
    }
