"""Identificación SYNOP: hora UTC, indicador de viento y estación."""
from datetime import datetime, timedelta, timezone

RULE_VERSION = "0.1-seccion-0"

def round_to_nearest_utc_hour(dt: datetime) -> datetime:
    """Redondea al entero UTC más cercano; en el punto medio avanza a la hora siguiente."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    floor = dt.replace(minute=0, second=0, microsecond=0)
    return floor if dt - floor < timedelta(minutes=30) else floor + timedelta(hours=1)

def build_section_0(observation_time_utc: datetime, iw: str, block: str = "87", station: str = "016") -> str:
    """Cifra AAXX, fecha UTC y el indicador de viento configurado."""
    if iw not in {"0", "1", "3", "4"}:
        raise ValueError("iw debe ser 0, 1, 3 o 4 según la tabla de clave 1855.")
    rounded = round_to_nearest_utc_hour(observation_time_utc)
    return f"AAXX {rounded.day:02d}{rounded.hour:02d}{iw} {block}{station}"

def build_draft(observation_time_utc: datetime, iw: str, block: str = "87", station: str = "016") -> dict:
    """Devuelve la identificación de Sección 0 con sus componentes."""
    section_0 = build_section_0(observation_time_utc, iw, block, station)
    return {
        "message": section_0,
        "groups": [{"section": "0", "group": "AAXX", "source": "fijo"},
                   {"section": "0", "group": section_0.split()[1], "source": "fecha/hora UTC + observador (iw)"},
                   {"section": "0", "group": f"{block}{station}", "source": "configuración de estación"}],
        "warnings": [],
        "rule_version": RULE_VERSION,
    }
