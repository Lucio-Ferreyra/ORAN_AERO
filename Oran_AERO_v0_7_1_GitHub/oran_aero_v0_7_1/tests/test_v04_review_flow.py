"""Regression: saving TS and TH must make a calculated group 2 available in review."""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password


def test_synop_group2_through_autosave_and_review_endpoint():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def temporary_database():
        with sessions() as session:
            yield session

    with sessions() as session:
        session.add(User(username='test_group2', full_name='Prueba Grupo 2',
                         password_hash=hash_password('StrongTemporaryPassword123!'),
                         role='observador', active=True))
        session.commit()

    app.dependency_overrides[get_db] = temporary_database
    try:
        with TestClient(app) as client:
            response = client.post('/login', data={'username': 'test_group2',
                                                   'password': 'StrongTemporaryPassword123!'},
                                   follow_redirects=False)
            assert response.status_code == 303
            assert client.get('/synop').status_code == 200
            draft = client.get('/api/synop/draft').json()
            saved = client.post('/api/synop/autoguardado', json={
                'observation_id': draft['observation_id'],
                'values': {'ts': '32.5', 'th': '25.7', 'psychro_table': 'I', '_step': '1'},
            })
            assert saved.status_code == 200
            result = saved.json()
            assert result['groups']['2'] == '20229'
            assert result['derived']['dew_point_c'] == 22.9
            assert result['derived']['vapor_hpa'] == 27.8
            assert result['derived']['relative_humidity_pct'] == 57
            assert '20229' in client.get('/api/synop/draft').json()['message']
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_review_frontend_flushes_and_fetches_updated_message():
    """Guard against the v0.4 regression where the report showed stale state.message."""
    source = (Path(__file__).resolve().parents[1] / 'app' / 'static' / 'workspace_v03.js').read_text(encoding='utf-8')
    assert 'await save();' in source
    assert "await synopRequest('/api/synop/draft'" in source
    assert "$('finalize').addEventListener('click',openFinalReview)" in source
