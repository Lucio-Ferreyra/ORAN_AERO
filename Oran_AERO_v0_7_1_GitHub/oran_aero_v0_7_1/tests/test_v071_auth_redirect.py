"""v0.7.1: browser navigation redirects to login while APIs retain JSON 401."""
from fastapi.testclient import TestClient
from app.main import app
from tests.test_v07_integrations import PWD, setup, login


def test_anonymous_requests_reach_login_without_json_page():
    engine, _session = setup()
    try:
        with TestClient(app) as client:
            response = client.get('/', follow_redirects=False)
            assert response.status_code == 303
            assert response.headers['location'] == '/login'
            assert 'no-store' in response.headers['cache-control']
            assert 'Ingreso al sistema' in client.get('/').text
            assert client.get('/login').status_code == 200
            for path in ['/synop', '/historial', '/extremos', '/estacion',
                         '/personal', '/tablas', '/instrumentos', '/documentos/clave_synop_smn_2022.pdf']:
                denied = client.get(path, follow_redirects=False)
                assert denied.status_code == 303, (path, denied.text)
                assert denied.headers['location'] == '/login'
            denied = client.post('/estacion', data={'name':'Orán AERO','block_number':'87','station_number':'016', 'latitude':"23°09' S",'longitude':"64°19' O",'runway_elevation_m':'357','wind_method':'estimado','wind_iw':'3'}, follow_redirects=False)
            assert denied.status_code == 303
            assert denied.headers['location'] == '/login'
            api = client.get('/api/synop/draft', follow_redirects=False)
            assert api.status_code == 401
            assert api.json() == {'detail': 'Iniciá sesión para continuar'}
            assert client.get('/static/workspace_v03.js').status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_logged_in_home_works_and_expired_session_redirects():
    engine, SessionLocal = setup()
    try:
        with TestClient(app) as client:
            login(client, 'chief')
            assert client.get('/', follow_redirects=False).headers['location'] == '/synop'
            assert client.get('/synop', follow_redirects=False).status_code == 200
            client.cookies.clear()
            expired = client.get('/synop', follow_redirects=False)
            assert expired.status_code == 303
            assert expired.headers['location'] == '/login'
            assert client.get('/api/synop/draft').status_code == 401
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_login_error_shows_form_and_does_not_redirect_loop():
    engine, _session = setup()
    try:
        with TestClient(app) as client:
            invalid = client.post('/login', data={'username':'chief','password':'invalid'},
                                  follow_redirects=False)
            assert invalid.status_code == 401
            assert 'Usuario o contraseña incorrectos' in invalid.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_workspace_api_requests_handle_session_expiry():
    from pathlib import Path
    script = (Path(__file__).parents[1] / 'app/static/workspace_v03.js').read_text(encoding='utf-8')
    assert "response.status === 401" in script
    assert "window.location.assign('/login')" in script
    for endpoint in ('autoguardado', 'draft', 'nueva', 'finalizar'):
        assert f"synopRequest('/api/synop/{endpoint}'" in script


def test_disabled_account_is_rejected_even_with_valid_session_cookie():
    engine, SessionLocal = setup()
    try:
        with TestClient(app) as client:
            login(client, 'watcher')
            assert client.get('/', follow_redirects=False).headers['location'] == '/synop'
            from app.models import User
            with SessionLocal() as db:
                person = db.query(User).filter_by(username='watcher').one()
                person.active = False
                db.commit()
            blocked = client.get('/historial', follow_redirects=False)
            assert blocked.status_code == 303
            assert blocked.headers['location'] == '/login'
            assert client.get('/', follow_redirects=False).headers['location'] == '/login'
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_expired_session_cannot_save_synop():
    engine, _session = setup()
    try:
        with TestClient(app) as client:
            denied = client.post('/api/synop/autoguardado',
                                 json={'observation_id':1,'values':{}},
                                 follow_redirects=False)
            assert denied.status_code == 401
            assert denied.headers.get('location') is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
