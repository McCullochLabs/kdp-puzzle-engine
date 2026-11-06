import base64,json,time,threading
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError
from PIL import Image,ImageDraw
import pytest
from background_generation.providers import GeminiImageCredentials,GeminiImageProvider,ProviderNotConfigured,ProviderError,ProviderRateLimitedError


def png():
    b=BytesIO();im=Image.new('RGB',(1200,1600),'#302050');d=ImageDraw.Draw(im);d.ellipse((100,100,1000,1450),fill='#d02585');im.save(b,format='PNG');return b.getvalue()


def response(payload):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,size=-1):return json.dumps(payload).encode()
    return Response()


def image_payload():return {'status':'completed','steps':[{'type':'model_output','content':[{'type':'image','mime_type':'image/png','data':base64.b64encode(png()).decode()}]}]}


def test_shared_listing_key_does_not_reuse_text_model(monkeypatch):
    monkeypatch.setattr('background_generation.providers.load_secret',lambda name:{'api_key':'test-secret','model':'gemini-3.5-flash-lite'} if name=='GeminiListingAI' else None)
    credentials=GeminiImageCredentials.load()
    assert credentials.model=='gemini-nano-banana-2.1' and 'test-secret' not in repr(credentials)


def test_paid_permission_required_before_network(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Must not send a billable request')
    monkeypatch.setattr('urllib.request.urlopen',forbidden)
    with pytest.raises(ProviderNotConfigured,match='paid-only'):GeminiImageProvider(GeminiImageCredentials('test-key')).generate('Adult book background')


def test_actual_interactions_shape_and_completed_image(monkeypatch):
    requests=[]
    def call(request,**kwargs):requests.append(request);return response(image_payload())
    monkeypatch.setattr('urllib.request.urlopen',call)
    raw=GeminiImageProvider(GeminiImageCredentials('test-key'),allow_paid=True).generate('Adult cocktail and word-game cover; no text')
    assert Image.open(BytesIO(raw)).size==(1200,1600)
    body=json.loads(requests[0].data);assert requests[0].full_url.endswith('/v1beta/interactions')
    assert body['model']=='gemini-nano-banana-2.1' and body['response_format']['image_size']=='4K'
    assert body['store'] is False and len(requests)==1


@pytest.mark.parametrize('payload',[[],{'status':'incomplete','steps':[]},{'status':'completed','steps':[{'type':'thought','summary':[{'type':'image','data':'ignored'}]}]}])
def test_malformed_partial_and_thought_only_images_are_rejected(monkeypatch,payload):
    monkeypatch.setattr('urllib.request.urlopen',lambda *args,**kwargs:response(payload))
    with pytest.raises(ProviderError):GeminiImageProvider(GeminiImageCredentials('test-key'),allow_paid=True).generate('Test')


def test_quota_error_never_retries_or_falls_back(monkeypatch):
    calls=[]
    def quota(*args,**kwargs):calls.append(1);raise HTTPError('https://example.test',429,'quota',None,None)
    monkeypatch.setattr('urllib.request.urlopen',quota)
    with pytest.raises(ProviderRateLimitedError):GeminiImageProvider(GeminiImageCredentials('test-key'),allow_paid=True).generate('Test')
    assert calls==[1]


def test_gemini_queue_keeps_provider_and_requires_individual_art_approval(tmp_path,monkeypatch):
    import background_generation.service as module
    from background_generation.index import BackgroundAssetIndex
    monkeypatch.setattr(module,'ROOT',tmp_path);monkeypatch.setattr(module,'QUEUE_FILE',tmp_path/'queue.json');monkeypatch.setattr(module,'GENERATED_DIR',tmp_path/'generated')
    monkeypatch.setattr('background_generation.index.ROOT',tmp_path)
    index=BackgroundAssetIndex(tmp_path/'assets.json');index.save({'assets':[]})
    class FakeGemini:
        name='gemini_api';provenance_name='Gemini API';credentials=SimpleNamespace(model='gemini-nano-banana-2.1')
        def generate(self,*args,**kwargs):return png()
    service=module.BackgroundGenerationService(index,FakeGemini());service.enqueue(topic='After-hours swearing and cocktails',adult=True)
    cloud=SimpleNamespace(name='cloudflare_workers_ai',generate=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('Wrong provider')))
    assert module.BackgroundGenerationService(index,cloud).process_next().status=='PAUSED'
    result=service.process_next();assert result.status=='AWAITING_REVIEW'
    assert result.asset['provenance']['provider']=='Gemini API' and result.asset['audience']=='adult'
    assert not index.production_selectable(result.asset)
    reviewed=service.review(result.asset['asset_id'],'approved')
    assert reviewed.asset['classification']=='APPROVED_GEMINI_GENERATED'
    assert index.production_selectable(reviewed.asset)


def test_adult_theme_does_not_match_nostalgia_from_audience_tag():
    from background_generation.index import BackgroundAssetIndex
    brief=BackgroundAssetIndex.cover_brief({'title':'Naughty Adult Word Search','topic':'Adult profanity and cocktails'})
    nostalgia={'name':'Childhood memories','topics':['adult','nostalgia','1950s'],'audience':'adult'}
    nightlife={'name':'After hours','topics':['naughty','cocktails','nightlife'],'audience':'adult'}
    assert BackgroundAssetIndex._topic_score(nostalgia,brief)<12
    assert BackgroundAssetIndex._topic_score(nightlife,brief)>12


def test_real_dialog_gemini_without_paid_permission_pauses_before_network(monkeypatch,tmp_path):
    import tkinter as tk
    import word_search_creator as gui
    import background_generation.service as service
    try:
        root=tk.Tk()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    root.withdraw()
    root.status=tk.StringVar(root)
    class EmptyIndex:
        def assets(self): return []
        def audit_legacy_library(self): return None
        def approved_choices(self,*args,**kwargs): return []
    monkeypatch.setattr(gui,'BackgroundAssetIndex',EmptyIndex)
    monkeypatch.setattr(service,'BackgroundAssetIndex',EmptyIndex)
    monkeypatch.setattr(service,'ROOT',tmp_path)
    monkeypatch.setattr(service,'QUEUE_FILE',tmp_path/'queue.json')
    monkeypatch.setattr(service,'GENERATED_DIR',tmp_path/'generated')
    monkeypatch.setattr(GeminiImageCredentials,'load',classmethod(lambda cls:cls('test-key')))
    def forbidden(*args,**kwargs): raise AssertionError('No paid request authorized')
    monkeypatch.setattr('urllib.request.urlopen',forbidden)
    notices=[]
    monkeypatch.setattr(gui.messagebox,'showinfo',lambda title,message,**kwargs:notices.append((title,message)))
    dialog=None
    try:
        dialog=gui.BackgroundGeneratorDialog(root,topic='After hours adult cocktails',palette='plum')
        assert dialog.adult_topic.get() and not dialog.paid_image_permission.get()
        dialog.image_provider.set('Gemini images')
        dialog.queue()
        queue=json.loads((tmp_path/'queue.json').read_text(encoding='utf-8'))
        assert 'gemini_api' in str(queue)
        dialog.generate()
        deadline=time.monotonic()+5
        while dialog._image_busy and time.monotonic()<deadline:
            root.update()
            time.sleep(.01)
        assert not dialog._image_busy
        assert notices and 'paid-only' in notices[-1][1]
        assert not dialog.paid_image_permission.get()
    finally:
        if dialog is not None: dialog.destroy()
        root.destroy()
