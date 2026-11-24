"""Regresiones de navegación y autoguardado de la actualización de pantallas."""
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password
from app.synop_rules_v05 import cloud_section3

ROOT=Path(__file__).resolve().parents[1]

def test_screen_fields_and_navigation_js():
    js=(ROOT/'app/static/workspace_v03.js').read_text()
    template=(ROOT/'app/templates/workspace_v03.html').read_text()
    code=(ROOT/'app/static/synop_code_descriptions.js').read_text()
    assert "['ch', 'altas', '0509'], ['cm', 'medias', '0515'], ['cl', 'bajas', '0513']" in js
    assert "id:'phenomena',title:'Fenómenos, visibilidad y suelo'" in js
    assert "id:'clouds',title:'Nubosidad observada'" in js
    assert js.index("id:'phenomena'") < js.index("id:'clouds'") < js.index("id:'cloud-bases'") < js.index("id:'cloud-layers'")
    assert "id:'precipitation',title:'Precipitación',when:()" in js
    assert "id:'temperatures',title:'Temperaturas máxima y mínima',when:()" in js
    assert "values.layer2_exists!=='yes'" in js
    assert "values.layer3_exists!=='yes'" in js
    assert "form==='0'||values.cloud_total==='0'" in js
    assert "form==='/'" in js
    assert "field('visibility_fine'" not in js
    assert "descriptionSource =" in js
    assert "displayCodeDescription(key,value)" in js
    assert "soil_state: codes.soil, w1: codes.past, w2: codes.past, tendency_a: codes.tendency" in js
    for marker in ('0509','0515','0513','0901','4561','0200'):
        assert marker in code
    assert 'test-observation-utc' not in js
    assert 'id="confirm-modal"' in template
    assert 'id="return-edit" class="secondary v05-return-edit"' in template
    assert '{{ loop.index }}.' not in template
    assert 'beta' not in template.lower()
    assert 'sujeto a revisión' not in template.lower()


def test_no_second_layer_omits_second_and_third():
    v={'cl_base':'25','ch_base':'70','layer1_genus':'9','layer1_octas':'1',
       'layer2_exists':'no','layer2_genus':'6','layer2_octas':'3','layer2_base':'30',
       'layer3_exists':'yes','layer3_genus':'0','layer3_octas':'8'}
    assert cloud_section3(v)['groups']==['81925']


def test_autosave_cloud_defaults_and_layer_locks():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    def test_db():
        with sessions() as db:yield db
    with sessions() as db:
        db.add(User(username='cloud_v051',full_name='Observador',password_hash=hash_password('StrongPassword12345!'),role='observador',active=True))
        db.commit()
    app.dependency_overrides[get_db]=test_db
    try:
        with TestClient(app) as client:
            assert client.post('/login',data={'username':'cloud_v051','password':'StrongPassword12345!'},follow_redirects=False).status_code==303
            draft=client.get('/api/synop/draft').json() if client.get('/api/synop/draft').status_code==200 else None
            if draft is None:
                assert client.get('/synop').status_code==200
                draft=client.get('/api/synop/draft').json()
            r=client.post('/api/synop/autoguardado',json={'observation_id':draft['observation_id'],'values':{
                'cloud_total':'8','ch_form':'0','ch_degree':'7','ch_base':'80','direction_ch':'6',
                'cm_form':'/','cm_degree':'4','direction_cm':'5',
                'cl_form':'9','cl_degree':'4','cl_base':'25',
                'layer2_exists':'no','layer2_genus':'6','layer2_octas':'3',
                'layer3_exists':'yes','layer3_genus':'0','layer3_octas':'8'}})
            assert r.status_code==200,r.text
            v=r.json()['values']
            assert (v['ch_degree'],v['ch_base'],v['direction_ch'])==('0','0','0')
            assert (v['cm_degree'],v['cm_base'],v['direction_cm'])==('/','/','/')
            assert v['layer2_genus']=='' and v['layer3_genus']==''
            assert v['layer3_exists']=='no'
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
