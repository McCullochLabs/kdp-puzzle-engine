"""Common requests route to real selected-book checks, including offline mode."""
import pytest
from publishing.studio_assistant import guide_request

@pytest.mark.parametrize('text',['Show the quality report','Give me the preflight results','Display QA results','Show me what needs fixing'])
def test_quality_report_aliases_use_existing_selected_book_check(text):
    assert guide_request(text,context={'book_id':'saved-id','title':'Saved book'}).action=='check_book'
    assert guide_request(text).action!='check_book'

@pytest.mark.parametrize('text',['Upload the quality report','Delete the QA report','Publish the preflight results'])
def test_quality_aliases_do_not_override_restricted_actions(text):
    assert guide_request(text,context={'book_id':'saved-id'}).action=='help'
