"""Regresiones para irixhVV y el foco del campo ww en la interfaz."""
from datetime import datetime, timezone
from pathlib import Path

from app.main import clean_values
from app.synop_v03 import assemble


AT_03_UTC = datetime(2026, 11, 22, 3, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def build(**overrides):
    values = {'cloud_total': '0', 'visibility_coarse': '25', 'ww': '02', 'w1': '0', 'w2': '0'}
    values.update(overrides)
    return assemble(values, AT_03_UTC, '3')


def test_unreported_visibility_is_not_invented_as_00():
    result = build(visibility_coarse='')
    assert 'irixhVV' not in result['groups']
    assert any('Ingresar visibilidad VV' in issue for issue in result['missing'])
    assert result['derived'].get('visibility_fine') is None


def test_valid_00_is_still_a_valid_observation_and_keeps_zeroes():
    result = build(visibility_coarse='00')
    assert result['groups']['irixhVV'] == '32900'
    assert result['derived']['visibility_fine'] == '90'


def test_no_clouds_uses_h9_even_if_old_draft_had_zero():
    result = build(plafond='0')
    assert result['groups']['irixhVV'] == '32925'


def test_unknown_cloud_base_can_be_coded_as_slash():
    result = build(cloud_total='4', plafond='/')
    assert result['groups']['irixhVV'] == '32/25'
    assert clean_values({'cloud_total': '4', 'plafond': '/'}, 3, {})['plafond'] == '/'


def test_invisible_sky_uses_slash_without_rerequesting_height():
    result = build(cloud_total='9')
    assert result['groups']['irixhVV'] == '32/25'
    assert clean_values({'cloud_total': '9'}, 3, {})['plafond'] == '/'


def test_cloudless_backend_autofill_uses_nine_not_zero():
    result = clean_values({'cloud_total': '0', 'plafond': '0', 'visibility_coarse': '25'}, 3, {})
    assert result['plafond'] == '9'
    assert result['visibility_coarse'] == '25'


def test_ix2_when_weather_codes_are_complete_and_non_significant():
    result = build(ww='02', w1='0', w2='0')
    assert result['groups']['irixhVV'] == '32925'
    assert '7' not in result['groups']
    assert ' 7' not in result['message']


def test_ix1_for_significant_ww_with_complete_past_weather():
    result = build(ww='07', w1='0', w2='0')
    assert result['groups']['irixhVV'] == '31925'
    assert result['groups']['7'] == '70700'


def test_ww_and_both_past_weather_fields_always_required():
    for overrides, description in (
        ({'ww': ''}, 'tiempo presente ww'),
        ({'ww': '0'}, 'tiempo presente ww'),
        ({'w1': ''}, 'tiempo pasado W1'),
        ({'w2': ''}, 'tiempo pasado W2'),
        ({'w1': '12'}, 'tiempo pasado W1'),
    ):
        result = build(**overrides)
        assert 'irixhVV' not in result['groups']
        assert any(description in item for item in result['missing'])
        assert not result['can_finalize']


def test_no_weather_observed_option_cannot_override_required_codes():
    with_codes = build(weather_unavailable='yes')
    assert with_codes['groups']['irixhVV'] == '32925'
    without_codes = build(ww='', w1='', w2='', weather_unavailable='yes')
    assert 'irixhVV' not in without_codes['groups']
    assert not without_codes['can_finalize']


def test_js_does_not_rebuild_all_inputs_while_typing_ww():
    script = (ROOT / 'app/static/workspace_v03.js').read_text(encoding='utf-8')
    # The description must be updated in place and not trigger render() for ww.
    assert "'cl_form'].includes(key))render();" in script
    assert "if(key==='ww'){const desc=fields.querySelector('.v04-code-description')" in script
    assert "'coded-height'" in script


def test_legacy_weather_unavailable_field_is_ignored_when_saving():
    cleaned = clean_values({
        'weather_unavailable': 'yes', 'ww': '07', 'w1': '4', 'w2': '3',
        'cloud_total': '0', 'visibility_coarse': '25',
    }, 3, {})
    assert 'weather_unavailable' not in cleaned
    assert [cleaned[key] for key in ('ww', 'w1', 'w2')] == ['07', '4', '3']
    result = assemble(cleaned, AT_03_UTC, '3')
    assert result['groups']['irixhVV'] == '31925'
    assert result['groups']['7'] == '70743'


def test_weather_required_ui_and_no_observation_unavailable_option():
    script = (ROOT / 'app/static/workspace_v03.js').read_text(encoding='utf-8')
    assert 'weather_unavailable' not in script
    assert 'Observación del tiempo no disponible' not in script
    assert "input.required=true" in script
    assert "['ww','w1','w2'].includes(f.key)" in script


def test_invisible_sky_does_not_force_section1_cloud_group_8():
    result = build(cloud_total='9')
    assert '8' not in result['groups']
    assert result['derived']['cloud_groups_omitted'] is True
