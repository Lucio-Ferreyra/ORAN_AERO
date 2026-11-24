"""Casos de aceptación basados en decisiones expresas del observador Orán AERO."""
from datetime import datetime, timezone
from app.synop_rules_v05 import visibility_fine, precip_groups, cloud_section3
from app.synop_v03 import assemble, pressure_code, temp_group
from app.psychrometry_v04 import calculate


def test_vv_4377_todos_los_codigos_gruesos():
    bands=[(0,0,90),(1,1,91),(2,4,92),(5,9,93),(10,19,94),
           (20,39,95),(40,59,96),(60,69,97),(70,83,98),(84,89,99)]
    for lo,hi,fine in bands:
        for code in range(lo,hi+1):
            assert visibility_fine(f'{code:02d}')==str(fine)
    assert visibility_fine('90') is None
    assert visibility_fine('5') is None


def test_presion_y_temperatura_decimas_sin_redondear():
    assert pressure_code('987.68')=='9876'
    assert pressure_code('1012.78')=='0127'
    assert temp_group('1','30.19')=='10301'
    assert temp_group('1','-1.39')=='11013'
    r=assemble({'pressure_hpa':'987.68','pressure_3h_manual':'985.25','tendency_a':'2'},
               datetime(2026,11,3,0,tzinfo=timezone.utc),'3')
    assert r['groups']['5']=='52024'
    assert r['groups']['3']=='39876'


def test_variacion_870_2_omitir_centenas_de_ppp():
    r=assemble({'pressure_hpa':'900.2','pressure_3h_manual':'30','tendency_a':'2'},
               datetime(2026,11,3,0,tzinfo=timezone.utc),'3')
    assert r['groups']['5']=='52702'


def test_precipitacion_24h_datos_ausentes_aportan_cero():
    history={18:{'state':'yes','mm':'5'},0:{'state':'unknown'},6:{'state':'yes','mm':'3'}}
    v={'precip_state':'yes','precip_mm':'2'}
    r=precip_groups(12,v,history)
    assert r['derived']['precip_24h_mm']=='10'
    assert r['section1']=='60104'
    assert r['section3']==['60021']
    assert r['states']==['yes','unknown','yes','yes']


def test_precipitacion_traza_y_horarios():
    assert precip_groups(3,{'precip_state':'yes','precip_mm':'5'}, {})['section1'] is None
    assert precip_groups(6,{'precip_state':'yes','precip_mm':'0'}, {})['section1']=='69901'
    # 990 trazas: grupo de 5 posiciones 6 + 990 + tR=1.
    x=precip_groups(12,{'precip_state':'yes','precip_mm':'0'}, {})
    assert x['section1']=='69904'
    assert x['section3']==['69901']
    assert precip_groups(18,{'precip_state':'unknown'}, {})['section1'] is None


def test_nubes_ejemplo_usuario_y_alturas_repetidas():
    v={'cl_base':'25','ch_base':'70','layer1_genus':'9','layer1_octas':'1',
       'layer2_genus':'6','layer2_octas':'3','layer2_base':'30',
       'layer3_exists':'yes','layer3_genus':'0','layer3_octas':'8'}
    r=cloud_section3(v)
    assert r['groups']==['81925','83630','88070']
    assert not r['warnings']
    v['layer2_base']='25'
    r=cloud_section3(v)
    assert r['groups']==[] and 'distintas' in r['warnings'][0]
    v['layer3_exists']='no'
    v['layer2_base']='30'
    assert cloud_section3(v)['groups']==['81925','83630']


def test_psicrometria_corrigida_confirmada_30_1_30_0():
    r=calculate(30.1,30.0)
    assert (r['dew_point_c'],r['vapor_hpa'],r['relative_humidity_pct']) == (29.9,42.3,99)


def test_no_grupos_no_seleccionados():
    v={'ts':'30.1','th':'30.0','pressure_hpa':'987.6','pressure_3h_manual':'987.0',
       'tendency_a':'2','precip_state':'no','cloud_total':'0','visibility_coarse':'25',
       'plafond':'3','ww':'02','w1':'0','w2':'0','wind_dd':'18','wind_unit':'3','wind_force':'3'}
    r=assemble(v,datetime(2026,11,3,12,tzinfo=timezone.utc),'3')
    assert '333' not in r['message']
    assert '333' not in r['section0']
    assert set(r['groups']).issubset({'irixhVV','N','1','2','3','4','5','6','7','8'})

def test_cloud_layer_octas_are_not_summed_across_levels():
    from app.synop_v03 import assemble
    v={'cloud_total':'8','cl_form':'9','cl_degree':'4','ch_form':'3','ch_degree':'8',
       'cm_form':'0','cm_degree':'0','cl_base':'25','ch_base':'70','layer1_genus':'9',
       'layer1_octas':'1','layer2_genus':'6','layer2_octas':'3','layer2_base':'30',
       'layer3_exists':'yes','layer3_genus':'0','layer3_octas':'8'}
    x=assemble(v,datetime(2026,11,3,12,tzinfo=timezone.utc),'3')
    assert x['groups']['8']=='84903'
    assert x['section3']==['81925','83630','88070']
    assert not any('suma' in w.lower() for w in x['warnings'])
