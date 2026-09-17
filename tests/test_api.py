import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import api
from anonymizer import TextAnonymizer
from test_anonymizer import FakeNER


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('ANONYMIZER_API_KEY', raising=False)
    monkeypatch.setattr(api, 'TextAnonymizer', lambda: TextAnonymizer(FakeNER(('Ali',))))
    with TestClient(api.app) as client:
        yield client


def test_safe_default_and_explicit_review(client):
    payload = {'text': 'Ali ali@example.com'}
    response = client.post('/anonymize', json=payload)
    assert response.status_code == 200
    data = response.json()
    assert 'Ali' not in response.text and 'ali@example.com' not in response.text
    assert all('text' not in e for e in data['entities'])
    assert data['counts_by_label'] == {'NAME': 1, 'EMAIL': 1}
    assert response.headers['cache-control'] == 'no-store'
    review = client.post('/anonymize', json={**payload, 'include_originals': True}).json()
    assert review['entities'][0]['text'] == 'Ali'


@pytest.mark.parametrize('payload', [
    {'text': 'SECRET', 'threshold': 2}, {'text': 'SECRET', 'profile': 'unknown'},
    {'text': 'SECRET', 'manual_spans': [{'start': 1, 'end': 10}]},
    {'text': 'SECRET', 'manual_spans': [{'start': 4, 'end': 2}]},
    {'text': 'SECRET', 'manual_spans': [{'start': True, 'end': 2}]},
    {'text': 'SECRET' * 20000}, {'text': '   '},
])
def test_validation_does_not_echo_input(client, payload):
    response = client.post('/anonymize', json=payload)
    assert response.status_code == 422
    assert 'SECRET' not in response.text


def test_authentication(client, monkeypatch):
    monkeypatch.setenv('ANONYMIZER_API_KEY', 'test-only-key')
    assert client.get('/health').json()['authentication_required']
    assert client.post('/anonymize', json={'text': 'Ali'}).status_code == 401
    assert client.post('/anonymize', headers={'X-API-Key': 'wrong'}, json={'text': 'Ali'}).status_code == 401
    assert client.post('/anonymize', headers={'X-API-Key': 'test-only-key'}, json={'text': 'Ali'}).status_code == 200


def test_body_limit_including_stream(client):
    assert client.post('/anonymize', content=b'a' * (api.MAX_BODY_BYTES + 1)).status_code == 413
    response = client.post('/anonymize', content=iter([b'a' * 600000, b'b' * 600000]))
    assert response.status_code == 413


def test_manual_span(client):
    result = client.post('/anonymize', json={'text': '😀 sır', 'manual_spans': [{'start': 2, 'end': 5}]}).json()
    assert result['masked_text'] == '😀 [MANUAL_1]'


def test_failure_does_not_return_partial_text(client, monkeypatch):
    def fail(*args):
        raise RuntimeError('SECRET original data')
    monkeypatch.setattr(api.app.state.anonymizer, 'anonymize', fail)
    response = client.post('/anonymize', json={'text': 'Ali'})
    assert response.status_code == 503 and 'SECRET' not in response.text


def test_busy_service_and_responsive_health(client, monkeypatch):
    started, finish = threading.Event(), threading.Event()
    original = api.app.state.anonymizer.anonymize

    def slow(*args):
        started.set()
        assert finish.wait(5)
        return original(*args)

    monkeypatch.setattr(api.app.state.anonymizer, 'anonymize', slow)
    with ThreadPoolExecutor() as pool:
        first = pool.submit(client.post, '/anonymize', json={'text': 'Ali'})
        try:
            assert started.wait(5)
            assert client.get('/health').status_code == 200
            busy = client.post('/anonymize', json={'text': 'Ali'})
            assert busy.status_code == 429 and busy.headers['retry-after'] == '2'
        finally:
            finish.set()
        assert first.result().status_code == 200


def test_static_and_cors(client):
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
    response = client.options('/anonymize', headers={'Origin': 'https://example.com', 'Access-Control-Request-Method': 'POST'})
    assert 'access-control-allow-origin' not in response.headers


def test_not_ready(client, monkeypatch):
    monkeypatch.setattr(api.app.state, 'anonymizer', None)
    assert client.get('/health').status_code == 503
    assert client.post('/anonymize', json={'text': 'Ali'}).status_code == 503
