"""Orán AERO: interfaz, permisos, persistencia versionada y endpoints.

El cifrado está encapsulado en synop_v03. No se reutilizan credenciales ni
borradores de otro usuario. Los informes anteriores son inmutables por versión.
"""
from __future__ import annotations
import copy
import io
import re
from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, Body, File, UploadFile, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from .config import APP_SECRET_KEY, STATIC_DIR, TEMPLATES_DIR, DATA_DIR
from .db import get_db
from .models import User, Station, Observation, Report, AuditLog, Instrument, DailyExtremes
from .security import verify_password, hash_password
from .schema_migrations import initialize_schema
from .synop_v03 import assemble, STEPS
from .table_data import get_table_names, get_table
from .services_v07 import (refresh_daily_extremes, previous_day_hoa_hr,
                           week_precipitation, latest_reports, compute_daily_extremes)
from .observation_clock import next_synop_hour, utc_iso

initialize_schema()
app=FastAPI(title="Sistema Meteorológico Orán AERO", version="0.7.7")
app.add_middleware(SessionMiddleware, secret_key=APP_SECRET_KEY, same_site="lax", https_only=False)
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates=Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.exception_handler(HTTPException)
async def redirect_unauthenticated_browser(request: Request, error: HTTPException):
    """Use a login page for browser requests; keep JSON errors for API clients.

    A 303 avoids retrying a form POST after the session has expired.
    Authentication checks still run on every protected endpoint.
    """
    if error.status_code == 401 and not request.url.path.startswith('/api/'):
        return RedirectResponse('/login', status_code=303,
                                headers={'Cache-Control': 'no-store'})
    return await http_exception_handler(request, error)


# --- ROLES Y CONFIGURACIÓN DE ESTACIÓN ---
CHIEF_ROLES={'jefe_estacion','jefe','jefe de estación'}
INSTRUMENT_TYPES={
 'ts':'Termómetro seco','th':'Termómetro húmedo','pressure':'Barómetro',
 'temp_max':'Termómetro de máxima','temp_min':'Termómetro de mínima',
 'wind':'Viento', 'viento':'Viento', 'other':'Otro'}



# --- AUTENTICACIÓN Y PERMISOS ---
def current_user(request:Request,db:Session):
    """Busca la cuenta activa asociada a la sesión del navegador."""
    user_id=request.session.get('user_id')
    if not user_id:return None
    u=db.get(User,user_id)
    if u and u.active:return u
    request.session.clear()
    return None

def require_user(request:Request,db:Session):
    """Impide el acceso a rutas que requieren una sesión iniciada."""
    user=current_user(request,db)
    if not user:raise HTTPException(401,'Iniciá sesión para continuar')
    return user

def is_chief(user):
    """Comprueba si la cuenta tiene rol de Jefe de Estación."""
    return bool(user and user.role.strip().lower() in CHIEF_ROLES)

def require_chief(request,db):
    """Restringe las modificaciones administrativas al Jefe."""
    u=require_user(request,db)
    if not is_chief(u):raise HTTPException(403,'Solo el Jefe de Estación puede realizar esta modificación')
    return u

def ensure_station(db):
    """Obtiene la estación configurada o crea sus datos iniciales."""
    station=db.query(Station).first()
    if not station:
        station=Station(name='Orán AERO',block_number='87',station_number='016',
                        latitude="23°09' S",longitude="64°19' O",runway_elevation_m=357,
                        wind_method='estimado',wind_iw='3')
        db.add(station);db.commit();db.refresh(station)
    return station

def log_change(db, actor, action, kind, entity_id, before=None, after=None):
    """Registra cambios administrativos sin perder valores anteriores."""
    db.add(AuditLog(user_id=actor.id if actor else None,action=action,entity_type=kind,
                    entity_id=str(entity_id),detail={'anterior':before,'nuevo':after}))

def info(request,db,**extra):
    """Prepara los datos compartidos por las plantillas protegidas."""
    return {'request':request,'user':require_user(request,db), 'station':ensure_station(db),
            'is_chief':is_chief(current_user(request,db)),**extra}


# --- INVENTARIO DE INSTRUMENTOS ---
def active_instruments(db):
    """Recupera los instrumentos y crea los básicos si no existen."""
    defaults=[('Termómetro seco','ts'),('Termómetro húmedo','th'),
              ('Barómetro digital','pressure'),('Termómetro máxima','temp_max'),
              ('Termómetro mínima','temp_min'),('Viento estimado','wind')]
    items=db.query(Instrument).order_by(Instrument.id).all()
    for title,kind in defaults:
        if not any(i.instrument_type==kind for i in items):
            new=Instrument(name=title,brand='S/D',instrument_type=kind,
                           serial_number='',status='en_servicio',physical_state='Bueno',
                           correction_mode='SC',correction_value=0,correction_notes='S/C')
            db.add(new);items.append(new)
    if any(i.id is None for i in items):db.commit()
    return db.query(Instrument).order_by(Instrument.id).all()

def instrument_state(db):
    """Prepara el estado y la corrección de los instrumentos para el SYNOP."""
    records=active_instruments(db)
    lookup={}
    for item in records:
        key='wind' if item.instrument_type=='viento' else item.instrument_type
        if key in ('ts','th','pressure','wind','temp_max','temp_min'):
            # Preferir un instrumento efectivamente en servicio.
            if key not in lookup or (lookup[key].status!='en_servicio' and item.status=='en_servicio'):
                lookup[key]=item
    out={}
    for key in ('ts','th','pressure','wind','temp_max','temp_min'):
        obj=lookup.get(key)
        out[key]={'id':obj.id,'name':obj.name,'status':obj.status,
                  'correction_mode':obj.correction_mode,'correction':obj.correction_value or 0,
                  'serial_number':obj.serial_number} if obj else {'status':'fuera_servicio','correction_mode':'SC','correction':0}
    return out


