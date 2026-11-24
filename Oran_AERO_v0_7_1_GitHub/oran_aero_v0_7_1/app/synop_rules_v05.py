"""Reglas de visibilidad, precipitación y nubosidad de las secciones 1 y 3."""
from decimal import Decimal, InvalidOperation

VISIBILITY_BANDS=((0,0,90),(1,1,91),(2,4,92),(5,9,93),(10,19,94),
                  (20,39,95),(40,59,96),(60,69,97),(70,83,98),(84,89,99))

def visibility_fine(coarse):
    """Convierte VV de escala gruesa a fina mediante la Tabla 4377."""
    v=str(coarse or '').strip()
    if len(v)!=2 or not v.isdecimal():return None
    n=int(v)
    return next((str(f) for lo,hi,f in VISIBILITY_BANDS if lo<=n<=hi),None)

def _decimal(value):
    """Interpreta valores numéricos sin redondeos."""
    try:return Decimal(str(value).replace(',','.'))
    except (ValueError,InvalidOperation,TypeError):return None

def rrr(mm, state):
    """Tabla 3590: lluvia 1..989 mm, trazas 990 y décimas 991..999.

    Nunca redondea; la primera décima se cifra solo en precipitaciones <1 mm.
    """
    if state != 'yes':return None
    value=_decimal(mm)
    if value is None or value<0:return None
    if value==0:return '990'
    if value<1:
        tenth=int(value*10)
        return f'{990+tenth:03d}' if tenth else '990'
    if value<990:return f'{int(value):03d}'
    return None

def precip_groups(hour, v, history):
    """history: clave de hora UTC 0,6,12,18 -> {state,mm}; actual desde v."""
    result={'section1':None,'section3':[],'warnings':[],'states':[],'derived':{}}
    if hour not in (0,6,12,18):return result
    state=v.get('precip_state','')
    present={'state':state,'mm':v.get('precip_mm')}
    if hour!=12:
        result['states']=[state] if state else []
        result['derived']['precip_period']='Últimas 6 horas'
        code=rrr(present['mm'],state)
        if code:result['section1']='6'+code+'1'
        elif state=='yes':result['warnings'].append('Precipitación: cantidad no cifrable aún por Tabla 3590; revisar RRR.')
        return result
    # 12 UTC: 12-18,18-00,00-06,06-12. No dato aporta 0 al acumulado.
    entries=[history.get(k,{'state':'unknown'}) for k in (18,0,6)]+[present]
    result['states']=[x.get('state','') for x in entries]
    total=Decimal(0)
    has_rain=False
    for entry in entries:
        if entry.get('state')=='yes':
            has_rain=True
            x=_decimal(entry.get('mm'))
            if x is None or x<0:
                result['warnings'].append('Período con precipitación sin cantidad válida; revisar antes de cifrar.')
            else:total+=x
    result['derived']['precip_24h_mm']=str(total)
    result['derived']['precip_24h_has_rain']=has_rain
    result['derived']['precip_24h_all_no']=all(x.get('state')=='no' for x in entries)
    result['derived']['precip_period']='12 UTC: Sección 1 (24 h) y Sección 3 (06–12 UTC)'
    if has_rain:
        c=rrr(str(total),'yes')
        if c:result['section1']='6'+c+'4'
        else:result['warnings'].append('Acumulado de 24 h no cifrable aún por Tabla 3590.')
    c=rrr(present['mm'],state)
    if c:result['section3'].append('6'+c+'1')
    elif state=='yes':result['warnings'].append('Grupo 6 Sección 3 necesita cifrado RRR válido.')
    return result

CLOUD_GENUS={0:'Cirrus',1:'Cirrocumulus',2:'Cirrostratus',3:'Altocumulus',
             4:'Altostratus',5:'Nimbostratus',6:'Stratocumulus',7:'Stratus',
             8:'Cumulus',9:'Cumulonimbus'}

def cloud_section3(values):
    """Desglose por el observador: primera capa / segunda / tercera condicional."""
    groups,warnings,missing=[],[],[]
    if str(values.get('cloud_total','')) == '0':
        return {'groups':[], 'warnings':[], 'missing':[]}
    rows=[]
    for i in (1,2,3):
        if i>=2 and values.get('layer2_exists')=='no':break
        if i==3 and values.get('layer3_exists')!='yes':break
        genus=str(values.get(f'layer{i}_genus','')).strip()
        octas=str(values.get(f'layer{i}_octas','')).strip()
        base=str(values.get(f'layer{i}_base','')).strip()
        # Las alturas reutilizables de la pantalla 4 se asignan sin volver a preguntar.
        if i==1 and not base:base=str(values.get('cl_base','')).strip()
        if i==3 and not base:base=str(values.get('ch_base','')).strip()
        if not genus and not octas and not values.get(f'layer{i}_base'):continue
        if genus not in '0123456789/' or len(genus)!=1 or not octas.isdecimal() or not base.isdecimal():
            missing.append(f'Capa {i}: género C, octavos Ns y altura hshs');continue
        n,h=int(octas),int(base)
        if not (0<=n<=9 and 0<=h<=99):warnings.append(f'Capa {i}: Ns o altura fuera de rango');continue
        rows.append((i,genus,n,h))
    if rows:
        bases=[x[3] for x in rows]
        if any(b>=a for b,a in zip(bases,bases[1:])):
            warnings.append('Las capas deben tener alturas distintas y estrictamente crecientes.')
            return {'groups':[],'warnings':warnings,'missing':missing}
        for i,g,n,h in rows:
            threshold={1:1,2:3,3:5}[i]
            if n<threshold and g!='9':
                warnings.append(f'Capa {i}: requiere {threshold} octavo(s) como mínimo.');continue
            groups.append(f'8{n}{g}{h:02d}')
    return {'groups':groups,'warnings':warnings,'missing':missing}
