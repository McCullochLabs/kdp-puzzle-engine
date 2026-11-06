import hashlib
from PIL import Image,ImageDraw
from background_generation.index import BackgroundAssetIndex


def test_finished_front_can_be_verified_but_not_selected_as_new_background(tmp_path,monkeypatch):
 import background_generation.index as module
 monkeypatch.setattr(module,'ROOT',tmp_path)
 path=tmp_path/'front.png';Image.new('RGB',(1200,1600),'black').save(path)
 index=BackgroundAssetIndex(tmp_path/'assets.json')
 row={'asset_id':'front','path':'front.png','name':'After Hours adult cocktails','topics':['afterhours','cocktails','naughty'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'project_generated':True,'classification':'APPROVED_PROJECT_GENERATED','approval_state':'approved','production_approved':True,'asset_role':'finished_front_cover','provenance':{'provider':'SladePuzzleCo project generation'}}
 index.save({'assets':[row]});monkeypatch.setattr(index,'ensure_provenance_audited',lambda:None)
 assert index.eligibility(path)[0]
 assert not index.production_choices({'topic':'afterhours cocktails naughty'})


def test_after_hours_wrap_uses_shared_matching_palette_and_no_false_claims():
 import cover,wrap_cover
 assert wrap_cover.PALETTES['after-hours-luxury']['bg']==cover.PALETTES['after-hours-luxury']['bg']==(16,18,17)
 image=Image.new('RGB',(2700,3400));actual=ImageDraw.Draw(image);captured=[]
 class Draw:
  def rectangle(self,*a,**k):return actual.rectangle(*a,**k)
  def textlength(self,*a,**k):return actual.textlength(*a,**k)
  def text(self,xy,text,**kwargs):captured.append(text);return actual.text(xy,text,**kwargs)
 wrap_cover.after_hours_luxury_back(image,Draw(),None,38,2588,38,3375)
 text=' '.join(captured)
 assert '100' in text and '1,200' in text and 'ADULTS 18+' in text
 assert not any(term in text.upper() for term in ('LARGE-PRINT','TEENS','PUZZLEBOOKSEARCHFUN'))