# --- BORRADORES E HISTORIAL DE OBSERVACIÓN ---
def _latest_draft(db, user_id=None):
    """Recupera el último borrador pendiente del usuario indicado."""
    query=db.query(Observation).filter(Observation.status=='borrador_autoguardado')
    if user_id is not None:query=query.filter(Observation.observer_id==user_id)
    return query.order_by(Observation.updated_at.desc(),Observation.id.desc()).first()

def restored_screen_index(values):
    """Traduce posiciones de pantallas de borradores de versiones anteriores."""
    try:idx=int((values or {}).get('_step',0))
    except (ValueError,TypeError):return 0
    if not 0<=idx<=11:return 0
    version=(values or {}).get('_ui_flow_version')
    if version=='3':return idx
    if version=='2':
        # Flujo v0.5: nubes(4) -> tres pantallas, precipitación(5) -> 7.
        return {4:4,5:7,6:8,7:9,8:10}.get(idx,idx)
    return {3:4,4:7,5:3,6:8,7:9,8:10}.get(idx,idx)

def _previous_value(db,obs,offset,key):
    """Consulta un dato histórico de la misma estación y hora UTC."""
    target=obs.observation_time_utc.replace(tzinfo=None)-timedelta(hours=offset)
    matches=latest_reports(db,obs.station_id,target,target+timedelta(seconds=1))
    if matches:
        report,original=matches[0]
        data=report.derived_snapshot if key.endswith('_corrected') else report.values_snapshot
        return (data or {}).get(key)
    return None

def _workspace_data(db,obs,station):
    """Calcula datos del formulario, informe provisorio y ayudas de carga."""
    from .synop_rules_v05 import precip_groups
    values=dict(obs.values or {})
    ins=instrument_state(db)
    old12=_previous_value(db,obs,12,'ts_corrected')
    old3=_previous_value(db,obs,3,'pressure_corrected')
    precip_history={}
    if obs.observation_time_utc.hour==12:
        for back,clock in ((18,18),(12,0),(6,6)):
            target=obs.observation_time_utc.replace(tzinfo=None)-timedelta(hours=back)
            matches=latest_reports(db,obs.station_id,target,target+timedelta(seconds=1))
            if matches:
                report,_=matches[0]
                data=report.values_snapshot or {}
                precip_history[clock]={'state':data.get('precip_state',''),
                                        'mm':data.get('precip_mm','')}
    h=None
    if obs.observation_time_utc.hour==12:
        h=previous_day_hoa_hr(db,obs.station_id,obs.observation_time_utc)
    rain=precip_groups(obs.observation_time_utc.hour,values,precip_history)
    week=None
    if obs.observation_time_utc.hour==12 and obs.observation_time_utc.weekday()==4:
        source={**values,**rain['derived']}
        week=week_precipitation(db,obs.station_id,obs.observation_time_utc,source)
    calculated=assemble(values,obs.observation_time_utc,station.wind_iw or '3',
        station.block_number,station.station_number,old12,old3,
        instruments=ins,precip_history=precip_history,previous_hoa_hr=h,
        week_precip=week, station_coordinates=(station.latitude,station.longitude))
    calculated.update({'precip_history':precip_history,'instruments':ins,
        'historical_ts12':old12,'historical_p3_found':old3 is not None,
        'status':obs.status,'values':values,'step':restored_screen_index(values),
        'observation_id':obs.id,'time_utc':utc_iso(obs.observation_time_utc),
        'source_report_id':obs.source_report_id})
    proposed_hour=next_synop_hour(db,obs.station_id)
    calculated['stale_draft']=(obs.source_report_id is None and
                               obs.observation_time_utc != proposed_hour)
    calculated['proposed_next_time_utc']=utc_iso(proposed_hour)
    return calculated


# --- ESTADO Y ACCESO DE LA APLICACIÓN ---
@app.get('/health')
def health():
    """Informa el estado básico de la aplicación."""
    from .db import engine
    return {'status':'ok','version':app.version,'database':engine.dialect.name}

@app.get('/login',response_class=HTMLResponse)
def login_page(request:Request):
    """Presenta el formulario de acceso."""
    return templates.TemplateResponse(request,'login.html',{'request':request,'error':None})

