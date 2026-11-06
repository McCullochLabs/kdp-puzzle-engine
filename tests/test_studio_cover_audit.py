from pathlib import Path
import hashlib
import threading
import pytest
from PIL import Image
from publishing.studio_cover_audit import audit_cover, validate_audit, cover_evidence, audit_text


@pytest.fixture
def book(tmp_path):
    cover = tmp_path / 'front_cover.png'
    Image.new('RGB', (600, 800), 'navy').save(cover)
    return {'book_id': 'a', 'metadata': {'title': 'Garden days', 'theme': 'Gardening', 'files': {'front_cover': str(cover)}}}


def test_no_saved_cover_is_not_a_success():
    with pytest.raises(ValueError, match='no saved cover'): cover_evidence({'metadata': {}})


def test_local_text_model_does_not_claim_visual_review(book):
    class Never:
        def request(self, *a, **kw): pytest.fail('Text model cannot audit images')
    result = audit_cover(book, 'Ollama', reviewer=Never())
    assert result['visual'] is None and 'text-only' in result['note']
    assert 'unavailable' in result['checks'][0]


def test_visual_review_receives_rendered_cover_and_never_modifies_it(book):
    source = Path(book['metadata']['files']['front_cover']); before = hashlib.sha256(source.read_bytes()).hexdigest()
    class Reviewer:
        def request(self, prompt, schema, **kwargs):
            assert len(kwargs['images']) == 1
            assert Path(kwargs['images'][0]).is_file()
            assert str(source) not in prompt
            assert 'untrusted' not in prompt or 'instructions' in prompt
            return {'summary': 'The title is not visible in this image.', 'findings': [
                {'area': 'Title readability', 'priority': 'High', 'observation': 'A blank field occupies the front.', 'suggestion': 'Add the book title in the cover layout tools.'}]}
    result = audit_cover(book, 'Codex', reviewer=Reviewer())
    assert 'AI design suggestions' in audit_text(result)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert 'never' not in audit_text(result) or result['note']


@pytest.mark.parametrize('data', [{}, {'summary': 'x', 'findings': [], 'approve': True},
    {'summary': 'x', 'findings': [{'area': 'Layout', 'observation': 'x', 'suggestion': 'x', 'priority': 'Approved'}]}])
def test_malformed_reviews_are_rejected(data):
    with pytest.raises(ValueError): validate_audit(data)


def test_cancelled_cover_review_does_not_invoke_ai(book):
    from publishing.studio_codex import RequestCancelled
    cancel = threading.Event(); cancel.set()
    class Never:
        def request(self, *a, **kw): pytest.fail('Cancelled request')
    with pytest.raises(RequestCancelled): audit_cover(book, 'Codex', cancel, Never())



def test_cover_changed_during_review_is_reported_as_stale(book):
    path = Path(book['metadata']['files']['front_cover'])
    class Reviewer:
        def request(self, *args, **kwargs):
            Image.new('RGB', (600, 800), 'red').save(path)
            return {'summary': 'Old version', 'findings': []}
    with pytest.raises(ValueError, match='cover changed'):
        audit_cover(book, 'Codex', reviewer=Reviewer())
