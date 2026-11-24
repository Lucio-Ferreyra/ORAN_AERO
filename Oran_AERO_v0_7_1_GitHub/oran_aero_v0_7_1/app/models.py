"""Modelos ORM de usuarios, estación, instrumentos, informes e historial."""

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow():
    """Devuelve una marca de tiempo actual en UTC."""
    return datetime.now(timezone.utc)

class User(Base):
    """Cuenta y permisos de acceso."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(30), default="observador")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Station(Base):
    """Identificación y parámetros de la estación."""
    __tablename__ = "stations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="Estación Meteorológica Orán AERO")
    block_number: Mapped[str] = mapped_column(String(2), default="87")
    station_number: Mapped[str] = mapped_column(String(3), default="016")
    latitude: Mapped[str] = mapped_column(String(40), default="23° 09' S")
    longitude: Mapped[str] = mapped_column(String(40), default="64° 19' W")
    runway_elevation_m: Mapped[float] = mapped_column(Float, default=357.0)
    wind_method: Mapped[str] = mapped_column(String(20), default="estimado")
    wind_iw: Mapped[str] = mapped_column(String(1), default="3")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class Observation(Base):
    """Datos y horario UTC de una observación."""
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), default=1)
    observer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    observation_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(40), default="iniciado")
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    source_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reports: Mapped[list["Report"]] = relationship(back_populates="observation")

class Report(Base):
    """Informe confirmado y su versión histórica."""
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(20), default="SYNOP")
    status: Mapped[str] = mapped_column(String(40), default="listo_para_revision")
    message: Mapped[str] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(40), default="0.1-no-validado")
    table_version: Mapped[str] = mapped_column(String(80), default="Tablas_Oran_Aero.xlsx-original")
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    root_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    values_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    derived_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    instrument_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    observations_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    observation: Mapped[Observation] = relationship(back_populates="reports")

class Instrument(Base):
    """Identificación, estado y correcciones del instrumental."""
    __tablename__ = "instruments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    instrument_type: Mapped[str] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brand: Mapped[str] = mapped_column(String(160), default="S/D")
    physical_state: Mapped[str] = mapped_column(String(12), default="Bueno")
    patrimony_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="en_servicio")
    correction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_mode: Mapped[str] = mapped_column(String(10), default='SC')
    correction_value: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class AuditLog(Base):
    """Registro de cambios administrativos."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailyExtremes(Base):
    """Resumen diario UTC; sus rangos son independientes de la Sección 5 (HOA)."""
    __tablename__ = "daily_extremes"
    __table_args__ = (UniqueConstraint("station_id", "date_utc", name="uq_daily_extremes_station_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    date_utc: Mapped[str] = mapped_column(String(10), index=True)
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
