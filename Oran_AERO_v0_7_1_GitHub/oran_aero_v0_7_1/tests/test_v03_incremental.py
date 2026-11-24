import unittest
from datetime import datetime, timezone
from app.synop_v03 import assemble, wind_knots, precip_rrr, temp_group, pressure_code

DT = datetime(2026,10,27,12,tzinfo=timezone.utc)

class V03Tests(unittest.TestCase):
    def test_wind_beaufort(self):
        self.assertEqual(wind_knots({'wind_unit':'3','wind_force':'4'}),13)
        self.assertIsNone(wind_knots({'wind_unit':'3','wind_force':'13'}))
    def test_wind_kmh_round(self):
        self.assertEqual(wind_knots({'wind_unit':'1','wind_force':'20'}),11)
    def test_temperature(self):
        self.assertEqual(temp_group('1','21.8'),'10218')
        self.assertEqual(temp_group('1','-3.5'),'11035')
    def test_pressure(self):
        self.assertEqual(pressure_code('985.6'),'9856')
    def test_trace(self):
        self.assertEqual(precip_rrr('0','yes'),'990')
        self.assertIsNone(precip_rrr('0','no'))
    def test_calmless_wind(self):
        d=assemble({'wind_unit':'3','wind_force':'0','wind_dd':'22','cloud_total':'5'},DT,'3')
        self.assertEqual(d['groups']['N'],'50000')
        self.assertFalse(d['can_finalize'])
    def test_qff_missing(self):
        d=assemble({'ts':'20','pressure_hpa':'985.6','ts_12h_unavailable':'yes'},DT,'3')
        self.assertEqual(d['groups']['4'],'4////')
    def test_tendency_missing(self):
        d=assemble({'pressure_hpa':'985.6','pressure_3h_unavailable':'yes'},DT,'3')
        self.assertEqual(d['groups']['5'],'5////')
    def test_cloud_omit(self):
        d=assemble({'cloud_total':'0'},DT,'3')
        self.assertNotIn('8',d['groups'])
    def test_cloud_eight(self):
        d=assemble({'cloud_total':'8','cl_form':'4','cm_form':'5','ch_form':'6','cl_degree':'8'},DT,'3')
        self.assertEqual(d['groups']['8'],'884//')

if __name__=='__main__':unittest.main()
