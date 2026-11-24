"""Motor de consultas de tablas Orán AERO.

Las consultas usan las tablas suministradas por la estación. No reemplazan
observaciones ausentes ni aplican fórmulas meteorológicas no autorizadas.
"""
from __future__ import annotations
from functools import lru_cache
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from openpyxl import load_workbook
from .config import DATA_DIR

WORKBOOK = DATA_DIR / "Tablas_Oran_Aero.xlsx"

@lru_cache(maxsize=1)
def _rows():
    """Carga filas no vacías de la tabla indicada."""
    if not WORKBOOK.exists():
        raise FileNotFoundError(f"No se encuentra el libro de tablas: {WORKBOOK}")
    wb = load_workbook(WORKBOOK, data_only=True, read_only=True)
    try:
        return {name: [list(row) for row in wb[name].iter_rows(values_only=True)] for name in wb.sheetnames}
    finally:
        wb.close()

def _num(value):
    """Convierte valores de tabla a número para su lectura."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _nearest(items, target, *, tie_higher=True):
    """Encuentra la equivalencia más cercana entre códigos disponibles."""
    valid = [x for x in items if x is not None]
    if not valid:
        raise ValueError("La tabla no contiene valores numéricos para esta consulta.")
    distance = min(abs(x - target) for x in valid)
    tied = [x for x in valid if abs(x - target) == distance]
    return max(tied) if tie_higher else min(tied)

def convert_hpa_to_mmhg(hpa: float) -> dict:
    """Busca hPa en la columna de equivalencias y devuelve mmHg más cercano; empate, superior."""
    rows = _rows()["Conversion_mmHg_hPa"]
    pairs = [(_num(r[0]), _num(r[1])) for r in rows[4:] if len(r) >= 2]
    pairs = [(mm, hp) for mm, hp in pairs if mm is not None and hp is not None]
    chosen_hpa = _nearest([hp for _, hp in pairs], float(hpa), tie_higher=True)
    mmhg = _nearest([mm for mm, hp in pairs if hp == chosen_hpa], float(hpa) * 3 / 4, tie_higher=True)
    # Si hay más de una equivalencia con el hPa seleccionado, priorizar la presión mmHg más alta.
    return {"input_hpa": float(hpa), "matched_hpa": chosen_hpa, "mmhg": max(mm for mm, hp in pairs if hp == chosen_hpa)}

def convert_mmhg_to_hpa(mmhg: float) -> dict:
    """Convierte milímetros de mercurio a hPa usando la tabla."""
    rows = _rows()["Conversion_mmHg_hPa"]
    pairs = [(_num(r[0]), _num(r[1])) for r in rows[4:] if len(r) >= 2]
    pairs = [(mm, hp) for mm, hp in pairs if mm is not None and hp is not None]
    chosen = _nearest([mm for mm, _ in pairs], float(mmhg), tie_higher=True)
    return {"input_mmhg": float(mmhg), "mmhg": chosen, "hpa": next(hp for mm, hp in pairs if mm == chosen)}

def _decimal_lookup(sheet: str, value: float, first_data_row: int, header_row: int, label_col: int = 0):
    """Busca por parte entera en la primera columna y décima en encabezado 0..9."""
    rows = _rows()[sheet]
    value = float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_DOWN))
    integer = int(value // 1)
    tenth = int((Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_DOWN) - Decimal(integer)) * 10)
    if tenth == 10:
        integer += 1; tenth = 0
    headers = {int(round(float(v))): i for i, v in enumerate(rows[header_row - 1]) if i > 0 and _num(v) is not None}
    col = headers.get(tenth)
    if col is None:
        raise ValueError(f"No se encontró la décima {tenth} en {sheet}.")
    for row in rows[first_data_row - 1:]:
        row_value = _num(row[label_col]) if len(row) > label_col else None
        if row_value is not None and int(row_value) == integer:
            result = _num(row[col]) if len(row) > col else None
            if result is None:
                raise ValueError(f"La celda correspondiente de {sheet} está vacía.")
            return result
    raise ValueError(f"El valor {value:.1f} está fuera del rango de {sheet}.")

def psychrometer_depression(wet_bulb_c: float, dry_bulb_c: float, table: str = "Tabla I") -> dict:
    """Devuelve la diferencia tabulada de la tabla psicrométrica seleccionada."""
    if table not in {"Tabla I", "Tabla II", "Tabla III"}:
        raise ValueError("Seleccione Tabla I, Tabla II o Tabla III según el instrumento y el procedimiento de la estación.")
    if wet_bulb_c >= 0 and table != "Tabla I":
        raise ValueError("Para TH igual o superior a 0 corresponde Tabla I.")
    from .psychrometry_v04 import humedad_tabla
    result=humedad_tabla(wet_bulb_c,table.split()[-1])
    return {"table":table,"wet_bulb_c":float(wet_bulb_c),"tabulated_value":float(result)}

def dewpoint_and_vapor_tension(table_iv_input_c: float) -> dict:
    """Busca el valor intermedio en Tabla IV y devuelve PR y TV de la misma celda."""
    rows = _rows()["Tabla IV"]
    value = float(Decimal(str(table_iv_input_c)).quantize(Decimal("0.1"), rounding=ROUND_DOWN))
    integer = int(value // 1)
    tenth = int((Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_DOWN) - Decimal(integer)) * 10)
    if tenth == 10: integer += 1; tenth = 0
    col = 1 + tenth * 2
    for row in rows[7:]:
        label = _num(row[0]) if row else None
        if label is not None and int(label) == integer:
            pr = _num(row[col]) if len(row) > col else None
            tv = _num(row[col + 1]) if len(row) > col + 1 else None
            if pr is None or tv is None:
                raise ValueError("La celda de Tabla IV no contiene PR y TV.")
            return {"table_input_c": value, "dew_point_c": pr, "vapor_tension_hpa": tv}
    raise ValueError(f"El valor {value:.1f} °C está fuera del rango de Tabla IV.")

def qnh_from_station_pressure(station_pressure_hpa: float) -> dict:
    """Lee el QNH a partir de la presión de estación."""
    rows = _rows()["QNH"]
    value = float(Decimal(str(station_pressure_hpa)).quantize(Decimal("0.1"), rounding=ROUND_DOWN))
    integer = int(value // 1)
    tenth = int((Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_DOWN) - Decimal(integer)) * 10)
    if tenth == 10: integer += 1; tenth = 0
    for row in rows[7:]:
        row_pressure = _num(row[0]) if row else None
        if row_pressure is not None and int(row_pressure) == integer:
            col = 1 + tenth
            result = _num(row[col]) if len(row) > col else None
            if result is None:
                raise ValueError("El valor de presión no tiene resultado en la tabla QNH.")
            return {"station_pressure_hpa": value, "qnh_hpa": result}
    raise ValueError(f"La presión {value:.1f} hPa está fuera del rango de la tabla QNH.")

def _range_label(label: str):
    # Formato de la planilla: "-8.0 a -6.1" o "30.0 a 31.9".
    """Construye la etiqueta del intervalo usado en la consulta."""
    try:
        left, right = label.split(" a ")
        return float(left), float(right)
    except (ValueError, AttributeError):
        return None

def d4_correction(average_temperature_c: float, station_pressure_mmhg: float) -> dict:
    """Cruza rango de temperatura promedio (filas) con rango de presión mmHg (columnas)."""
    rows = _rows()["Tabla_D4"]
    temp = float(average_temperature_c); pressure = float(station_pressure_mmhg)
    # Las filas 9+ contienen rangos de temperatura y valores de corrección.
    row_match = None
    for row in rows[8:]:
        limits = _range_label(str(row[0]) if row else "")
        if limits and limits[0] <= temp <= limits[1]:
            row_match = row; break
    if row_match is None:
        raise ValueError(f"La temperatura promedio {temp:.1f} °C está fuera del rango de Tabla D-4.")
    # Encabezados en filas 7 y 8 definen bandas de presión de 5 mmHg.
    lower = rows[6]; upper = rows[7]
    for col in range(1, min(len(lower), len(upper), len(row_match))):
        lo = _num(lower[col]); hi = _num(upper[col])
        if lo is not None and hi is not None and lo <= pressure <= hi:
            result = _num(row_match[col])
            if result is None:
                raise ValueError("La celda de Tabla D-4 está vacía.")
            return {"average_temperature_c": temp, "station_pressure_mmhg": pressure,
                    "temperature_range": rows[8 + rows[8:].index(row_match)][0],
                    "pressure_range_mmhg": [lo, hi], "correction_mmhg": result}
    raise ValueError(f"La presión {pressure:.1f} mmHg está fuera del rango de Tabla D-4.")

def calculate_qff(ts_c: float, ts_12h_c: float, station_pressure_hpa: float) -> dict:
    """Calcula el QFF siguiendo el procedimiento escrito de Orán AERO."""
    average = (float(ts_c) + float(ts_12h_c)) / 2
    station_mm = convert_hpa_to_mmhg(float(station_pressure_hpa))
    correction = d4_correction(average, station_mm["mmhg"])
    corrected_mm = station_mm["mmhg"] + correction["correction_mmhg"]
    qff = convert_mmhg_to_hpa(corrected_mm)
    return {
        "ts_current_c": float(ts_c),
        "ts_12h_c": float(ts_12h_c),
        "average_temperature_c": average,
        "station_pressure_hpa_input": float(station_pressure_hpa),
        "station_pressure_hpa_table": station_mm["matched_hpa"],
        "station_pressure_mmhg": station_mm["mmhg"],
        "d4_correction_mmhg": correction["correction_mmhg"],
        "corrected_station_pressure_mmhg": corrected_mm,
        "qff_hpa": qff["hpa"],
        "table_trace": {"d4_temperature_range": correction["temperature_range"],
                        "d4_pressure_range_mmhg": correction["pressure_range_mmhg"]}
    }
