from pathlib import Path
import sqlite3

import pytest

from publishing.phone_pack_service import PackService, Conflict, suggest_pack
from publishing.studio_assistant import AssistantIntent

ROOT=Path(__file__).resolve().parents[1]


def choices(**changes):
    return {'title':'Durable Space Pack','theme':'Space & Astronomy','reader_profile':'ages_6_8',
            'activity_count':3,'formats':['Word Search','Word Scramble','Sudoku'],'theme_balance':'Balanced'} | changes


@pytest.fixture
def service(tmp_path):
    value=PackService(ROOT,tmp_path/'catalog.db',tmp_path/'packs',start_worker=False)
    yield value
    value.close()


def test_version_conflicts_and_immutable_jobs(service):
    first=service.save(choices())
    job=service.enqueue(first['id'],first['revision'])
    assert service.enqueue(first['id'],first['revision']) == job
    second=service.save(choices(title='Changed'),first['id'],first['revision'])
    assert second['revision']==2
    assert service.job(job)['title']=='Durable Space Pack'
    with pytest.raises(Conflict): service.save(choices(title='Stale'),first['id'],1)
    with pytest.raises(Conflict): service.enqueue(first['id'],1)
    assert service.project(first['id'])['request']['title']=='Changed'


def test_queued_job_and_projects_survive_restart(service):
    project=service.save(choices())
    job=service.enqueue(project['id'],1)
    again=PackService(ROOT,service.database,service.output,start_worker=False)
    assert again.project(project['id'])['revision']==1
    assert again.job(job)['status']=='queued'
    again.update(job,status='running')
    restarted=PackService(ROOT,service.database,service.output,start_worker=False)
    assert restarted.job(job)['status']=='interrupted'
    retry=restarted.enqueue(project['id'],1)
    assert retry!=job
    again.close();restarted.close()


def test_real_build_preview_download_and_reopen(service):
    from pypdf import PdfReader
    from PIL import Image
    from io import BytesIO
    project=service.save(choices())
    job=service.enqueue(project['id'],1)
    assert service.process_next()
    assert service.job(job)['status']=='ready'
    assert len(PdfReader(service.artifact(job,'activities')).pages)==4
    assert service.artifact(job,'answers').read_bytes().startswith(b'%PDF')
    assert service.artifact(job,'zip').read_bytes().startswith(b'PK')
    with Image.open(BytesIO(service.preview(job,'activities',1))) as image:
        assert image.width>600 and image.height>800
    again=PackService(ROOT,service.database,service.output,start_worker=False)
    assert again.job(job)['status']=='ready'
    assert again.enqueue(project['id'],1)==job
    with pytest.raises(ValueError): again.preview(job,'answers',24)
    with pytest.raises(ValueError): again.artifact(job,'../../data/books.db')
    again.close()


def test_failed_build_is_not_ready_and_can_retry(service,monkeypatch):
    import publishing.phone_pack_service as module
    def fail(*args,**kwargs): raise ValueError('Not enough checked words.')
    monkeypatch.setattr(module,'prepare_pack_request',fail)
    project=service.save(choices())
    job=service.enqueue(project['id'],1)
    service.process_next()
    assert service.job(job)['status']=='failed'
    with pytest.raises(ValueError): service.artifact(job,'zip')
    assert service.enqueue(project['id'],1)!=job


def test_saved_folder_cannot_escape_output(service,tmp_path):
    project=service.save(choices());job=service.enqueue(project['id'],1)
    service.update(job,status='ready',folder=str(tmp_path))
    with pytest.raises(ValueError,match='location'): service.artifact(job,'answers')


def test_ai_uses_codex_once_and_proposals_still_validate():
    calls=[]
    def interpreter(provider,text):
        calls.append(provider)
        return AssistantIntent(action='create_pack',topic='Homesteading',activity_count=6,
            source_groups=('Gardening','Home and Household'))
    value=suggest_pack(ROOT,'Make a homesteading activity pack for a nine-year-old.',interpreter=interpreter)
    assert calls==['Codex']
    assert value['reader_profile']=='ages_9_12'
    assert value['source_groups']==['Gardening','Home and Household']


def test_ai_never_falls_back_and_unknown_groups_fail():
    calls=[]
    def unavailable(provider,text):
        calls.append(provider);raise RuntimeError('Unavailable')
    with pytest.raises(RuntimeError): suggest_pack(ROOT,'Make a pack',interpreter=unavailable)
    assert calls==['Codex']
    with pytest.raises(ValueError): suggest_pack(ROOT,'Make a pack',interpreter=lambda *args:AssistantIntent(action='create_pack',topic='Custom',source_groups=('Made Up Group',)))


def test_ai_cannot_route_books_into_pack_generation():
    with pytest.raises(ValueError,match='Books and cover'):
        suggest_pack(ROOT,'Make a book',interpreter=lambda *args:AssistantIntent(action='create_book',topic='Homesteading'))


def test_only_one_background_worker_for_a_catalog(tmp_path):
    first=PackService(ROOT,tmp_path/'one.db',tmp_path/'packs')
    try:
        with pytest.raises(ValueError,match='already running'):
            PackService(ROOT,tmp_path/'one.db',tmp_path/'packs')
    finally:
        first.close()
