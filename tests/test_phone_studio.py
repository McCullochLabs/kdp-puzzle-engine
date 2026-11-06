from http.client import HTTPConnection
from threading import Thread

import pytest

from phone_studio import PrototypeHandler, configuration
from http.server import ThreadingHTTPServer
from publishing.activity_packs import FORMATS
from publishing.studio_reader_profiles import READER_PROFILES, BALANCES


@pytest.fixture
def server():
    with ThreadingHTTPServer(('127.0.0.1', 0), PrototypeHandler) as instance:
        thread = Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        yield instance
        instance.shutdown()
        thread.join(timeout=3)


def request(server, path, method='GET', headers=None, body=None):
    connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
    connection.request(method, path, headers=headers or {}, body=body)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response, data


def test_reuses_existing_choices_without_generation():
    value = configuration()
    assert value['readers'] == {key: profile['label'] for key, profile in READER_PROFILES.items()}
    assert value['balances'] == list(BALANCES)
    assert value['formats'] == list(FORMATS)
    assert value['generation_available'] is True
    assert 'ChatGPT/Codex' in value['ai_policy']


@pytest.mark.parametrize('path', ['/', '/app.js', '/style.css', '/api/config'])
def test_only_reviewed_assets_are_served(server, path):
    response, data = request(server, path)
    assert response.status == 200 and data
    assert response.getheader('Cache-Control') == 'no-store'
    assert "frame-ancestors 'none'" in response.getheader('Content-Security-Policy')


@pytest.mark.parametrize('path', ['/../requirements.txt', '/%2e%2e/data/books.db', '/data/books.db', '/api/generate', '/cover.py'])
def test_no_file_or_generation_access(server, path):
    response, _ = request(server, path)
    assert response.status == 404


def test_no_mutations_or_foreign_hosts(server):
    assert request(server, '/api/generate', method='POST')[0].status == 403
    assert request(server, '/', headers={'Host': 'untrusted.example'})[0].status == 403



def plan_headers(server):
    return {'Origin': f'http://127.0.0.1:{server.server_port}',
            'X-Studio-Request': 'plan', 'Content-Type': 'application/json'}


def test_checked_planning_endpoint(server, monkeypatch):
    import phone_studio
    import json
    monkeypatch.setattr(phone_studio, 'prepare_pack_request', lambda data, root: {'word_count': 16, 'generated': False})
    response, body = request(server, '/api/plan', 'POST', plan_headers(server), '{}')
    assert response.status == 200
    assert json.loads(body)['generated'] is False


@pytest.mark.parametrize('bad', [{'Origin':'https://untrusted.example'}, {'X-Studio-Request':''}, {'Origin':''}])
def test_cross_site_planning_rejected(server, bad):
    headers = plan_headers(server) | bad
    assert request(server, '/api/plan', 'POST', headers, '{}')[0].status == 403


def test_body_limits_and_bad_json(server):
    assert request(server, '/api/plan', 'POST', plan_headers(server), 'x' * 8193)[0].status == 413
    assert request(server, '/api/plan', 'POST', plan_headers(server), '{broken')[0].status == 422
    assert request(server, '/api/plan', 'POST', plan_headers(server) | {'Content-Type':'text/plain'}, '{}')[0].status == 415
    assert request(server, '/api/generate', 'POST', plan_headers(server), '{}')[0].status == 404


def test_concurrent_planning_has_clear_retry(server):
    import phone_studio
    with phone_studio.PLANNING_LOCK:
        assert request(server, '/api/plan', 'POST', plan_headers(server), '{}')[0].status == 409