@app.post('/login',response_class=HTMLResponse)
def login(request:Request,username:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    """Verifica credenciales y abre sesión."""
    user=db.query(User).filter_by(username=username.strip()).first()
    if not user or not user.active or not verify_password(password,user.password_hash):
        return templates.TemplateResponse(request,'login.html',{'request':request,'error':'Usuario o contraseña incorrectos.'},status_code=401)
    request.session.clear();request.session['user_id']=user.id
    return RedirectResponse('/synop',status_code=303)

@app.post('/logout')
def logout(request:Request):
    """Cierra la sesión del navegador."""
    request.session.clear();return RedirectResponse('/login',status_code=303)

@app.get('/')
def home(request: Request, db: Session = Depends(get_db)):
    """Dirige al usuario al SYNOP o a la pantalla de acceso."""
    destination = '/synop' if current_user(request, db) else '/login'
    return RedirectResponse(destination, status_code=303,
                            headers={'Cache-Control': 'no-store'})

@app.get('/synop',response_class=HTMLResponse)
def synop_workspace(request:Request,db:Session=Depends(get_db)):
    """Abre el último borrador o inicia el siguiente horario UTC."""
    user=require_user(request,db)
    station=ensure_station(db)
    obs=_latest_draft(db,user.id)
    if not obs:
        chosen=next_synop_hour(db,station.id)
        obs=Observation(station_id=station.id,observer_id=user.id,
             observation_time_utc=chosen,status='borrador_autoguardado',
             values={'_step':0,'_ui_flow_version':'3'})
        db.add(obs);db.commit();db.refresh(obs)
    return templates.TemplateResponse(request,'workspace_v03.html',
           info(request,db,state=_workspace_data(db,obs,station),steps=STEPS))

@app.get('/api/synop/draft')
def get_synop_draft(request:Request,db:Session=Depends(get_db)):
    """Entrega al cliente los datos del borrador del usuario."""
    u=require_user(request,db)
    obs=_latest_draft(db,u.id)
    if not obs:raise HTTPException(404,'No hay borrador de este usuario')
    return _workspace_data(db,obs,ensure_station(db))


# --- CAMPOS ADMITIDOS PARA CARGA SYNOP ---
ALLOWED_FIELDS={
 'ts','th','pressure_hpa','ts_12h_manual','ts_12h_unavailable',
 'pressure_3h_manual','pressure_3h_unavailable','wind_dd','wind_force','wind_unit',
 'ww','w1','w2','cloud_total','cl_form','cm_form','ch_form',
 'cl_degree','cm_degree','ch_degree','plafond','cl_base','cm_base','ch_base',
 'precip_state','precip_mm','visibility_coarse','soil_state','tendency_a','psychro_table',
 '_step','_ui_flow_version','temp_max','temp_min','layer2_exists','layer3_exists',
 'layer1_genus','layer1_octas','layer1_base','layer2_genus','layer2_octas','layer2_base',
 'layer3_genus','layer3_octas','layer3_base','direction_cl','direction_cm','direction_ch',
 'conv_c','conv_da','conv_ec','ash_present','hr_extremes_confirmed'}
DIGIT_FIELDS={'wind_dd','ww','w1','w2','cloud_total','cl_form','cm_form','ch_form',
              'cl_degree','cm_degree','ch_degree','plafond','cl_base','cm_base','ch_base',
              'visibility_coarse','soil_state','tendency_a','layer1_genus','layer1_octas',
              'layer1_base','layer2_genus','layer2_octas','layer2_base',
              'layer3_genus','layer3_octas','layer3_base','direction_cl','direction_cm',
              'direction_ch','conv_c','conv_da','conv_ec'}
SLASH_FIELDS={'plafond','cl_form','cm_form','ch_form','cl_degree','cm_degree','ch_degree',
              'cl_base','cm_base','ch_base','direction_cl','direction_cm','direction_ch'}
DECIMAL_FIELDS={'ts','th','pressure_hpa','ts_12h_manual','pressure_3h_manual',
                'precip_mm','temp_max','temp_min'}


def clean_values(changed,observation_hour,ins):
    """Valida y normaliza las entradas permitidas del formulario."""
    if not isinstance(changed,dict):raise HTTPException(422,'Los datos deben ser un objeto')
    clean={k:str(value)[:80] if value is not None else '' for k,value in changed.items() if k in ALLOWED_FIELDS}
    for kind,fields in {'ts':['ts'],'th':['th'],'pressure':['pressure_hpa'],
                        'wind':['wind_force','wind_dd','wind_unit'],
                        'temp_max':['temp_max'],'temp_min':['temp_min']}.items():
        if ins.get(kind,{}).get('status')=='fuera_servicio':
            for field in fields:clean[field]=''
    for name,value in clean.items():
        if not value:continue
        if name in DIGIT_FIELDS:
            pattern=r'(?:\d+|/)' if name in SLASH_FIELDS else r'\d+'
            if not re.fullmatch(pattern,value):raise HTTPException(422,f'{name}: código inválido')
        elif name in DECIMAL_FIELDS and not re.fullmatch(r'-?\d+(?:[.,]\d+)?',value):
            raise HTTPException(422,f'{name}: número inválido')
    if clean.get('ts_12h_manual'):clean['ts_12h_unavailable']=''
    if clean.get('precip_state')!='yes':clean['precip_mm']=''
    if observation_hour not in (0,6,12,18):clean['precip_state']='';clean['precip_mm']=''
    if clean.get('layer2_exists')!='yes':
        clean['layer3_exists']='no'
        for k in ('layer2_genus','layer2_octas','layer2_base'):clean[k]=''
    if clean.get('layer3_exists')!='yes':
        for k in ('layer3_genus','layer3_octas','layer3_base'):clean[k]=''
    for cloud in ('ch','cm','cl'):
        val=clean.get(cloud+'_form')
        if val in ('0','/'):
            for ending in ('degree','base'):clean[cloud+'_'+ending]=val
            clean['direction_'+cloud]=val
    if clean.get('cloud_total')=='0':
        for k in ('cl_form','cm_form','ch_form','cl_degree','cm_degree','ch_degree',
                  'cl_base','cm_base','ch_base','direction_cl','direction_cm','direction_ch'):
            clean[k]='0'
        clean['plafond']='9'  # Tabla 1600: sin nubes
    if clean.get('cloud_total')=='9': clean['plafond']='/'  # Cielo invisible
    if clean.get('pressure_3h_unavailable')=='yes':clean['pressure_3h_manual']='';clean['tendency_a']=''
    if clean.get('wind_force')=='0':clean['wind_dd']='00'
    clean['_ui_flow_version']='3'
    return clean


# --- GUARDADO Y VERSIONADO DEL SYNOP ---
@app.post('/api/synop/autoguardado')
def autosave_synop(request:Request,payload:dict=Body(...),db:Session=Depends(get_db)):
    """Guarda automáticamente los datos en la observación en curso."""
    u=require_user(request,db);obs=_latest_draft(db,u.id)
    if not obs or payload.get('observation_id')!=obs.id:raise HTTPException(409,'Borrador reemplazado, recargá la página')
    clean=clean_values(payload.get('values'),obs.observation_time_utc.hour,instrument_state(db))
    obs.values=clean;obs.updated_at=datetime.now(timezone.utc)
    db.commit()
    return _workspace_data(db,obs,ensure_station(db))

@app.post('/api/synop/nueva')
def restart_synop(request:Request,payload:dict=Body(...),db:Session=Depends(get_db)):
    """Descarta el borrador confirmado y crea la siguiente observación."""
    u=require_user(request,db)
    if payload.get('discard_confirmed') is not True:
        raise HTTPException(400,'Confirmar descarte del borrador')
    old=_latest_draft(db,u.id)
    if old:
        log_change(db,u,'descartar_borrador','observation',old.id,old.values,None)
        old.status='descartado'
    station=ensure_station(db)
    # La hora no es editable: evita crear dos informes en el mismo horario por API.
    if 'observation_time_utc' in payload:
        raise HTTPException(422,'La fecha y hora de un SYNOP nuevo se asignan automáticamente en UTC')
    chosen=next_synop_hour(db,station.id)
    obs=Observation(station_id=station.id,observer_id=u.id,observation_time_utc=chosen,
                    status='borrador_autoguardado',values={'_step':0,'_ui_flow_version':'3'})
    db.add(obs);db.commit()
    return {'ok':True,'observation_id':obs.id}

@app.post('/api/synop/finalizar')
def finalize_synop(request:Request,payload:dict=Body(...),db:Session=Depends(get_db)):
    """Guarda un informe confirmado y conserva las versiones anteriores."""
    u=require_user(request,db);draft=_latest_draft(db,u.id)
    if not draft or payload.get('observation_id')!=draft.id:
        raise HTTPException(409,'El borrador cambió o ya fue finalizado')
    station=ensure_station(db)
    state=_workspace_data(db,draft,station)
    # Guardar solo informes con los datos necesarios; no se inventan grupos.
    if state['missing']:
        raise HTTPException(422,{'message':'Faltan datos para generar el informe', 'missing':state['missing']})
    if payload.get('confirmed') is not True:
        raise HTTPException(400,'Confirmación explícita requerida')
    initial=db.get(Report,draft.source_report_id) if draft.source_report_id else None
    if not initial:
        # La misma observación debe corregirse por versionado, nunca duplicarse.
        existing=(db.query(Report.id)
            .join(Observation, Report.observation_id == Observation.id)
            .filter(Observation.station_id == draft.station_id,
                    Observation.source_report_id.is_(None),
                    Observation.observation_time_utc == draft.observation_time_utc,
                    Report.status == 'finalizado', Report.report_type == 'SYNOP')
            .first())
        if existing:
            raise HTTPException(409,
                'Ya existe un SYNOP para esta hora UTC. Corregí el informe guardado o iniciá la siguiente observación.')
    if initial:
        root=initial.root_report_id or initial.id
        previous=db.query(Report).filter((Report.id==root)|(Report.root_report_id==root)).order_by(Report.version_number.desc()).first()
        version=(previous.version_number if previous else 1)+1
    else:root=None;version=1
    from hashlib import sha256
    tables_digest=sha256((DATA_DIR/'Tablas_Oran_Aero.xlsx').read_bytes()).hexdigest()
    report=Report(observation_id=draft.id,report_type='SYNOP',status='finalizado',
        message=state['message'],rule_version='0.7.0',table_version='sha256:'+tables_digest,
        version_number=version,root_report_id=root,
        values_snapshot=copy.deepcopy(state['values']),
        derived_snapshot=copy.deepcopy(state['derived']),
        instrument_snapshot=copy.deepcopy(state['instruments']),
        observations_snapshot={'warnings':state['warnings'],'groups':state['groups'],
                               'section3':state['section3'],'section5':state['section5'],
                               'station_iiiii':station.block_number+station.station_number,
                               'wind_iw':station.wind_iw},created_by=u.id)
    draft.status='finalizado';db.add(report);db.flush()
    if root is None:report.root_report_id=report.id
    log_change(db,u,'corregir_informe' if initial else 'guardar_informe','report',report.id,
               {'version':initial.version_number,'message':initial.message} if initial else None,
               {'version':version,'message':report.message})
    refresh_daily_extremes(db,draft.station_id,draft.observation_time_utc.date(),u.id)
    db.commit()
    return {'ok':True,'report_id':report.id,'version':version,'redirect':f'/reportes/{report.id}'}


# --- HISTORIAL Y CORRECCIONES DE INFORMES ---
@app.get('/historial',response_class=HTMLResponse)
def history_page(request:Request,db:Session=Depends(get_db)):
    """Presenta el historial de informes de la estación."""
    require_user(request,db)
    reports=db.query(Report).order_by(Report.created_at.desc(),Report.id.desc()).limit(500).all()
    return templates.TemplateResponse(request,'history.html',info(request,db,reports=reports))

@app.get('/reportes/{report_id}',response_class=HTMLResponse)
def report_review(report_id:int,request:Request,db:Session=Depends(get_db)):
    """Muestra un informe y sus versiones conservadas."""
    require_user(request,db)
    report=db.get(Report,report_id)
    if not report:raise HTTPException(404,'Informe inexistente')
    root=report.root_report_id or report.id
    versions=db.query(Report).filter((Report.id==root)|(Report.root_report_id==root)).order_by(Report.version_number).all()
    return templates.TemplateResponse(request,'report_review.html',info(request,db,report=report,
        versions=versions,values=report.values_snapshot or {},
        observation=report.observation,warnings=(report.observations_snapshot or {}).get('warnings',[])))

@app.post('/reportes/{report_id}/corregir')
def correct_report(report_id:int,request:Request,db:Session=Depends(get_db)):
    """Abre una corrección a partir de una versión confirmada."""
    u=require_user(request,db)
    original=db.get(Report,report_id)
    if not original:raise HTTPException(404,'Informe inexistente')
    latest=db.query(Report).filter((Report.id==(original.root_report_id or original.id))|
             (Report.root_report_id==(original.root_report_id or original.id))).order_by(Report.id.desc()).first()
    if latest and latest.id!=original.id:raise HTTPException(409,'Abrí la versión más reciente antes de corregir')
    earlier=_latest_draft(db,u.id)
    if earlier:earlier.status='descartado';log_change(db,u,'descartar_borrador','observation',earlier.id,earlier.values,None)
    obs=Observation(station_id=original.observation.station_id,observer_id=u.id,
        observation_time_utc=original.observation.observation_time_utc,
        status='borrador_autoguardado',source_report_id=original.id,
        values={**copy.deepcopy(original.values_snapshot or {}),'_step':0,'_ui_flow_version':'3'})
    db.add(obs);db.commit()
    return RedirectResponse('/synop',status_code=303)

@app.get('/extremos',response_class=HTMLResponse)
def extremes_page(request:Request,day:str|None=None,db:Session=Depends(get_db)):
    """Muestra extremos diarios seleccionados por fecha UTC."""
    require_user(request,db)
    try:target=date.fromisoformat(day) if day else datetime.now(timezone.utc).date()-timedelta(days=1)
    except ValueError:raise HTTPException(422,'Fecha UTC inválida')
    station=ensure_station(db)
    existing=db.query(DailyExtremes).filter_by(station_id=station.id,date_utc=target.isoformat()).first()
    # La vista siempre deriva el cálculo de las versiones definitivas actuales.
    result=compute_daily_extremes(db,station.id,target)
    return templates.TemplateResponse(request,'extremes.html',info(request,db,day=target,extremes=result,stored=bool(existing)))


# --- ESTACIÓN E INSTRUMENTOS ---
@app.get('/estacion',response_class=HTMLResponse)
def station_page(request:Request,db:Session=Depends(get_db)):
    """Consulta datos de estación e instrumental."""
    return templates.TemplateResponse(request,'station.html',info(request,db,instruments=active_instruments(db),types=INSTRUMENT_TYPES))

@app.get('/instrumentos')
def instruments_page(request: Request, db: Session = Depends(get_db)):
    """Abre el acceso de instrumentos dentro del menú de estación."""
    require_user(request, db)
    return RedirectResponse('/estacion#instrumentos', status_code=303)

@app.post('/estacion')
def update_station(request:Request, name:str=Form(...),block_number:str=Form(...),
    station_number:str=Form(...),identifier:str=Form(''),latitude:str=Form(...),longitude:str=Form(...),
    runway_elevation_m:float=Form(...),wind_method:str=Form(...),wind_iw:str=Form(...),
    db:Session=Depends(get_db)):
    """Actualiza la configuración de estación con control de permisos."""
    u=require_chief(request,db)
    if not re.fullmatch(r'\d{2}',block_number) or not re.fullmatch(r'\d{3}',station_number):
        raise HTTPException(422,'Bloque II de 2 dígitos y número iii de 3 dígitos')
    if identifier and identifier != block_number+station_number:
        raise HTTPException(422,'El identificador debe coincidir con Bloque II + Número iii')
    if not name.strip() or len(name)>160 or not (0<=runway_elevation_m<=10000):
        raise HTTPException(422,'Datos de estación inválidos')
    if wind_method not in ('estimado','anemometro') or wind_iw not in ({'0','3'} if wind_method=='estimado' else {'1','4'}):
        raise HTTPException(422,'Método del viento y código iw incompatibles')
    if not re.fullmatch(r"\d{1,2}°\s*\d{1,2}'\s*[NS]",latitude.strip(),re.I) or not re.fullmatch(r"\d{1,3}°\s*\d{1,2}'\s*[EOOW]",longitude.strip(),re.I):
        raise HTTPException(422,'Coordenadas esperadas como 23°09\' S y 64°19\' O')
    station=ensure_station(db)
    fields=('name','block_number','station_number','latitude','longitude','runway_elevation_m','wind_method','wind_iw')
    before={k:getattr(station,k) for k in fields}
    values=dict(zip(fields,(name.strip(),block_number,station_number,latitude.strip(),longitude.strip(),runway_elevation_m,wind_method,wind_iw)))
    for field,value in values.items():setattr(station,field,value)
    log_change(db,u,'actualizar_estacion','station',station.id,before,values)
    db.commit();return RedirectResponse('/estacion?guardado=1',status_code=303)

@app.post('/instrumentos')
def save_instrument(request:Request,instrument_id:int=Form(0),name:str=Form(...),
    brand:str=Form('S/D'),instrument_type:str=Form(...),serial_number:str=Form(''),
    correction_mode:str=Form('SC'),correction_value:str=Form('0'),
    status:str=Form('en_servicio'),physical_state:str=Form('Bueno'),
    patrimony_number:str=Form(''),db:Session=Depends(get_db)):
    """Crea o modifica el inventario instrumental."""
    u=require_chief(request,db)
    if instrument_type not in INSTRUMENT_TYPES or status not in ('en_servicio','fuera_servicio') or physical_state not in ('Bueno','Malo') or correction_mode not in ('SC','valor'):
        raise HTTPException(422,'Datos de instrumental inválidos')
    if not name.strip() or len(name)>160 or not serial_number.strip():
        raise HTTPException(422,'Nombre y número de instrumental son obligatorios')
    try:correction=Decimal(correction_value.replace(',','.')) if correction_mode=='valor' else Decimal(0)
    except Exception:raise HTTPException(422,'Corrección instrumental inválida')
    if not correction.is_finite():raise HTTPException(422,'Corrección instrumental inválida')
    record=db.get(Instrument,instrument_id) if instrument_id else None
    if instrument_id and not record:raise HTTPException(404,'Instrumento inexistente')
    before={k:getattr(record,k) for k in ('name','brand','instrument_type','serial_number','status','physical_state','patrimony_number','correction_value','correction_mode')} if record else None
    if not record:record=Instrument()
    changed={'name':name.strip(),'brand':brand.strip() or 'S/D','instrument_type':instrument_type,
             'serial_number':serial_number.strip(),'status':status,'physical_state':physical_state,
             'patrimony_number':patrimony_number.strip() or None,
             'correction_mode':correction_mode,'correction_value':float(correction),
             'correction_notes':'S/C' if correction_mode=='SC' else str(correction)}
    for field,value in changed.items():setattr(record,field,value)
    db.add(record);db.flush();log_change(db,u,'modificar_instrumento' if instrument_id else 'crear_instrumento','instrument',record.id,before,changed)
    db.commit();return RedirectResponse('/estacion#instrumentos',status_code=303)

@app.post('/instrumentos/{instrument_id}/eliminar')
def deactivate_instrument(instrument_id:int,request:Request,db:Session=Depends(get_db)):
    """Cambia el estado del instrumento sin borrar su historial."""
    u=require_chief(request,db);record=db.get(Instrument,instrument_id)
    if not record:raise HTTPException(404,'Instrumento inexistente')
    before=record.status;record.status='fuera_servicio'
    log_change(db,u,'retirar_instrumento','instrument',record.id,before,record.status)
    db.commit();return RedirectResponse('/estacion#instrumentos',status_code=303)


# --- PERSONAL Y CONTRASEÑAS ---
@app.get('/personal',response_class=HTMLResponse)
def personnel_page(request:Request,db:Session=Depends(get_db)):
    """Presenta las cuentas del personal y sus estados."""
    users=db.query(User).order_by(User.full_name).all()
    return templates.TemplateResponse(request,'personnel.html',info(request,db,people=users))

@app.post('/personal/guardar')
def save_person(request:Request,user_id:int=Form(0),username:str=Form(...),
    full_name:str=Form(...),role:str=Form('observador'),active:str=Form('yes'),
    password:str=Form(''),db:Session=Depends(get_db)):
    """Crea o actualiza cuentas, roles y permisos administrativos."""
    actor=require_chief(request,db)
    if role not in ('observador','jefe_estacion') or active not in ('yes','no'):
        raise HTTPException(422,'Rol o estado inválidos')
    if not re.fullmatch(r'[a-zA-Z0-9._-]{3,80}',username):
        raise HTTPException(422,'Nombre de usuario inválido')
    if not full_name.strip() or len(full_name)>160:raise HTTPException(422,'Nombre completo obligatorio')
    account=db.get(User,user_id) if user_id else None
    if user_id and not account:raise HTTPException(404,'Usuario inexistente')
    if db.query(User).filter(User.username==username,User.id!=user_id).first():
        raise HTTPException(409,'El nombre de usuario ya existe')
    if not account and len(password)<12:raise HTTPException(422,'La contraseña inicial requiere al menos 12 caracteres')
    if account and is_chief(account) and (role!='jefe_estacion' or active=='no'):
        others=db.query(User).filter(User.id!=account.id, User.role.in_(CHIEF_ROLES),User.active==True).count()
        if not others:raise HTTPException(409,'No se puede quitar el último Jefe activo')
    before={'name':account.full_name,'role':account.role,'active':account.active} if account else None
    if not account:account=User(password_hash=hash_password(password))
    account.username=username;account.full_name=full_name.strip();account.role=role;account.active=active=='yes'
    db.add(account);db.flush()
    log_change(db,actor,'actualizar_cuenta' if user_id else 'crear_cuenta','user',account.id,before,
               {'name':account.full_name,'role':role,'active':account.active})
    db.commit();return RedirectResponse('/personal',status_code=303)

@app.post('/personal/{user_id}/eliminar')
def deactivate_person(user_id:int,request:Request,db:Session=Depends(get_db)):
    """Desactiva cuentas conservando sus informes."""
    actor=require_chief(request,db);person=db.get(User,user_id)
    if not person:raise HTTPException(404,'Usuario inexistente')
    if is_chief(person) and db.query(User).filter(User.id!=person.id,User.role.in_(CHIEF_ROLES),User.active==True).count()==0:
        raise HTTPException(409,'No se puede desactivar el último Jefe activo')
    person.active=False;log_change(db,actor,'desactivar_cuenta','user',user_id,True,False)
    db.commit();return RedirectResponse('/personal',status_code=303)

@app.post('/personal/contrasena')
def change_password(request:Request,target_user_id:int=Form(...),new_password:str=Form(...),
    current_password:str=Form(''),db:Session=Depends(get_db)):
    """Cambia la contraseña propia o restablece una cuenta autorizada."""
    actor=require_user(request,db);target=db.get(User,target_user_id)
    if not target:raise HTTPException(404,'Usuario inexistente')
    if target.id!=actor.id and not is_chief(actor):raise HTTPException(403,'No podés modificar otra contraseña')
    if target.id==actor.id and not verify_password(current_password,actor.password_hash):
        raise HTTPException(403,'Contraseña actual incorrecta')
    if len(new_password)<12:raise HTTPException(422,'La nueva contraseña requiere 12 caracteres o más')
    target.password_hash=hash_password(new_password)
    log_change(db,actor,'cambio_contrasena_propia' if actor.id==target.id else 'restablecer_contrasena','user',target.id,None,'actualizada')
    db.commit();return RedirectResponse('/personal?contrasena=ok',status_code=303)


# --- TABLAS DE LA ESTACIÓN ---
@app.get('/tablas',response_class=HTMLResponse)
def tables_page(request:Request,sheet:str|None=None,db:Session=Depends(get_db)):
    """Lista las tablas meteorológicas disponibles."""
    names=get_table_names();selected=sheet if sheet in names else (names[0] if names else None)
    rows=get_table(selected) if selected else []
    history=db.query(AuditLog).filter(AuditLog.entity_type=='table',AuditLog.entity_id==selected).order_by(AuditLog.id.desc()).limit(15).all() if selected else []
    history=[h for h in history if (h.detail or {}).get('nuevo',{}).get('backup')]
    return templates.TemplateResponse(request,'tables.html',info(request,db,names=names,selected=selected,
        rows=rows,row_count=len(rows),table_history=history))

@app.get('/tablas/descargar/{sheet_name}')
def download_sheet(sheet_name:str,request:Request,db:Session=Depends(get_db)):
    """Descarga la hoja de Excel seleccionada."""
    require_chief(request,db)
    if sheet_name not in get_table_names():raise HTTPException(404,'Tabla inexistente')
    from openpyxl import load_workbook,Workbook
    src=load_workbook(DATA_DIR/'Tablas_Oran_Aero.xlsx',read_only=True,data_only=True)
    output=Workbook();ws=output.active;ws.title=sheet_name
    for row in src[sheet_name].iter_rows(values_only=True):ws.append(list(row))
    src.close();buffer=io.BytesIO();output.save(buffer);buffer.seek(0)
    return StreamingResponse(buffer,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':f'attachment; filename="tabla_Oran_AERO_{sheet_name.replace(" ","_")}.xlsx"'})

@app.post('/tablas/revisar')
async def preview_sheet(request:Request,sheet_name:str=Form(...),file:UploadFile=File(...),db:Session=Depends(get_db)):
    """Valida una hoja y muestra sus cambios antes de activarla."""
    u=require_chief(request,db)
    if sheet_name not in get_table_names():raise HTTPException(404,'Tabla inexistente')
    content=await file.read()
    if len(content)>5_000_000 or not file.filename.lower().endswith('.xlsx'):
        raise HTTPException(422,'Subí un Excel .xlsx de hasta 5 MB')
    try:
        from openpyxl import load_workbook
        existing=load_workbook(DATA_DIR/'Tablas_Oran_Aero.xlsx',read_only=True,data_only=True)
        proposed=load_workbook(io.BytesIO(content),read_only=True,data_only=True)
        if proposed.sheetnames!=[sheet_name]:raise ValueError('El archivo debe contener solamente la hoja seleccionada')
        a=existing[sheet_name];b=proposed[sheet_name]
        if a.max_row!=b.max_row or a.max_column!=b.max_column:raise ValueError('La estructura de la hoja no coincide')
        changes=[]
        for ra,rb in zip(a.iter_rows(),b.iter_rows()):
            for ca,cb in zip(ra,rb):
                av,bv=ca.value,cb.value
                if av==bv:continue
                # Filas de encabezado y columnas de referencia nunca se editan.
                locked_top={'QNH':7,'Tabla IV':7,'Tabla_D4':8,
                            'Humedad Relativa I':4,'Humedad Relativa II':4,
                            'Conversion_mmHg_hPa':4}.get(sheet_name,1)
                locked_humid=sheet_name=='Tabla Humedo' and any(start<=ca.row<=end for start,end in ((1,5),(42,47),(84,89)))
                if ca.column==1 or ca.row<=locked_top or locked_humid:
                    raise ValueError(f'Fila o columna de referencia no modificable: {ca.coordinate}')
                if not isinstance(av,(int,float)) or isinstance(av,bool) or not isinstance(bv,(int,float)) or isinstance(bv,bool):
                    raise ValueError(f'No se pueden modificar identificadores/encabezados: {ca.coordinate}')
                changes.append({'cell':ca.coordinate,'old':av,'new':bv})
        existing.close();proposed.close()
    except (ValueError,KeyError) as e:raise HTTPException(422,str(e))
    except Exception as e:raise HTTPException(422,'No se pudo interpretar el Excel') from e
    if not changes:raise HTTPException(422,'La hoja no contiene cambios')
    # Se guarda la propuesta en el servidor, nunca se acepta archivo arbitrario en activar.
    from hashlib import sha256
    token=sha256(content).hexdigest()
    target=DATA_DIR/'proposals';target.mkdir(exist_ok=True)
    (target/f'{u.id}-{token}.xlsx').write_bytes(content)
    request.session['table_proposal']={'sheet':sheet_name,'sha':token,'user':u.id}
    return templates.TemplateResponse(request,'table_preview.html',info(request,db,
         sheet=sheet_name,changes=changes[:200],total_changes=len(changes),token=token))

@app.post('/tablas/activar')
def activate_sheet(request:Request,token:str=Form(...),db:Session=Depends(get_db)):
    """Activa los valores de una hoja validada conservando respaldo."""
    u=require_chief(request,db)
    session=request.session.pop('table_proposal',{})
    if session.get('user')!=u.id or session.get('sha')!=token:
        raise HTTPException(403,'Propuesta inválida o vencida')
    from openpyxl import load_workbook
    source=DATA_DIR/'proposals'/f'{u.id}-{token}.xlsx'
    if not source.exists():raise HTTPException(404,'Propuesta inexistente')
    workbook=DATA_DIR/'Tablas_Oran_Aero.xlsx'
    from datetime import datetime as dt
    backup=DATA_DIR/'table_history';backup.mkdir(exist_ok=True)
    identifier=dt.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    import shutil
    shutil.copy2(workbook,backup/f'{identifier}.xlsx')
    target=load_workbook(workbook)
    proposed=load_workbook(source,data_only=True,read_only=True)
    sheet=session['sheet']
    for existing_row,new_row in zip(target[sheet].iter_rows(),proposed[sheet].iter_rows(values_only=True)):
        for cell,new in zip(existing_row,new_row):
            if isinstance(cell.value,(int,float)) and not isinstance(cell.value,bool) and isinstance(new,(int,float)):
                cell.value=new
    temp=DATA_DIR/f'.tables-{identifier}.xlsx';target.save(temp)
    temp.replace(workbook)
    proposed.close();target.close();source.unlink(missing_ok=True)
    # Ambas fuentes de psicrometría deben activarse juntas.
    from .calculations import _rows
    from .psychrometry_v04 import tables as psychro_tables
    _rows.cache_clear();psychro_tables.cache_clear();get_table_names.cache_clear()
    if sheet in ('Tabla Humedo','Tabla IV','Humedad Relativa I','Humedad Relativa II'):
        wb=load_workbook(workbook,read_only=True,data_only=True)
        import json
        data={name:[list(row) for row in wb[name].iter_rows(values_only=True)] for name in
              ('Tabla Humedo','Tabla IV','Humedad Relativa I','Humedad Relativa II')}
        wb.close();(DATA_DIR/'psicrometria_tablas.json').write_text(json.dumps(data,ensure_ascii=False,default=str),encoding='utf-8')
    log_change(db,u,'activar_tabla','table',sheet,None,{'backup':identifier,'sha256':token})
    db.commit()
    return RedirectResponse('/tablas?sheet='+sheet.replace(' ','%20'),status_code=303)

@app.post('/tablas/restaurar')
def restore_sheet(request:Request,sheet_name:str=Form(...),backup_id:str=Form(...),db:Session=Depends(get_db)):
    """Recupera una versión anterior de la hoja indicada."""
    user=require_chief(request,db)
    if sheet_name not in get_table_names() or not re.fullmatch(r'\d{8}T\d{12}',backup_id):
        raise HTTPException(422,'Referencia a la tabla inválida')
    audit=db.query(AuditLog).filter(AuditLog.entity_type=='table',AuditLog.entity_id==sheet_name).all()
    if not any((a.detail or {}).get('nuevo',{}).get('backup')==backup_id for a in audit):
        raise HTTPException(403,'No existe un respaldo autorizado para esta hoja')
    backup=DATA_DIR/'table_history'/f'{backup_id}.xlsx'
    if not backup.is_file():raise HTTPException(404,'No se encontró el respaldo')
    from openpyxl import load_workbook
    from datetime import datetime as dt
    import shutil
    current=DATA_DIR/'Tablas_Oran_Aero.xlsx'
    saved_id=dt.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    shutil.copy2(current,DATA_DIR/'table_history'/f'{saved_id}.xlsx')
    original=load_workbook(backup,read_only=True,data_only=True)
    target=load_workbook(current)
    old=original[sheet_name]
    sheet=target[sheet_name]
    if (old.max_row,old.max_column)!=(sheet.max_row,sheet.max_column):
        raise HTTPException(409,'La estructura del respaldo no coincide con la versión vigente')
    # Restaurar exclusivamente valores numéricos; las celdas combinadas y los encabezados son inmutables.
    for existing_row,old_row in zip(sheet.iter_rows(),old.iter_rows(values_only=True)):
        for cell,value in zip(existing_row,old_row):
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool) and isinstance(value, (int, float)) and not isinstance(value, bool):
                cell.value = value
    temp=DATA_DIR/f'.tables-restore-{saved_id}.xlsx'
    target.save(temp);temp.replace(current)
    original.close();target.close()
    from .calculations import _rows
    from .psychrometry_v04 import tables as psychro_tables
    _rows.cache_clear();psychro_tables.cache_clear();get_table_names.cache_clear()
    if sheet_name in ('Tabla Humedo','Tabla IV','Humedad Relativa I','Humedad Relativa II'):
        book=load_workbook(current,read_only=True,data_only=True)
        import json
        data={name:[list(row) for row in book[name].iter_rows(values_only=True)] for name in
              ('Tabla Humedo','Tabla IV','Humedad Relativa I','Humedad Relativa II')}
        book.close();(DATA_DIR/'psicrometria_tablas.json').write_text(json.dumps(data,ensure_ascii=False,default=str),encoding='utf-8')
    log_change(db,user,'restaurar_tabla','table',sheet_name,None,{'backup':saved_id,'restaurada_desde':backup_id})
    db.commit();return RedirectResponse('/tablas?sheet='+sheet_name.replace(' ','%20'),status_code=303)


# --- DOCUMENTOS DE CONSULTA ---
@app.get('/documentos/{filename}')
def reference_pdf(filename:str,request:Request,db:Session=Depends(get_db)):
    """Sirve al visor los documentos de referencia autorizados."""
    require_user(request,db)
    if filename not in ('clave_synop_smn_2022.pdf','libreta_smn_2022.pdf'):
        raise HTTPException(404,'Documento no disponible')
    return FileResponse(DATA_DIR/'pdf'/filename,media_type='application/pdf',
                        headers={'Content-Disposition':'inline'})
