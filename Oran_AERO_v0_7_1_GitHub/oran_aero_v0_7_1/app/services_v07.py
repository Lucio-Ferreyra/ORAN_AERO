"""Consultas históricas aisladas del motor de cifrado SYNOP.

El registro diario utiliza 00:00..00:00 UTC. La humedad de sección 5 usa
00:00..24:00 HOA del día local anterior; jamás intercambiamos esas ventanas.
"""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from .models import AuditLog, DailyExtremes, Observation, Report
from .synop_v03 import BEAUFORT_KT


def numeric(raw):
    """Convierte entradas numéricas a Decimal sin redondearlas."""
    try:
        return Decimal(str(raw).replace(",", ".")) if raw not in (None, "") else None
    except (TypeError, ValueError, InvalidOperation):
        return None


def as_utc_naive(moment):
    """Normaliza fechas para las consultas históricas de la base."""
    if moment.tzinfo:
        return moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def latest_reports(db: Session, station_id: int, start_utc: datetime, end_utc: datetime):
    """Por instante conserva la revisión más reciente del informe."""
    matches = (
        db.query(Report, Observation)
        .join(Observation, Report.observation_id == Observation.id)
        .filter(Observation.station_id == station_id,
                Observation.observation_time_utc >= as_utc_naive(start_utc),
                Observation.observation_time_utc < as_utc_naive(end_utc),
                Report.status == "finalizado")
        .order_by(Report.id.asc()).all()
    )
    selected = {}
    for report, obs in matches:
        selected[obs.observation_time_utc.replace(tzinfo=None)] = (report, obs)
    return sorted(selected.values(), key=lambda row: row[1].observation_time_utc)


def _latest_extreme(rows, metric, *, maximum=True):
    """Busca el máximo o mínimo calculado en informes guardados."""
    best = None
    for report, obs in rows:
        value = numeric((report.derived_snapshot or {}).get(metric))
        if value is None:
            continue
        if best is None or (value > best[0] if maximum else value < best[0]):
            best = (value, obs.observation_time_utc, report.id)
    return ({"value": str(best[0]), "time_utc": best[1].isoformat(), "report_id": best[2]}
            if best else None)


def _raw_extreme(rows, field, *, maximum=True):
    """Busca extremos instrumentales en informes guardados."""
    best = None
    for report, obs in rows:
        value = numeric((report.derived_snapshot or {}).get(field))
        if value is None:continue
        if best is None or (value > best[0] if maximum else value < best[0]):
            best = (value, obs.observation_time_utc, report.id)
    return ({"value": str(best[0]), "time_utc": best[1].isoformat(), "report_id": best[2]}
            if best else None)


def _wind_beaufort(knots: int):
    # Rangos de la escala Beaufort por velocidad medida en nudos.
    """Convierte los nudos registrados a escala Beaufort."""
    lower_bounds=(0,1,4,7,11,17,22,28,34,41,48,56,64)
    return max(i for i, lower in enumerate(lower_bounds) if knots >= lower)


def compute_daily_extremes(db: Session, station_id: int, day: date):
    """Calcula con informes confirmados [día 00 UTC, siguiente 00 UTC)."""
    start = datetime.combine(day, time.min)
    rows = latest_reports(db, station_id, start, start + timedelta(days=1))
    result = {
        "day_utc": day.isoformat(), "report_count": len(rows),
        "temperature_max": _raw_extreme(rows, "temp_max_corrected", maximum=True),
        "temperature_min": _raw_extreme(rows, "temp_min_corrected", maximum=False),
        "wet_max": _latest_extreme(rows, "th_corrected", maximum=True),
        "wet_min": _latest_extreme(rows, "th_corrected", maximum=False),
        "vapor_max": _latest_extreme(rows, "vapor_hpa", maximum=True),
        "vapor_min": _latest_extreme(rows, "vapor_hpa", maximum=False),
        "dew_max": _latest_extreme(rows, "dew_point_c", maximum=True),
        "dew_min": _latest_extreme(rows, "dew_point_c", maximum=False),
        "hr_max": _latest_extreme(rows, "relative_humidity_pct", maximum=True),
        "hr_min": _latest_extreme(rows, "relative_humidity_pct", maximum=False),
        "wind_max": None,
    }
    for report, obs in rows:
        knots = numeric((report.derived_snapshot or {}).get("wind_kt"))
        if knots is None:continue
        prev=result["wind_max"]
        if prev is not None and knots <= numeric(prev["knots"]):continue
        raw=(report.values_snapshot or {})
        dd=str(raw.get("wind_dd", ""))
        bft=numeric(raw.get("wind_force")) if raw.get("wind_unit")=="3" else None
        result["wind_max"]={
            "knots":str(knots), "beaufort":int(bft) if bft is not None and 0<=bft<=12 else _wind_beaufort(int(knots)),
            "direction_dd": dd, "direction_degrees":int(dd)*10 if dd.isdigit() else None,
            "time_utc": obs.observation_time_utc.isoformat(), "report_id":report.id}
    return result