def test_live_http_saved_pack_workflow(server,tmp_path):
    import json
    import phone_studio
    from publishing.phone_pack_service import PackService
    from pathlib import Path
    service=PackService(Path(phone_studio.ROOT),tmp_path/'catalog.db',tmp_path/'packs',start_worker=False)
    server.service=service
    choices={'title':'HTTP Space Pack','theme':'Space & Astronomy','reader_profile':'ages_6_8','activity_count':3,'formats':['Word Search','Word Scramble','Sudoku'],'theme_balance':'Balanced'}
    response,body=request(server,'/api/projects','POST',plan_headers(server),json.dumps({'request':choices,'id':None,'revision':None}))
    assert response.status==200
    project=json.loads(body)
    response,body=request(server,'/api/create','POST',plan_headers(server),json.dumps({'id':project['id'],'revision':1}))
    assert response.status==200
    job=json.loads(body)['job']
    service.process_next()
    assert json.loads(request(server,'/api/jobs/'+job)[1])['status']=='ready'
    response,data=request(server,'/api/files/'+job+'/activities')
    assert response.status==200 and data.startswith(b'%PDF')
    assert 'ACTIVITIES.pdf' in response.getheader('Content-Disposition')
    response,data=request(server,'/api/preview/'+job+'/answers/1')
    assert response.status==200 and data.startswith(b'\x89PNG')
    assert json.loads(request(server,'/api/projects')[1])['projects'][0]['id']==project['id']
    assert request(server,'/api/files/'+job+'/../../data/books.db')[0].status==404
    service.close()


@pytest.mark.parametrize('case,status',[('oversized',413),('content_type',415),('route',404),('busy',409)])
def test_delayed_rejected_body_returns_status_without_tcp_abort(server,monkeypatch,case,status):
    import time
    import phone_studio
    monkeypatch.setattr(phone_studio,'prepare_pack_request',lambda *a:pytest.fail('Rejected request reached planning'))
    payload=b'x'*8193 if case=='oversized' else b'{}'
    headers=plan_headers(server)|{'Content-Length':str(len(payload))}
    if case=='content_type':headers['Content-Type']='text/plain'
    path='/not-a-route' if case=='route' else '/api/plan'
    def delayed():
        half=len(payload)//2;yield payload[:half];time.sleep(.03);yield payload[half:]
    if case=='busy':phone_studio.PLANNING_LOCK.acquire()
    try:assert request(server,path,'POST',headers,delayed())[0].status==status
    finally:
        if case=='busy':phone_studio.PLANNING_LOCK.release()


def test_accepted_body_limit_remains_exact_and_rejections_do_not_plan(server,monkeypatch):
    import phone_studio
    calls=[]
    monkeypatch.setattr(phone_studio,'prepare_pack_request',lambda *a:(calls.append(True) or {'fixture':True}))
    assert request(server,'/api/plan','POST',plan_headers(server),'{}'+' '*8190)[0].status==200
    assert request(server,'/api/plan','POST',plan_headers(server),'{}'+' '*8191)[0].status==413
    assert calls==[True]


def test_rejected_body_drain_has_a_short_deadline(server):
    import time
    connection=HTTPConnection('127.0.0.1',server.server_port,timeout=3)
    try:
        connection.putrequest('POST','/api/plan')
        for key,value in (plan_headers(server)|{'Content-Length':'8193'}).items():connection.putheader(key,value)
        connection.endheaders();start=time.monotonic();response=connection.getresponse();response.read()
        assert response.status==413 and time.monotonic()-start<2
    finally:connection.close()


def test_rejected_drain_budget_shrinks_even_while_data_keeps_arriving(monkeypatch):
    from types import SimpleNamespace
    import phone_studio
    clock=[0.0];timeouts=[];reads=[]
    monkeypatch.setattr(phone_studio,'monotonic',lambda:clock[0])
    def one_byte(size):reads.append(size);clock[0]+=.1;return b'x'
    handler=phone_studio.PrototypeHandler.__new__(phone_studio.PrototypeHandler)
    handler.headers={'Content-Length':'8193'}
    handler.connection=SimpleNamespace(gettimeout=lambda:15,settimeout=timeouts.append)
    handler.rfile=SimpleNamespace(read1=one_byte)
    handler._discard_small_request_body(phone_studio.REJECTED_BODY_DRAIN_LIMIT)
    assert len(reads)==3 and timeouts[:-1]==pytest.approx([.25,.15,.05]) and timeouts[-1]==15
