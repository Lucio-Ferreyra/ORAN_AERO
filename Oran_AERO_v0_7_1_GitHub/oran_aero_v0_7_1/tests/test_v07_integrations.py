"""Regresiones agregadas a v0.7: historial, permisos y extremos UTC/HOA."""
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
from app.models import User, Observation, Report, DailyExtremes
from app.security import hash_password
from app.services_v07 import compute_daily_extremes, previous_day_hoa_hr, week_precipitation
from app.section5_v07 import weekly_code, hr_coded, section5_groups
from app.synop_rules_v05 import precip_groups

PWD='Clav3-MuyLarga-2026!'

def setup():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);S=sessionmaker(bind=engine)
    with S() as db:
        db.add_all([User(username='chief',full_name='Jefe',role='jefe_estacion',active=True,password_hash=hash_password(PWD)),
                    User(username='watcher',full_name='Observador',role='observador',active=True,password_hash=hash_password(PWD))])
        db.commit()
    def dependency():
        with S() as db:yield db
    app.dependency_overrides[get_db]=dependency
    return engine,S

def login(c,username):
    resp=c.post('/login',data={'username':username,'password':PWD},follow_redirects=False)
    assert resp.status_code==303

def observation(c):
    assert c.get('/synop').status_code==200
    return c.get('/api/synop/draft').json()

VALID={
    'ts':'30.1','th':'30.0','pressure_hpa':'987.6','ts_12h_manual':'29.0',
    'pressure_3h_manual':'986.6','tendency_a':'2','wind_dd':'18','wind_force':'3',
    'wind_unit':'3','ww':'02','w1':'0','w2':'0','cloud_total':'0',
    'visibility_coarse':'25','soil_state':'0','plafond':'0','precip_state':'no'}


def test_save_and_revise_preserves_old_report_and_new_version():
    engine,S=setup()
    try:
        with TestClient(app) as c:
            login(c,'chief');d=observation(c)
            assert 'AAXX' in d['message']
            r=c.post('/api/synop/autoguardado',json={'observation_id':d['observation_id'],'values':VALID})
            assert r.status_code==200
            assert r.json()['missing']==[]
            assert r.json()['message'].endswith('555 10303')
            saved=c.post('/api/synop/finalizar',json={'observation_id':d['observation_id'],'confirmed':True})
            assert saved.status_code==200,saved.text
            one=saved.json()['report_id']
            assert c.get('/reportes/'+str(one)).status_code==200
            assert c.post(f'/reportes/{one}/corregir',follow_redirects=False).status_code==303
            edited=c.get('/api/synop/draft').json()
            vals={**VALID,'ts':'31.1'}
            assert c.post('/api/synop/autoguardado',json={'observation_id':edited['observation_id'],'values':vals}).status_code==200
            saved2=c.post('/api/synop/finalizar',json={'observation_id':edited['observation_id'],'confirmed':True})
            assert saved2.status_code==200,saved2.text
            assert saved2.json()['version']==2
            with S() as db:
                assert db.query(Report).count()==2
                old=db.get(Report,one);new=db.get(Report,saved2.json()['report_id'])
                assert old.message!=new.message
                assert old.values_snapshot['ts']=='30.1'
                assert new.values_snapshot['ts']=='31.1'
                assert db.query(DailyExtremes).count()==1
    finally:
        app.dependency_overrides.clear();engine.dispose()


def test_roles_and_passwords_are_enforced_server_side():
    engine,S=setup()
    try:
        with TestClient(app) as c:
            login(c,'watcher')
            assert c.post('/estacion',data={'name':'Peligro','block_number':'87','station_number':'016',
                'latitude':"23°09' S",'longitude':"64°19' O",'runway_elevation_m':'357',
                'wind_method':'estimado','wind_iw':'3'}).status_code==403
            assert c.post('/personal/guardar',data={'username':'evil','full_name':'Evil','role':'jefe_estacion','password':PWD}).status_code==403
            assert c.post('/personal/contrasena',data={'target_user_id':'1','new_password':'X'*15,'current_password':PWD}).status_code==403
            assert c.post('/personal/contrasena',data={'target_user_id':'2','new_password':'New-2026-Password','current_password':PWD},follow_redirects=False).status_code==303
            c.post('/logout')
            login(c,'chief')
            response=c.post('/estacion',data={'name':'Orán AERO','block_number':'87','station_number':'016',
                'latitude':"23°09' S",'longitude':"64°19' O",'runway_elevation_m':'357',
                'wind_method':'anemometro','wind_iw':'4'},follow_redirects=False)
            assert response.status_code==303
            assert observation(c)['section0'].startswith('AAXX ')
            assert observation(c)['section0'].split(' ')[1][-1]=='4'
            assert c.post('/personal/contrasena',data={'target_user_id':'2','new_password':'Reset-2026-Password'},follow_redirects=False).status_code==303
    finally:
        app.dependency_overrides.clear();engine.dispose()