def refresh_daily_extremes(db: Session, station_id: int, day: date, actor_id: int | None):
    """Actualiza el resumen diario y registra diferencias en auditoría."""
    new = compute_daily_extremes(db, station_id, day)
    record = db.query(DailyExtremes).filter_by(station_id=station_id, date_utc=day.isoformat()).first()
    if record:
        before = record.values
        if before != new:
            db.add(AuditLog(user_id=actor_id, action="actualizar_extremos",
                entity_type="daily_extremes", entity_id=str(record.id),
                detail={"anterior":before, "nuevo":new}))
            record.values = new
            record.updated_at = datetime.now(timezone.utc)
    else:
        record = DailyExtremes(station_id=station_id, date_utc=day.isoformat(), values=new)
        db.add(record)
    db.flush()
    return record


def previous_day_hoa_hr(db: Session, station_id: int, observation_time_utc: datetime):
    """Obtiene extremos de HR del día civil anterior en HOA."""
    local_tz=ZoneInfo("America/Argentina/Salta")
    observed=observation_time_utc.replace(tzinfo=timezone.utc) if observation_time_utc.tzinfo is None else observation_time_utc
    previous_local=observed.astimezone(local_tz).date()-timedelta(days=1)
    local_start=datetime.combine(previous_local,time.min,tzinfo=local_tz)
    start=local_start.astimezone(timezone.utc)
    rows=latest_reports(db,station_id,start,start+timedelta(days=1))
    maxima=_latest_extreme(rows,"relative_humidity_pct",maximum=True)
    minima=_latest_extreme(rows,"relative_humidity_pct",maximum=False)
    return {"max":maxima,"min":minima,"period_hoa":previous_local.isoformat()}


def week_precipitation(db: Session, station_id: int, target_utc: datetime, current_values:dict):
    """Últimas 7 observaciones de 12 UTC (sábado hasta viernes, incluidos)."""
    if target_utc.weekday()!=4 or target_utc.hour!=12:
        return None
    start=target_utc.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=6)
    end=start+timedelta(days=7)
    rows=latest_reports(db,station_id,start,end)
    by_day={obs.observation_time_utc.date():report for report,obs in rows if obs.observation_time_utc.hour==12}
    total=Decimal("0")
    has_rain=False
    all_no=True
    count=0
    for offset in range(7):
        day=start.date()+timedelta(days=offset)
        if day == target_utc.date():
            has_daily_rain=current_values.get("precip_24h_has_rain")
            no_daily_rain=current_values.get("precip_24h_all_no")
            mm=current_values.get("precip_24h_mm")
        else:
            report=by_day.get(day)
            if not report:
                all_no=False;continue
            derived=report.derived_snapshot or {}
            has_daily_rain=derived.get("precip_24h_has_rain")
            no_daily_rain=derived.get("precip_24h_all_no")
            mm=derived.get("precip_24h_mm")
        if has_daily_rain is not True and no_daily_rain is not True:
            all_no=False;continue
        count+=1
        if has_daily_rain:
            all_no=False;has_rain=True
            measured=numeric(mm)
            if measured is not None and measured>=0:total+=measured
    return {"total":str(total),"has_rain":has_rain,"all_no":all_no and count==7,"available_days":count}
