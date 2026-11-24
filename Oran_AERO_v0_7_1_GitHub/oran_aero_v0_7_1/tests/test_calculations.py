import unittest
from app.calculations import (
    convert_hpa_to_mmhg, convert_mmhg_to_hpa, psychrometer_depression,
    d4_correction, qnh_from_station_pressure,
)

class OranTableEngineTests(unittest.TestCase):
    def test_hpa_to_mmhg_example_from_station(self):
        self.assertEqual(convert_hpa_to_mmhg(948.3)["mmhg"], 711.2)

    def test_mmhg_to_hpa_uses_supplied_table(self):
        result = convert_mmhg_to_hpa(718.4)
        self.assertEqual(result["mmhg"], 718.4)
        self.assertEqual(result["hpa"], 957.9)

    def test_table_i_example(self):
        self.assertEqual(psychrometer_depression(18.9, 20.0, "Tabla I")["tabulated_value"], 66.7)

    def test_d4_example_from_station(self):
        result = d4_correction(30.5, 718.4)
        self.assertEqual(result["correction_mmhg"], 29.0)
        self.assertEqual(result["temperature_range"], "30.0 a 31.9")
        self.assertEqual(result["pressure_range_mmhg"], [717.4, 722.3])

    def test_qnh_table_lookup(self):
        self.assertEqual(qnh_from_station_pressure(948.3)["qnh_hpa"], 989.6)

    def test_wrong_psychrometer_table_is_rejected(self):
        with self.assertRaises(ValueError):
            psychrometer_depression(-2.0, -1.0, "Tabla I")

if __name__ == "__main__":
    unittest.main()
