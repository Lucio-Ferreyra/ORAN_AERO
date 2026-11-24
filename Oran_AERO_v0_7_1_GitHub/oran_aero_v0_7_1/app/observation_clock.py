"""Asignación de horas para nuevas observaciones SYNOP.

Las observaciones definitivas tienen una hora UTC estable. Una corrección crea
otra versión del mismo instante, mientras que un SYNOP nuevo usa la hora que
sigue a la última observación original confirmada de la estación.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import Observation, Report
from .synop import round_to_nearest_utc_hour


def utc_naive(instant: datetime) -> datetime:
    """Normaliza a UTC sin tzinfo para SQLAlchemy/SQLite y MySQL."""
    if instant.tzinfo is not None:
        return instant.astimezone(timezone.utc).replace(tzinfo=None)
    return instant


def next_synop_hour(
    db: Session,
    station_id: int,
    *,
    now_utc: datetime | None = None,
) -> datetime:
    """Devuelve la próxima hora UTC de la estación, sin repetir la anterior.

    - Si hay informes confirmados, avanza una hora desde el más reciente POR
      FECHA DE OBSERVACIÓN, no desde el último informe que fue modificado.
    - Las correcciones conservan el instante original y no adelantan el reloj.
    - Al crear el primer SYNOP se toma la hora UTC real, redondeada según la
      regla acordada, incluyendo el cambio de día/mes/año.
    """
    last = (
        db.query(Observation.observation_time_utc)
        .join(Report, Report.observation_id == Observation.id)
        .filter(
            Observation.station_id == station_id,
            Observation.source_report_id.is_(None),
            Report.report_type == "SYNOP",
            Report.status == "finalizado",
        )
        .order_by(Observation.observation_time_utc.desc())
        .first()
    )
    if last is not None:
        return utc_naive(last[0]).replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(hours=1)

    instant = now_utc if now_utc is not None else datetime.now(timezone.utc)
    return utc_naive(round_to_nearest_utc_hour(instant))


def utc_iso(instant: datetime) -> str:
    """Fecha UTC inequívoca para JavaScript (evita interpretar la hora local)."""
    return utc_naive(instant).isoformat(timespec="seconds") + "Z"
