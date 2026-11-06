import pytest
from types import SimpleNamespace
from publishing.studio_project_queries import project_query, title_page_designs_text
from publishing.family_studio import FamilyStudio
from publishing.studio_chat_revisions import _change
from publishing.title_pages import STYLE_LABELS

@pytest.mark.parametrize('text', ['Show title page designs', 'List available title-page presets', 'Show me supported title page styles?'])
def test_design_query(text):
    assert project_query(text) == 'title_page_designs'

@pytest.mark.parametrize('text', ['Do not show title page designs', 'Show title page designs and accept revision', 'Change title page designs', 'Show title page designs and publish'])
def test_compound_or_mutating_request_is_not_read_query(text):
    assert project_query(text) is None

def test_renderer_labels_and_example_stay_valid():
    text=title_page_designs_text()
    for label in ('Automatic', *STYLE_LABELS.values()):
        assert label in text
        assert _change('Change the title page design to "'+label+'"') == ('title_page_style',label)
    assert 'not provided' in text and 'approval checks' in text

def test_no_project_or_worker_needed_and_pending_context_untouched():
    context={'book_id':'owned','pending_semantic_revision':{'revision_id':'pending'}}
    messages=[]
    fake=SimpleNamespace(context=context,_say=lambda *args:messages.append(args))
    assert FamilyStudio._handle_project_query(fake,'Show title page designs')
    assert fake.context is context and len(messages)==1
    assert 'Review the staged candidate' in messages[0][1]


@pytest.mark.parametrize('label', ['Automatic', *STYLE_LABELS.values()])
def test_exact_unquoted_title_page_presets(label):
    from publishing.studio_chat_revisions import is_revision_request
    request='Change the title-page style to '+label
    assert is_revision_request(request)
    assert _change(request)==('title_page_style',label)
    assert _change('Set title page design to “'+label+'”')==('title_page_style',label)

@pytest.mark.parametrize('value',['Unknown style','Automatic and export it','Automatic then accept revision','"Automatic','Automatic"','“Automatic"','Automatic; publish'])
def test_unquoted_presets_do_not_accept_extra_commands_or_malformed_quotes(value):
    with pytest.raises(ValueError,match='supported title page design'):
        _change('Change title page style to '+value)
