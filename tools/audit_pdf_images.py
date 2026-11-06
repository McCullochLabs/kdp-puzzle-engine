"""Read-only effective embedded-raster DPI screening for preserved PDF interiors."""
from pathlib import Path
import json,math,sys
from pypdf import PdfReader
from pypdf.generic import ContentStream
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from publishing.pdf_print_screen import IDENTITY,compose
from publishing.package_layout import package_file

def images_in_pdf(path):
 reader=PdfReader(path);rows=[];unknown=[]
 def walk(stream,resources,page,ctm=IDENTITY,active=()):
  stack=[]
  for args,op in ContentStream(stream,reader).operations:
   if op==b'q':stack.append(ctm)
   elif op==b'Q':
    if stack:ctm=stack.pop()
    else:unknown.append({'page':page,'reason':'unbalanced_graphics_state'})
   elif op==b'cm':ctm=compose(ctm,tuple(float(x) for x in args))
   elif op==b'INLINE IMAGE':unknown.append({'page':page,'reason':'inline_image_not_measured'})
   elif op==b'Do':
    objects=resources.get('/XObject',{});objects=objects.get_object() if objects else {};obj=objects.get(args[0]);obj=obj.get_object() if obj else None
    if obj is None:continue
    if obj.get('/Subtype')=='/Image':
     x=math.hypot(ctm[0],ctm[1]);y=math.hypot(ctm[2],ctm[3]);width=int(obj['/Width']);height=int(obj['/Height'])
     if not x or not y:unknown.append({'page':page,'reason':'zero_image_transform'});continue
     dx=width*72/x;dy=height*72/y
     rows.append({'page':page,'name':str(args[0]),'pixels':[width,height],'placed_inches':[round(x/72,4),round(y/72,4)],'dpi_x':round(dx,2),'dpi_y':round(dy,2),'below_300dpi':min(dx,dy)<300-1e-6,'image_mask':bool(obj.get('/ImageMask',False))})
    elif obj.get('/Subtype')=='/Form':
     identity=id(obj)
     if identity in active:unknown.append({'page':page,'reason':'recursive_form'});continue
     nested=compose(ctm,tuple(float(x) for x in obj.get('/Matrix',IDENTITY)));walk(obj,obj.get('/Resources',resources).get_object(),page,nested,active+(identity,))
 for i,page in enumerate(reader.pages,1):walk(page.get_contents(),page.get('/Resources',{}).get_object(),i)
 return {'pages':len(reader.pages),'images':rows,'unresolved':unknown}

if __name__=='__main__':
 a=ROOT/'audits/system_20261101';books=[]
 for b in json.loads((a/'portfolio_current.json').read_text()):
  result=images_in_pdf(package_file(Path(b['folder']),'interior.pdf'));books.append({'family':b['family'],'folder':b['folder'],**result})
 output=a/'phase2/pdf_raster_screen.json';assert not output.exists();output.write_text(json.dumps({'minimum_dpi':300,'books':books,'limitations':['DPI is an embedded pixel/placed-size check, not proof of original image detail.','Inline images and unsupported transforms require separate review.','Cover image resolution and physical proof remain separate.']},indent=2),encoding='utf-8')
 print(json.dumps([{'family':b['family'],'image_placements':len(b['images']),'below_300dpi':sum(x['below_300dpi'] for x in b['images']),'unresolved':len(b['unresolved'])} for b in books],indent=2))
