"""Verifica que la Sección 0 tenga solo tres elementos y siga el orden aprobado."""
from datetime import datetime, timezone
from app.synop_v03 import assemble

DATE = datetime(2026, 11, 22, 20, tzinfo=timezone.utc)
COORDS = ("23°09′ S", "64°19′ O")


def observation(**values):
    base = {
        'cloud_total': '5', 'plafond': '5', 'visibility_coarse': '60',
        'ww': '02', 'w1': '0', 'w2': '0',
        'wind_dd': '14', 'wind_unit': '3', 'wind_force': '2',
    }
    base.update(values)
    return assemble(base, DATE, '3', station_coordinates=COORDS)


def test_no_unrequested_latitude_group():
    result = observation()
    tokens = result['message'].split()
    assert result['section0'] == 'AAXX 22203 87016'
    assert tokens[:3] == ['AAXX', '22203', '87016']
    assert len(result['section0'].split()) == 3
    assert '99231' not in tokens
    assert '50643' not in tokens
    assert not any(token.startswith('99') and len(token) == 5 for token in tokens)


def test_irixhvv_immediately_precedes_nddff():
    result = observation()
    tokens = result['message'].split()
    assert result['groups']['irixhVV'] == '32560'
    assert result['groups']['N'] == '51405'
    assert tokens[:5] == ['AAXX','22203','87016','32560','51405']
    assert tokens.index('51405') == tokens.index('32560') + 1


def test_order_without_station_coordinates_is_also_correct():
    result = assemble({
        'cloud_total': '0', 'visibility_coarse': '25',
        'ww': '02', 'w1': '0', 'w2': '0',
        'wind_dd': '14', 'wind_unit': '3', 'wind_force': '2',
    }, DATE, '3')
    tokens = result['message'].split()
    assert tokens[:5] == ['AAXX', '22203', '87016', '32925', '01405']


def test_coordinates_never_enter_section_zero():
    """Los datos geográficos son informativos, no grupos del SYNOP solicitado."""
    for coords in (("23°09′ S", "64°19′ O"), ("11°30′ N", "22°44′ E"),
                   (None, None)):
        result = assemble({'cloud_total': '0', 'visibility_coarse': '25',
                           'ww': '02', 'w1': '0', 'w2': '0',
                           'wind_dd': '14', 'wind_unit': '3', 'wind_force': '2'},
                          DATE, '3', station_coordinates=coords)
        assert result['section0'].split() == ['AAXX', '22203', '87016']
        assert result['message'].split()[:5] == ['AAXX', '22203', '87016',
                                                   '32925', '01405']
