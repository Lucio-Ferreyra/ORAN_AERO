"""Motor de cifrado SYNOP a partir de observaciones y tablas de Orán AERO.

Se conservan los datos originales, los derivados y los motivos de datos faltantes.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from .synop import build_section_0
from .calculations import convert_hpa_to_mmhg, calculate_qff, qnh_from_station_pressure
from .psychrometry_v04 import calculate as psychro

BEAUFORT_KT = (0, 2, 5, 8, 13, 18, 24, 30, 37, 44, 52, 60, 64)
STEPS = ('Termómetro seco y presión', 'Termómetro húmedo y psicrometría',
         'Viento', 'Fenómenos, visibilidad y suelo', 'Nubosidad observada',
         'Bases y desplazamiento', 'Capas de nubes', 'Precipitación',
         'Tiempo pasado', 'Tendencia barométrica', 'Temperaturas máxima y mínima', 'Sección 5')

def number(value):
    """Convierte un valor de entrada a Decimal o devuelve ausencia de dato."""
    if value is None or str(value).strip() == '':
        return None
    try:
        return Decimal(str(value).replace(',', '.'))
    except Exception:
        return None

def rounded_int(value):
    """Obtiene enteros cuando una conversión lo requiere."""
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def wind_knots(values):
    """Convierte la velocidad observada a nudos según su unidad."""
    f = number(values.get('wind_force'))
    if f is None or f < 0:
        return None
    unit = str(values.get('wind_unit', '3'))
    if unit == '3':
        if f != f.to_integral_value() or f > 12:
            return None
        return BEAUFORT_KT[int(f)]
    if unit == '1':
        return rounded_int(f / Decimal('1.852'))
    if unit == '2':
        return rounded_int(f * Decimal('1.9438444924'))
    if unit == '4':
        return rounded_int(f)
    return None

def pressure_code(hpa):
    """Cifra presión en centena, decena, unidad y primera décima."""
    x = number(hpa)
    if x is None or x <= 0:
        return None
    return f'{int(x * 10) % 10000:04d}'

def temp_group(prefix, value):
    """Codifica signo y décimas de una temperatura."""
    x = number(value)
    if x is None:
        return None
    n = int(abs(x) * 10)
    if n > 999:
        return None
    return f'{prefix}{1 if x < 0 else 0}{n:03d}'

def precip_rrr(mm, occurred):
    """Representa la cantidad de precipitación de una observación."""
    if occurred != 'yes':
        return None
    x = number(mm)
    if x is None or x < 0:
        return None
    if x == 0:
        return '990'  # Trazas acordadas
    # Se evita inventar la codificación de cantidades no enteras sin verificar clave 3590.
    if x == x.to_integral_value() and x <= 989:
        return f'{int(x):03d}'
    return None

def cloud_code(v):
    """Valida un código simple de forma de nube."""
    n = str(v or '').strip()
    return n if (n=='/' or (len(n)==1 and n.isdigit() and 0<=int(n)<=9)) else None

def assemble(values, observation_time, iw, block='87', station='016', history_12h=None, history_3h=None, instruments=None, precip_history=None, previous_hoa_hr=None, week_precip=None, station_coordinates=None):
    """Compone los grupos seleccionados y devuelve mensaje, valores derivados y validaciones."""
    v = values or {}
    section0 = build_section_0(observation_time, iw, block, station)
    # Sección 0: exclusivamente AAXX, YYGGiw e IIiii.
    # station_coordinates se conserva como parámetro por compatibilidad de llamadas,
    # pero latitud, longitud y cuadrante NO se incorporan al mensaje SYNOP.
    warnings, derived, missing = [], {}, []
    groups = {}
    instruments=instruments or {}
    def available(k):return instruments.get(k,{}).get('status','en_servicio')=='en_servicio'
    def correction(k):
        item=instruments.get(k,{})
        return Decimal(str(item.get('correction',0))) if item.get('correction_mode','SC')=='valor' else Decimal(0)
    p_raw = number(v.get('pressure_hpa')) if available('pressure') else None
    p = p_raw + correction('pressure') if p_raw is not None else None
    ts_raw = number(v.get('ts')) if available('ts') else None
    th_raw = number(v.get('th')) if available('th') else None
    ts = ts_raw + correction('ts') if ts_raw is not None else None
    th = th_raw + correction('th') if th_raw is not None else None
    if ts is not None:derived['ts_corrected']=float(ts)
    if p is not None:derived['pressure_corrected']=float(p)
    if th is not None:derived['th_corrected']=float(th)
    if not available('pressure'):warnings.append('Barómetro fuera de servicio: presión, QNH, QFF y tendencia bloqueadas.')
    if not available('ts'):warnings.append('Termómetro seco fuera de servicio: TS y cálculos dependientes bloqueados.')
    if not available('th'):warnings.append('Termómetro húmedo fuera de servicio: cálculos psicrométricos bloqueados.')
    if not available('wind'):warnings.append('Anemoveleta fuera de servicio: dirección y fuerza del viento bloqueadas.')
    # Los valores históricos se recuperan del JSON como float o texto.
    # Normalizarlos a Decimal evita mezclar tipos al calcular la tendencia 3 h.
    ts12 = number(history_12h) if history_12h is not None else number(v.get('ts_12h_manual'))
    p3 = number(history_3h) if history_3h is not None else number(v.get('pressure_3h_manual'))
    if p is not None:
        groups['3'] = '3' + pressure_code(p)
        try:
            derived['mmhg'] = convert_hpa_to_mmhg(float(p))['mmhg']
            derived['qnh_hpa'] = qnh_from_station_pressure(float(p))['qnh_hpa']
        except ValueError as ex:
            warnings.append(f'Tabla de presión: {ex}')
    groups['1'] = temp_group('1',ts) if ts is not None else '1////' if not available('ts') else None
    if not available('pressure'):groups['3']='3////'
    if p is None or ts is None:
        if not available('pressure') or not available('ts'):groups['4']='4////'
    if p is not None and ts is not None:
        if ts12 is not None:
            try:
                qff = calculate_qff(float(ts), float(ts12), float(p))
                derived['qff_hpa'] = qff['qff_hpa']
                derived['qff_trace'] = qff
                groups['4'] = '4' + pressure_code(qff['qff_hpa'])
            except ValueError as ex:
                warnings.append(f'QFF no calculable: {ex}')
                groups['4'] = '4////'
        elif v.get('ts_12h_unavailable') == 'yes':
            groups['4'] = '4////'
        else:
            missing.append('Temperatura seca de 12 horas anteriores o indicación de dato no disponible')
    if ts is not None and th is not None:
        choice=str(v.get('psychro_table') or 'I') if th<0 else 'I'
        try:
            result=psychro(float(ts),float(th),choice)
            derived.update(result)
            groups['2']=temp_group('2',result['dew_point_c'])
        except (ValueError,TypeError) as ex:
            warnings.append('Psicrometría: '+str(ex))
            groups['2']='2////'
    else:
        groups['2']='2////'
    n = v.get('cloud_total')
    dd = str(v.get('wind_dd', '')).strip().zfill(2)
    knots = wind_knots(v) if available('wind') else None
    if not available('wind') and str(n).isdigit() and 0<=int(n)<=9:groups['N']=str(n)+'////'
    if knots is not None:
        derived['wind_kt'] = knots
        # iw=0/1 expresa ff en m/s; iw=3/4 en nudos, por Tabla 1855.
        # La velocidad en nudos se conserva siempre para Valores Extremos.
        if iw in ('0','1'):
            raw_mps=number(v.get('wind_force')) if v.get('wind_unit')=='2' else None
            ff=int(raw_mps) if raw_mps is not None else int(Decimal(knots)*Decimal('0.514444'))
        else:
            ff=knots
        derived['wind_ff']=ff
        if knots == 0:
            dd = '00'
        if n is not None and str(n).isdigit() and 0 <= int(n) <= 9 and len(dd) == 2 and dd.isdigit() and 0 <= int(dd) <= 36 and ff <= 99:
            groups['N'] = f'{n}{dd}{ff:02d}'
        elif ff > 99:
            warnings.append('Viento mayor de 99 nudos: requiere codificación especial, no generada automáticamente.')
    # Un dato ausente no puede transformarse en una medición de visibilidad 00.
    raw_vv = v.get('visibility_coarse')
    vv = str(raw_vv).strip() if raw_vv is not None else ''
    vv_valid = len(vv) == 2 and vv.isascii() and vv.isdecimal() and int(vv) <= 89

    # Tabla 1600: cielo despejado = 9; base no discernible = /.
    h = '9' if str(n) == '0' else '/' if str(n) == '9' else str(v.get('plafond') or '').strip()
    h_valid = len(h) == 1 and (h in '0123456789/')

    # Tabla 1860: ww, W1 y W2 los informa siempre el observador.
    # ix=1 cuando hay tiempo significativo; ix=2 cuando no lo hay.
    # No se genera ix a partir de códigos incompletos ni se utiliza ix=3.
    ww, w1, w2 = [('' if v.get(k) is None else str(v.get(k)).strip())
                  for k in ('ww', 'w1', 'w2')]
    ww_valid = len(ww) == 2 and ww.isascii() and ww.isdecimal()
    w1_valid = len(w1) == 1 and w1 in '0123456789'
    w2_valid = len(w2) == 1 and w2 in '0123456789'
    if not ww_valid:
        missing.append('Ingresar tiempo presente ww (dos cifras de 00 a 99)')
    if not w1_valid:
        missing.append('Ingresar tiempo pasado W1 (una cifra de 0 a 9)')
    if not w2_valid:
        missing.append('Ingresar tiempo pasado W2 (una cifra de 0 a 9)')
    ix = None
    if ww_valid and w1_valid and w2_valid:
        significant = int(ww) > 3 or int(w1) > 2 or int(w2) > 2
        ix = '1' if significant else '2'
        if significant:
            groups['7'] = '7' + ww + w1 + w2
    # Sección 1 registra coberturas por nivel, que pueden superponerse.
    # Ejemplo aprobado: N=8, CL=4 y CH=8; NO sumar para invalidar.
    cloud_degrees = [number(v.get(k)) for k in ('cl_degree','cm_degree','ch_degree')]
    if str(n).isdigit() and int(n)<=8:
        for degree in cloud_degrees:
            if degree is not None and (degree < 0 or degree > Decimal(str(n))):
                warnings.append('La nubosidad de un nivel no puede superar la cobertura total N.')
                missing.append('Revisar la cantidad de nubes ingresada')

    if str(n) in ('0', '9', '/'):
        derived['cloud_groups_omitted'] = True
    elif n is not None:
        cl = cloud_code(v.get('cl_form'))
        cm = cloud_code(v.get('cm_form'))
        ch = cloud_code(v.get('ch_form'))
        l, m = number(v.get('cl_degree')), number(v.get('cm_degree'))
        if l == 8: cm = ch = '/'
        elif m == 8: ch = '/'
        nh = int(l) if l is not None and l > 0 else int(m) if m is not None and m > 0 else 0
        if all(x is not None for x in (cl, cm, ch)):
            groups['8'] = f'8{nh}{cl}{cm}{ch}'
        else:
            missing.append('Completar las formas CL, CM y CH de la nubosidad observada')
    if not available('pressure'):groups['5']='5////'
    if p is not None:
        if p3 is None and v.get('pressure_3h_unavailable') == 'yes':
            groups['5'] = '5////'
        elif p3 is not None:
            diff = p - p3
            derived['pressure_tendency_hpa'] = float(diff)
            a = str(v.get('tendency_a','')).strip()
            if len(a) == 1 and a.isdigit() and 0 <= int(a) <= 8:
                ppp = int(abs(diff) * 10) % 1000
                groups['5'] = f'5{a}{ppp:03d}'
    # Precipitación únicamente 00, 06, 12 y 18 UTC. Cada ventana es 6 h.
    from .synop_rules_v05 import precip_groups, cloud_section3, visibility_fine
    rain_result = precip_groups(observation_time.hour, v, precip_history or {})
    derived.update(rain_result['derived'])
    warnings.extend(rain_result['warnings'])
    if rain_result['section1']: groups['6'] = rain_result['section1']
    section3 = list(rain_result['section3'])
    cloud_result = cloud_section3(v)
    section3.extend(cloud_result['groups'])
    warnings.extend(cloud_result['warnings'])
    missing.extend(cloud_result['missing'])
    section3_hours = observation_time.hour == 12
    if section3_hours:
        for prefix, field,kind in [('1', 'temp_max','temp_max'), ('2', 'temp_min','temp_min')]:
            original = number(v.get(field)) if available(kind) else None
            val=original + correction(kind) if original is not None else None
            if val is not None:
                derived[field+'_corrected']=float(val)
                code=temp_group(prefix,val)
                if code: section3.append(code)
    if groups.get('8'):
        directions = []
        for k in ('cl','cm','ch'):
            value=str(v.get('direction_' + k, '')).strip()
            amount=number(v.get(k+'_degree'))
            directions.append('/' if str(v.get(k+'_form'))=='/' else '0' if amount == 0 else value)
        if all(len(d)==1 and (d in '012345678/' ) for d in directions):
            section3.append('56'+''.join(directions))
        else: missing.append('Direcciones de desplazamiento DL, DM y DH para grupo 56')
    cl_code = str(v.get('cl_form','')).strip()
    cm_code = str(v.get('cm_form','')).strip()
    if str(n) not in ('0','9','/') and (cl_code in ('2','3','9') or cm_code == '4'):
        c,da,ec = [str(v.get(k,'')).strip() for k in ('conv_c','conv_da','conv_ec')]
        if all(len(z)==1 and z.isdigit() for z in (c,da,ec)):
            section3.append('57'+c+da+ec)
        else:missing.append('Datos C, Da, ec para grupo 57')
    vv_fine = visibility_fine(v.get('visibility_coarse'))
    if vv_fine is not None: derived['visibility_fine']=vv_fine
    elif vv: warnings.append('VV debe ser un código de escala gruesa de 00 a 89.')
    else: missing.append('Ingresar visibilidad VV (escala gruesa de dos cifras)')
    if 'N' not in groups: missing.append('Grupo Nddff')
    if '1' not in groups: missing.append('Temperatura seca')
    if '3' not in groups: missing.append('Presión de estación')
    if '4' not in groups: missing.append('QFF o ausencia de datos')
    if '5' not in groups: missing.append('Tendencia barométrica o ausencia de datos')
    # ir según presencia real de grupos 6 y estados observados, sin suposiciones.
    has1=bool(groups.get('6'))
    has3=any(g.startswith('6') and len(g)==5 for g in section3)
    if has1 and has3: ir='0'
    elif has1: ir='1'
    elif has3: ir='2'
    elif observation_time.hour not in (0,6,12,18): ir='3'
    else:
        states=rain_result['states']
        ir='4' if states and all(x=='unknown' for x in states) else '3' if states and all(x in ('unknown','no') for x in states) else None
    if ir is not None and ix is not None and h_valid and vv_valid:
        groups['irixhVV']=ir+ix+h+vv
        derived['ir']=ir
    if 'irixhVV' not in groups:
        if not h_valid: missing.append('Ingresar h (Tabla 1600: 0–9 o / para altura desconocida)')
        if ix is None: missing.append('Completar tiempo presente y pasado para determinar ix')
        missing.append('Completar el grupo obligatorio irixhVV')
    # Orden fijo: irixhVV debe preceder inmediatamente a Nddff.
    ordered = [groups[k] for k in ('irixhVV','N','1','2','3','4','5','6','7','8') if groups.get(k)]
    # Solo los grupos elegidos para Sección 3, en el orden correcto.
    def sec3_rank(g):
        if g.startswith('56'):return 2
        if g.startswith('57'):return 3
        return {'1':0,'2':1,'6':4,'8':5}.get(g[0],99)
    section3.sort(key=sec3_rank)
    from .section5_v07 import section5_groups
    part5=section5_groups(observation_time,v,derived.get('qnh_hpa'),previous_hoa_hr,week_precip)
    derived.update(part5['derived'])
    missing.extend(part5['missing'])
    # No incluir grupos no seleccionados: únicamente las secciones 0, 1, 3 y 5.
    message = section0 + (' ' + ' '.join(ordered) if ordered else '')
    if section3:message+=' 333 '+' '.join(section3)
    if part5['groups']:message+=' 555 '+' '.join(part5['groups'])
    if p is not None and 'qnh_hpa' not in derived:
        missing.append('QNH no disponible en la tabla de la estación')
    if groups.get('8') and not any(g.startswith('8') and len(g)==5 for g in section3):
        missing.append('Completar el desglose de capas del grupo 8 de la Sección 3')
    required=list(dict.fromkeys(missing))
    return {'message': message, 'groups': groups, 'derived': derived, 'warnings': warnings,
            'missing': required, 'section0': section0, 'section3': section3,
            'section5':part5['groups'], 'can_finalize': not required}
