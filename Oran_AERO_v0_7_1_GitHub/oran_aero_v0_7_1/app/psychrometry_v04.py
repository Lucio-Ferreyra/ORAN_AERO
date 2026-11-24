"""Consultas discretas a los valores publicados en el Excel actualizado de Orán AERO.
No extrapola ni sustituye valores ausentes; los casos de referencia se verifican en tests.
"""
import json
from decimal import Decimal, ROUND_DOWN
from functools import lru_cache
from .config import DATA_DIR

@lru_cache(maxsize=1)
def tables():
    return json.loads((DATA_DIR/'psicrometria_tablas.json').read_text(encoding='utf-8'))

def split_tenths(v):
    x=Decimal(str(v)).quantize(Decimal('0.1'),rounding=ROUND_DOWN)
    # -1.3 => encabezado -1, columna 3; -0.3 => fila 0, columna 3
    base=int(x)  # truncado hacia cero, no floor
    tenth=int(abs((x-Decimal(base))*10))
    return base,tenth

def _lookup(table, v, begin, end, head_offset=1):
    base, tenth=split_tenths(v)
    for row in table[begin:end]:
        if isinstance(row[0],(int,float)) and int(row[0])==base:
            out=row[head_offset+tenth]
            if not isinstance(out,(int,float)):
                raise ValueError('La tabla no contiene el valor solicitado')
            return Decimal(str(out))
    raise ValueError('Temperatura fuera de rango de la tabla seleccionada')

def humedad_tabla(v, option):
    """Consulta el valor de humedad en la tabla indicada."""
    t=tables()['Tabla Humedo']
    bounds={'I':(5,41),'II':(47,83),'III':(89,125)}
    if option not in bounds:raise ValueError('Tabla psicrométrica desconocida')
    return _lookup(t,v,*bounds[option])

def pr_tv(v):
    t=tables()['Tabla IV'];base,col=split_tenths(v)
    for row in t[7:]:
        if isinstance(row[0],(int,float)) and int(row[0])==base:
            pr=row[1+col*2];tv=row[2+col*2]
            if not isinstance(pr,(int,float)) or not isinstance(tv,(int,float)):break
            return float(pr),float(tv)
    raise ValueError('Resultado fuera de la Tabla IV')

def nearest_cell(matrix, v, start, end, result_kind):
    target=Decimal(str(v)); options=[]
    for row in matrix[start:end]:
        for col in range(1,11):
            cell=row[col] if len(row)>col else None
            if isinstance(cell,(int,float)):
                options.append((abs(Decimal(str(cell))-target),-Decimal(str(cell)),row[0],col-1,cell))
    if not options:raise ValueError('Tabla sin datos utilizables')
    _,__,label,c,cell=min(options,key=lambda x:(x[0],x[1]))
    if result_kind=='second':
        # La tabla II: coordenada fila + décima de columna -> valor intermedio
        return float(Decimal(str(label))+Decimal(c)/10),cell
    # Tabla I: fila de decenas + unidad de columna => HR
    return int(label)+c,cell

def calculate(ts,th,option='I'):
    if Decimal(str(th))>=0:option='I'
    a=humedad_tabla(th,option)
    sum_value=a+Decimal(str(ts))
    pr,tv=pr_tv(sum_value)
    # HR: consultar PR y TS DIRECTAMENTE en Humedad Relativa II;
    # diferencia -> buscar celda en Humedad Relativa I (no en Tabla Húmedo).
    pr_lookup=_lookup(tables()['Humedad Relativa II'],pr,4,120)
    ts_lookup=_lookup(tables()['Humedad Relativa II'],ts,4,120)
    delta=pr_lookup-ts_lookup
    hr,matched1=nearest_cell(tables()['Humedad Relativa I'],delta,4,25,'first')
    matched2=delta
    intermediate=float(delta)
    return {'dew_point_c':pr,'vapor_hpa':tv,'relative_humidity_pct':hr,'psychro_table':option,
            'psychro_trace':{'th_lookup':float(a),'sum_for_iv':float(sum_value),
            'pr_lookup':float(pr_lookup),'ts_lookup':float(ts_lookup),'difference':float(delta),
            'hr2_value':float(matched2),'hr2_result':intermediate,'hr1_match':float(matched1)}}
