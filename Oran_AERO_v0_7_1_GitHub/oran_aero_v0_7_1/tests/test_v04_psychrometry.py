from app.psychrometry_v04 import calculate
from app.synop_v03 import assemble
from datetime import datetime,timezone

def test_approved_positive_case():
    x=calculate(32.5,25.7,'I')
    assert (x['dew_point_c'],x['vapor_hpa'],x['relative_humidity_pct'])==(22.9,27.8,57)

def test_approved_negative_case():
    x=calculate(-.3,-1.3,'III')
    assert (x['dew_point_c'],x['vapor_hpa'],x['relative_humidity_pct'])==(-3.3,4.8,77)

def test_synop_group2_positive():
    x=assemble({'ts':'32.5','th':'25.7','psychro_table':'I'},datetime(2026,10,29,12,tzinfo=timezone.utc),'3')
    assert x['groups']['2']=='20229'

def test_synop_group2_missing():
    x=assemble({'ts':'32.5'},datetime(2026,10,29,12,tzinfo=timezone.utc),'3')
    assert x['groups']['2']=='2////'

def test_out_of_service_groups():
    ins={k:{'status':'fuera_servicio','correction':0,'correction_mode':'SC'} for k in ('ts','th','pressure','wind')}
    x=assemble({'cloud_total':'5','ts':'32.5','pressure_hpa':'948.3'},datetime(2026,10,29,12,tzinfo=timezone.utc),'3',instruments=ins)
    for k,g in [('1','1////'),('2','2////'),('3','3////'),('4','4////'),('5','5////'),('N','5////')]:assert x['groups'][k]==g
