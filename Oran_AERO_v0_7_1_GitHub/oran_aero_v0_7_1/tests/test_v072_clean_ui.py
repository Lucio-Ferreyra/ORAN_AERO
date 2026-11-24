from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_no_development_messages_in_public_templates():
    templates = (ROOT / "app" / "templates").glob("*.html")
    content = "\n".join(template.read_text(encoding="utf-8").lower() for template in templates)
    for notice in (
        "etapa de desarrollo",
        "borrador parcial",
        "se completará con los grupos validados",
        "los grupos meteorológicos aún están en desarrollo",
        "todavía no está completo ni es apto para transmitir",
    ):
        assert notice not in content


def test_modules_keep_documented_responsibilities():
    for source in (ROOT / "app").glob("*.py"):
        program = ast.parse(source.read_text(encoding="utf-8"))
        assert ast.get_docstring(program), f"Falta la descripción del módulo {source.name}"


def test_real_warnings_are_kept_in_synop():
    source = (ROOT / "app" / "synop_v03.py").read_text(encoding="utf-8")
    assert "QFF no calculable" in source
    assert "VV debe ser un código" in source
    assert "Grupo irixhVV pendiente de codificación completa" not in source
