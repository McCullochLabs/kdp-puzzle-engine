import pytest
from publishing.studio_chat_revisions import is_revision_request, _change

@pytest.mark.parametrize('text', ['Make this book large print','Make this book 6x9','Make this book use larger fonts','Increase the font size','Change the layout to landscape','Set the reader profile to seniors','Make it portrait','Make this book use bigger fonts and export it'])
def test_unsupported_design_edits_are_revisions_not_creation(text):
    assert is_revision_request(text)
    with pytest.raises(ValueError,match='not supported for an existing book'):
        _change(text)

@pytest.mark.parametrize('text',['Create a large print Word Search book','Make a 6x9 Sudoku book','Show title page designs','Do not change the font size'])
def test_new_creation_and_read_only_commands_not_intercepted(text):
    assert not is_revision_request(text)


def test_actual_offline_design_followup_never_creates_or_calls_provider(tmp_path,monkeypatch):
    import gc,tkinter as tk,time
    import word_search_creator as desktop
    monkeypatch.setattr(desktop,'load_app_preferences',lambda:{'assistant_provider':'Guide','local_ai_enabled':False})
    monkeypatch.setattr(desktop.WordSearchCreator,'APP_DIR',tmp_path,raising=False)
    monkeypatch.setattr('publishing.family_studio.LocalAssistant.models',lambda self:[])
    monkeypatch.setattr('publishing.family_studio.guide_request',lambda *a,**k:pytest.fail('Revision reached creation interpreter'))
    gc.collect()
    try:app=desktop.WordSearchCreator()
    except tk.TclError as exc:pytest.skip(str(exc))
    try:
        app.update();f=app.family_studio;f.context={'book_id':'owned','title':'Owned Sudoku','kind':'Sudoku'}
        f.prompt.set('Make this book large print');f.send();end=time.monotonic()+3
        while f.busy and time.monotonic()<end:app.update();time.sleep(.01)
        app.update()
        assert not f.busy and f.context['book_id']=='owned'
        assert 'not supported for an existing book' in f.chat.get('1.0','end')
        assert getattr(f,'_chat_creation_plan',None) is None
        assert not list((tmp_path/'out').glob('**/*.pdf'))
    finally:app.destroy();gc.collect()
