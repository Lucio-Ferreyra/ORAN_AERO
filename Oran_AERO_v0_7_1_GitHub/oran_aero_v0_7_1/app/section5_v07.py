"""Únicamente los cuatro grupos seleccionados por Orán AERO para Sección 5."""
from decimal import Decimal
from .synop_v03 import number, pressure_code

ASH_WW={"04","06","07","08","09"}


def hr_coded(info):
    """Representa la humedad relativa de Sección 5 en dos cifras."""
    if not info:return None
    maximum = info.get("max")
    minimum = info.get("min")
    if not maximum or not minimum:return None
    a,b=number(maximum.get("value")),number(minimum.get("value"))
    if a is None or b is None or not (0<=b<=a<=100):return None
    to_code=lambda d: "00" if d==100 else f"{int(d):02d}"
    return "8"+to_code(a)+to_code(b)


def weekly_code(info):
    """Construye el acumulado semanal según trazas y lluvia registrada."""
    if not info:return None
    total=number(info.get("total"))
    if total is None or total<0:return None
    if total>0:
        tenths=int(total*10)  # nunca redondear
        return f"9{tenths:04d}" if tenths<=9999 else None
    if info.get("has_rain"):
        return "90000"  # trazas sin acumulado mensurable
    if info.get("all_no"):
        return "9///0"  # siete registros válidos sin lluvia
    return None  # datos insuficientes: no afirmar que no llovió


def section5_groups(observation_time, values, qnh_hpa=None, previous_hoa_hr=None, week_precip=None):
    """Selecciona exclusivamente los grupos autorizados de Sección 5."""
    groups=[];missing=[];derived={}
    if qnh_hpa is not None:
        code=pressure_code(qnh_hpa)
        if code:groups.append("1"+code)
    if str(values.get("ww", "")).zfill(2) in ASH_WW:
        state=values.get("ash_present")
        if state=="yes":groups.append("29999")
        elif state=="no":groups.append("20000")
        else:missing.append("Confirmar presencia o ausencia de ceniza volcánica")
    if observation_time.hour==12:
        h=hr_coded(previous_hoa_hr)
        if h:
            groups.append(h)
            derived["hr_previous_day_hoa"]=previous_hoa_hr
            if values.get("hr_extremes_confirmed")!="yes":
                missing.append("Confirmar los extremos de humedad relativa del día civil anterior")
        if observation_time.weekday()==4:
            w=weekly_code(week_precip)
            if w:groups.append(w)
            elif week_precip and not week_precip.get("has_rain") and week_precip.get("available_days",0)<7:
                derived["weekly_precip_status"]="Datos insuficientes para distinguir ausencia total de precipitación"
    return {"groups":groups,"missing":missing,"derived":derived}
