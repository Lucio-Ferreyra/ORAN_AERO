"""Compatibilidad de borradores y nuevas tablas descriptivas del flujo de carga."""
from pathlib import Path
from app.main import restored_screen_index
from app.synop_v03 import STEPS

ROOT = Path(__file__).resolve().parents[1]


def test_restore_old_draft_sections():
    assert restored_screen_index({'_step': 3}) == 4  # Nubosidad
    assert restored_screen_index({'_step': 4}) == 7  # Precipitación
    assert restored_screen_index({'_step': 5}) == 3  # Fenómenos, VV, suelo
    assert restored_screen_index({'_step': 3, '_ui_flow_version': '2'}) == 3
    assert restored_screen_index({'_step': 5, '_ui_flow_version': '2'}) == 7
    for invalid in (None, '', 'número', -1, 20):
        assert restored_screen_index({'_step': invalid}) == 0
    assert restored_screen_index({}) == 0


def test_no_numbered_screen_names_and_order():
    assert STEPS[3:8] == ('Fenómenos, visibilidad y suelo', 'Nubosidad observada', 'Bases y desplazamiento', 'Capas de nubes', 'Precipitación')
    assert len(STEPS) == 12
    assert not any(s[:2].strip().rstrip('.').isdigit() for s in STEPS)


def test_reference_descriptions_loaded_in_correct_order():
    html=(ROOT/'app/templates/workspace_v03.html').read_text()
    assert html.index('synop_code_descriptions.js') < html.index('workspace_v03.js')
    code=(ROOT/'app/static/synop_code_descriptions.js').read_text()
    for tag in ('cl:', 'cm:', 'ch:', 'soil:', 'past:', 'tendency:'):
        assert tag in code
    assert "'3': 'Suelo inundado.'" in code
    assert "'4': 'Superficie del suelo helada.'" in code
    assert "'9': 'Cirrocúmulus predominantes" in code
