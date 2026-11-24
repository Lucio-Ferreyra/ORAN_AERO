"""Lectura de las hojas originales para consulta en pantalla; no altera las tablas fuente."""
from functools import lru_cache
from openpyxl import load_workbook
from .config import DATA_DIR

WORKBOOK = DATA_DIR / "Tablas_Oran_Aero.xlsx"

@lru_cache(maxsize=1)
def get_table_names():
    """Enumera las hojas de consulta de la estación."""
    if not WORKBOOK.exists():
        return []
    wb = load_workbook(WORKBOOK, read_only=True, data_only=False)
    try:
        return wb.sheetnames
    finally:
        wb.close()

def get_table(sheet_name: str):
    """Lee las celdas de una hoja por su nombre."""
    if sheet_name not in get_table_names():
        raise KeyError(sheet_name)
    wb = load_workbook(WORKBOOK, read_only=True, data_only=False)
    try:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            vals = ["" if v is None else str(v) for v in row]
            while vals and vals[-1] == "":
                vals.pop()
            if any(vals):
                rows.append(vals)
        return rows
    finally:
        wb.close()
