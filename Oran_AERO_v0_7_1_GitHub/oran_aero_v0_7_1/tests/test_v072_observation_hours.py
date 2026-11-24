"""Pruebas de fecha/hora UTC y secuencia de observaciones SYNOP."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Observation, Report, Station, User
from app.observation_clock import next_synop_hour, utc_iso
from app.security import hash_password

PASSWORD = 'Password-Largo-2026!'


@pytest.fixture
def database():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        session.add(Station(id=1, name='Orán AERO', wind_iw='3', block_number='87', station_number='016',
                            latitude="23°09' S", longitude="64°19' O", runway_elevation_m=357))
        session.add_all([
            User(username='jefe', full_name='Jefe', role='jefe_estacion',
                 active=True, password_hash=hash_password(PASSWORD)),
            User(username='observador', full_name='Observador', role='observador',
                 active=True, password_hash=hash_password(PASSWORD)),
        ])
        session.commit()
    def session_dependency():
        with session_factory() as session:
            yield session
    app.dependency_overrides[get_db] = session_dependency
    try:
        yield session_factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def add_confirmed(session, moment, *, source_report_id=None):
    obs = Observation(station_id=1, observer_id=1, observation_time_utc=moment,
                      status='finalizado', source_report_id=source_report_id, values={})
    session.add(obs)
    session.flush()
    report = Report(observation_id=obs.id, report_type='SYNOP', status='finalizado',
                    message='AAXX', values_snapshot={}, derived_snapshot={})
    session.add(report)
    session.flush()
    return report


def login(client, name='jefe'):
    assert client.post('/login', data={'username': name, 'password': PASSWORD},
                       follow_redirects=False).status_code == 303


def test_first_observation_uses_real_utc_and_nearest_hour(database):
    with database() as session:
        assert next_synop_hour(session, 1, now_utc=datetime(2026, 11, 22, 18, 37, tzinfo=timezone.utc)) == datetime(2026, 11, 22, 19)
        assert next_synop_hour(session, 1, now_utc=datetime(2026, 11, 22, 23, 42, tzinfo=timezone.utc)) == datetime(2026, 11, 23, 0)
        assert utc_iso(datetime(2026, 11, 22, 19)) == '2026-11-22T19:00:00Z'
        assert utc_iso(datetime(2026, 11, 22, 16, tzinfo=timezone(-__import__('datetime').timedelta(hours=3)))) == '2026-11-22T19:00:00Z'


@pytest.mark.parametrize('last_hour,expected', [
    (datetime(2026, 11, 22, 3), datetime(2026, 11, 22, 4)),
    (datetime(2026, 11, 22, 23), datetime(2026, 11, 23, 0)),
    (datetime(2026, 11, 30, 23), datetime(2026, 12, 1, 0)),
    (datetime(2026, 12, 31, 23), datetime(2027, 1, 1, 0)),
    (datetime(2028, 2, 28, 23), datetime(2028, 2, 29, 0)),
])
def test_next_hour_rollover(database, last_hour, expected):
    with database() as session:
        add_confirmed(session, last_hour)
        session.commit()
        assert next_synop_hour(session, 1, now_utc=datetime(2030, 1, 1, tzinfo=timezone.utc)) == expected


def test_new_after_saved_report_keeps_sequence_and_utc_in_client(database):
    with database() as session:
        add_confirmed(session, datetime(2026, 11, 22, 3))
        session.commit()

    with TestClient(app) as client:
        login(client)
        assert client.get('/synop').status_code == 200
        initial = client.get('/api/synop/draft').json()
        assert initial['time_utc'] == '2026-11-22T04:00:00Z'
        assert initial['section0'].startswith('AAXX 22043 ')

        # Fecha/hora histórica inmutable: nueva observación no permite suplantarla.
        refused = client.post('/api/synop/nueva', json={
            'discard_confirmed': True, 'observation_time_utc': '2026-11-21T00:00:00Z'})
        assert refused.status_code == 422

        # Descartar un borrador no genera la siguiente hora (solo guardarlo).
        again = client.post('/api/synop/nueva', json={'discard_confirmed': True})
        assert again.status_code == 200
        draft = client.get('/api/synop/draft').json()
        assert draft['time_utc'] == '2026-11-22T04:00:00Z'

        from tests.test_v07_integrations import VALID
        ok = client.post('/api/synop/autoguardado', json={
            'observation_id': draft['observation_id'], 'values': VALID})
        assert ok.status_code == 200
        completed = client.post('/api/synop/finalizar', json={
            'observation_id': draft['observation_id'], 'confirmed': True})
        assert completed.status_code == 200, completed.text

        # La siguiente observación sale 05, sin depender de la hora del equipo.
        assert client.get('/synop').status_code == 200
        following = client.get('/api/synop/draft').json()
        assert following['section0'].startswith('AAXX 22053 ')
        assert following['time_utc'] == '2026-11-22T05:00:00Z'
        assert following['observation_id'] != draft['observation_id']

        # Corregir la observación 04 preserva 04, y no corre el reloj a 06.
        r = client.post(f"/reportes/{completed.json()['report_id']}/corregir", follow_redirects=False)
        assert r.status_code == 303
        fix = client.get('/api/synop/draft').json()
        assert fix['time_utc'] == '2026-11-22T04:00:00Z'
        assert fix['source_report_id'] == completed.json()['report_id']
        corrected = client.post('/api/synop/finalizar', json={
            'observation_id': fix['observation_id'], 'confirmed': True})
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()['version'] == 2
        assert client.get('/synop').status_code == 200
        assert client.get('/api/synop/draft').json()['time_utc'] == '2026-11-22T05:00:00Z'


def test_duplicate_same_station_hour_refused_at_finalization(database):
    from tests.test_v07_integrations import VALID
    with database() as session:
        add_confirmed(session, datetime(2026, 11, 22, 3))
        obs = Observation(station_id=1, observer_id=1,
                          observation_time_utc=datetime(2026, 11, 22, 3),
                          status='borrador_autoguardado', values=VALID)
        session.add(obs)
        session.commit()
        duplicate_id = obs.id
    with TestClient(app) as client:
        login(client)
        response = client.post('/api/synop/finalizar', json={
            'observation_id': duplicate_id, 'confirmed': True})
        assert response.status_code == 409, response.text
        assert 'Ya existe' in response.json()['detail']


def test_stale_draft_keeps_its_date_until_observer_discards_it(database):
    with database() as session:
        add_confirmed(session, datetime(2026, 11, 22, 3))
        stale = Observation(station_id=1, observer_id=1,
                            observation_time_utc=datetime(2026, 11, 21, 0),
                            status='borrador_autoguardado', values={})
        session.add(stale)
        session.commit()
        stale_id = stale.id
    with TestClient(app) as client:
        login(client)
        assert client.get('/synop').status_code == 200
        resumed = client.get('/api/synop/draft').json()
        assert resumed['observation_id'] == stale_id
        assert resumed['time_utc'] == '2026-11-21T00:00:00Z'
        assert resumed['stale_draft'] is True
        assert resumed['proposed_next_time_utc'] == '2026-11-22T04:00:00Z'
        assert client.post('/api/synop/nueva', json={'discard_confirmed': True}).status_code == 200
        new_draft = client.get('/api/synop/draft').json()
        assert new_draft['time_utc'] == '2026-11-22T04:00:00Z'
        assert new_draft['stale_draft'] is False
