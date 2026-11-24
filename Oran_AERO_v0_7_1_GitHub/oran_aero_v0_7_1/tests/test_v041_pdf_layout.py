from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password


def test_two_pdf_endpoints_and_full_width_workspace():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def temporary_database():
        with sessions() as db:
            yield db

    with sessions() as session:
        session.add(User(username='pdf_test', full_name='Prueba PDF',
                         password_hash=hash_password('TestStrongPassword123'),
                         role='observador', active=True))
        session.commit()

    app.dependency_overrides[get_db] = temporary_database
    try:
        with TestClient(app) as client:
            assert client.post('/login',data={'username':'pdf_test','password':'TestStrongPassword123'},follow_redirects=False).status_code==303
            page=client.get('/synop')
            assert page.status_code==200
            assert 'id="pdf-expand"' in page.text
            assert 'v04-pdf-buttons' in page.text
            assert '/static/workspace_v03.js?v=0740' in page.text
            for filename in ('clave_synop_smn_2022.pdf','libreta_smn_2022.pdf'):
                assert f'data-pdf="{filename}"' in page.text
                response=client.get('/documentos/'+filename)
                assert response.status_code==200
                assert response.headers['content-type'].startswith('application/pdf')
                assert response.content.startswith(b'%PDF-')
            assert client.get('/documentos/clave_metar_speci.pdf').status_code==404
            assert 'METAR' not in page.text
            css=(Path(__file__).resolve().parents[1]/'app/static/style.css').read_text(encoding='utf-8')
            js=(Path(__file__).resolve().parents[1]/'app/static/workspace_v03.js').read_text(encoding='utf-8')
            assert 'max-width:1920px' in css
            assert 'v04-pdf-fullscreen' in css
            assert "document.querySelectorAll('[data-pdf]')" in js
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