def insert(db,stamp,details,derived,station_id=1):
    obs=Observation(station_id=station_id,observer_id=1,observation_time_utc=stamp,
                    status='finalizado',values=details)
    db.add(obs);db.flush()
    report=Report(observation_id=obs.id,status='finalizado',report_type='SYNOP',message='AAXX',
                  version_number=1,values_snapshot=details,derived_snapshot=derived)
    db.add(report);db.flush();return report


def test_extreme_wind_tie_uses_first_occurrence_and_utc_half_open():
    engine,S=setup()
    try:
        with S() as db:
            base=datetime(2026,11,19)
            insert(db,base+timedelta(hours=10),{'wind_dd':'18','wind_unit':'3','wind_force':'5'},
                   {'wind_kt':18,'th_corrected':24,'dew_point_c':18,'relative_humidity_pct':85,'vapor_hpa':24})
            insert(db,base+timedelta(hours=14),{'wind_dd':'27','wind_unit':'4','wind_force':'24'},
                   {'wind_kt':24,'temp_max_corrected':34,'temp_min_corrected':23,'th_corrected':25,'relative_humidity_pct':90})
            insert(db,base+timedelta(hours=17),{'wind_dd':'29','wind_unit':'4','wind_force':'24'},
                   {'wind_kt':24,'th_corrected':20,'relative_humidity_pct':60,'vapor_hpa':17})
            insert(db,base+timedelta(days=1),{'wind_dd':'12','wind_unit':'4','wind_force':'95'},
                   {'wind_kt':95,'relative_humidity_pct':100})
            db.commit()
            x=compute_daily_extremes(db,1,date(2026,11,19))
            assert x['wind_max']['knots']=='24' and x['wind_max']['time_utc'].endswith('14:00:00')
            assert x['hr_max']['value']=='90' and x['hr_min']['value']=='60'
            assert x['temperature_max']['value']=='34'
            assert x['temperature_min']['value']=='23'
            assert x['report_count']==3
    finally:
        app.dependency_overrides.clear();engine.dispose()


def test_previous_day_hoa_differs_from_daily_utc():
    engine,S=setup()
    try:
        with S() as db:
            insert(db,datetime(2026,11,19,1),{}, {'relative_humidity_pct':10})  # outside HOA previous day
            insert(db,datetime(2026,11,19,5),{}, {'relative_humidity_pct':94})  # inside
            insert(db,datetime(2026,11,19,20),{}, {'relative_humidity_pct':56}) # inside
            insert(db,datetime(2026,11,20,1),{}, {'relative_humidity_pct':99}) # HOA prior day 22:00
            db.commit()
            x=previous_day_hoa_hr(db,1,datetime(2026,11,20,12))
            assert x['max']['value']=='99' and x['min']['value']=='56'
            assert hr_coded(x)=='89956'
            assert hr_coded({'max':{'value':'100'},'min':{'value':'37'}})=='80037'
    finally:
        app.dependency_overrides.clear();engine.dispose()


def test_weekly_traces_and_time_gates():
    assert weekly_code({'total':'0','has_rain':True,'all_no':False})=='90000'
    assert weekly_code({'total':'0','has_rain':False,'all_no':True})=='9///0'
    assert weekly_code({'total':'19.89','has_rain':True,'all_no':False})=='90198'
    assert weekly_code({'total':'0','has_rain':False,'all_no':False}) is None
    assert not section5_groups(datetime(2026,11,21,6),{'ww':'02'})['groups']
    assert section5_groups(datetime(2026,11,21,6),{'ww':'04','ash_present':'yes'})['groups']==['29999']
    for hour in range(24):
        result=precip_groups(hour,{'precip_state':'yes','precip_mm':'2'}, {})
        assert bool(result['section1'])==(hour in (0,6,12,18))
        assert bool(result['section3'])==(hour==12)
    assert precip_groups(6,{'precip_state':'yes','precip_mm':'0.4'}, {})['section1']=='69941'

def test_wind_units_follow_iw_while_daily_extremes_keep_knots():
    from app.synop_v03 import assemble
    v={**VALID,'cloud_total':'0','wind_force':'5','wind_unit':'3'}
    d=datetime(2026,11,20,12)
    knots=assemble(v,d,'3')
    metric=assemble(v,d,'0')
    assert knots['derived']['wind_kt']==metric['derived']['wind_kt']==18
    assert knots['groups']['N']=='01818'
    assert metric['groups']['N']=='01809'

