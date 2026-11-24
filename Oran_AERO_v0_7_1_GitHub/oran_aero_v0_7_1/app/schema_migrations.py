"""Migraciones aditivas para bases SQLite creadas con Orán AERO anterior.

Nunca reescribimos versiones ni borramos tablas. En MySQL la guía exige crear la
base v2 por separado y ejecutar el esquema nuevo desde cero.
"""
from sqlalchemy import inspect, text
from .db import Base, engine

ALTERATIONS = {
    "stations": {"wind_method": "VARCHAR(20) DEFAULT 'estimado'", "wind_iw": "VARCHAR(1) DEFAULT '3'"},
    "observations": {"source_report_id": "INTEGER"},
    "reports": {
        "root_report_id": "INTEGER", "values_snapshot": "JSON", "derived_snapshot": "JSON",
        "instrument_snapshot": "JSON", "observations_snapshot": "JSON"},
    "instruments": {
        "correction_value": "FLOAT DEFAULT 0", "correction_mode": "VARCHAR(10) DEFAULT 'SC'",
        "brand": "VARCHAR(160) DEFAULT 'S/D'", "physical_state": "VARCHAR(12) DEFAULT 'Bueno'",
        "patrimony_number": "VARCHAR(100)"},
}


def initialize_schema():
    """Crea tablas y agrega campos compatibles con datos existentes."""
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table, fields in ALTERATIONS.items():
            if not inspector.has_table(table):
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, column_type in fields.items():
                if name not in existing:
                    # Nombres de tabla y columna definidos estáticamente arriba.
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}"))