def test_download_preview_activate_and_restore_one_sheet(tmp_path,monkeypatch):
    import io,re,shutil
    from pathlib import Path
    from openpyxl import load_workbook
    import app.main as main
    import app.table_data as table_data
    import app.calculations as calculations
    import app.psychrometry_v04 as psychro
    from app.models import AuditLog
    origin=Path(__file__).resolve().parents[1]/'data'
    (tmp_path/'Tablas_Oran_Aero.xlsx').write_bytes((origin/'Tablas_Oran_Aero.xlsx').read_bytes())
    (tmp_path/'psicrometria_tablas.json').write_bytes((origin/'psicrometria_tablas.json').read_bytes())
    monkeypatch.setattr(main,'DATA_DIR',tmp_path)
    monkeypatch.setattr(table_data,'WORKBOOK',tmp_path/'Tablas_Oran_Aero.xlsx')
    monkeypatch.setattr(calculations,'WORKBOOK',tmp_path/'Tablas_Oran_Aero.xlsx')
    monkeypatch.setattr(psychro,'DATA_DIR',tmp_path)
    table_data.get_table_names.cache_clear();calculations._rows.cache_clear();psychro.tables.cache_clear()
    engine,S=setup()
    try:
        with TestClient(app) as c:
            login(c,'chief')
            original=c.get('/tablas/descargar/QNH')
            assert original.status_code==200
            wb=load_workbook(io.BytesIO(original.content))
            ws=wb['QNH'];before=ws['B8'].value
            ws['B8']=before-0.1
            data=io.BytesIO();wb.save(data);wb.close()
            result=c.post('/tablas/revisar',data={'sheet_name':'QNH'},
                files={'file':('QNH.xlsx',data.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
            assert result.status_code==200,result.text[:300]
            token=re.search(r'name="token" value="([0-9a-f]{64})"',result.text).group(1)
            updated=c.post('/tablas/activar',data={'token':token},follow_redirects=False)
            assert updated.status_code==303,updated.text
            wb=load_workbook(tmp_path/'Tablas_Oran_Aero.xlsx',read_only=True,data_only=True)
            assert abs(wb['QNH']['B8'].value-(before-0.1))<0.001
            wb.close()
            with S() as db:
                change=db.query(AuditLog).filter_by(action='activar_tabla').first()
                assert change is not None
                backup_id=change.detail['nuevo']['backup']
            restore=c.post('/tablas/restaurar',data={'sheet_name':'QNH','backup_id':backup_id},follow_redirects=False)
            assert restore.status_code==303,restore.text
            wb=load_workbook(tmp_path/'Tablas_Oran_Aero.xlsx',read_only=True,data_only=True)
            assert wb['QNH']['B8'].value==before
            wb.close()
    finally:
        app.dependency_overrides.clear();engine.dispose()
        table_data.get_table_names.cache_clear();calculations._rows.cache_clear();psychro.tables.cache_clear()


def test_past_pressure_from_json_float_is_normalized_without_rounding():
    """Un informe previo almacena float; la tendencia usa Decimal de ambos lados."""
    from decimal import Decimal
    from app.synop_v03 import assemble
    instant = datetime(2026, 11, 22, 15, tzinfo=timezone.utc)
    data = {'pressure_hpa': '987.68', 'tendency_a': '2'}
    for historical in (985.25, '985.25', Decimal('985.25')):
        report = assemble(data, instant, '3', history_3h=historical, history_12h=29.1)
        assert report['groups']['5'] == '52024'
        assert report['derived']['pressure_tendency_hpa'] == 2.43
        assert report['groups']['3'] == '39876'


def test_workspace_and_autosave_recover_past_float_pressure():
    """Reproduce el error 500 de /synop y /api/synop/autoguardado del registro."""
    from app.models import Station
    engine, S = setup()
    try:
        with S() as db:
            db.add(Station(id=1))
            db.flush()
            instant = datetime(2026, 11, 22, 15)
            insert(db, instant - timedelta(hours=12), {},
                   {'ts_corrected': 29.1})
            insert(db, instant - timedelta(hours=3), {},
                   {'pressure_corrected': 985.25})
            draft = Observation(
                station_id=1, observer_id=1, observation_time_utc=instant,
                status='borrador_autoguardado',
                values={'pressure_hpa': '987.68', 'tendency_a': '2',
                        '_step': 0, '_ui_flow_version': '3'},
            )
            db.add(draft)
            db.commit()
            draft_id = draft.id
        with TestClient(app) as client:
            login(client, 'chief')
            page = client.get('/synop')
            assert page.status_code == 200, page.text[:300]
            state = client.get('/api/synop/draft')
            assert state.status_code == 200, state.text
            assert state.json()['groups']['5'] == '52024'
            response = client.post('/api/synop/autoguardado', json={
                'observation_id': draft_id,
                'values': {'pressure_hpa': '987.68', 'tendency_a': '2',
                           'ts': '30.1', 'th': '30.0',
                           'cloud_total': '0', 'visibility_coarse': '25',
                           'wind_dd': '18', 'wind_force': '3', 'wind_unit': '3',
                           'ww': '02', 'w1': '0', 'w2': '0'},
            })
            assert response.status_code == 200, response.text
            body = response.json()
            assert body['groups']['5'] == '52024'
            assert body['derived']['pressure_tendency_hpa'] == 2.43
            assert body['historical_p3_found'] is True
            assert body['historical_ts12'] == 29.1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
