"""Read-only PDF stroke/font screen. No production files are written."""
from __future__ import annotations
from pathlib import Path
import collections, copy, hashlib, json, math, re, sys
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, DecodedStreamObject, NameObject

IDENTITY=(1.,0.,0.,1.,0.,0.)
def compose(a,b):
    # Affine columns: CTM(a) after the new local transform(b).
    aa,ab,ac,ad,ae,af=a;ba,bb,bc,bd,be,bf=b
    return (aa*ba+ac*bb,ab*ba+ad*bb,aa*bc+ac*bd,ab*bc+ad*bd,aa*be+ac*bf+ae,ab*be+ad*bf+af)

def scales(m):
    a,b,c,d,_,_=m
    trace=a*a+b*b+c*c+d*d;det=(a*d-b*c)**2
    delta=math.sqrt(max(0.,trace*trace-4*det))
    return math.sqrt(max(0.,(trace-delta)/2)),math.sqrt(max(0.,(trace+delta)/2))

class Screen:
    def __init__(self,reader):
        self.reader=reader;self.strokes=[];self.unsupported=[];self.font_samples=[]
    def walk(self,stream,resources,page,state=None,label='page',active=()):
        state=copy.deepcopy(state or {'ctm':IDENTITY,'width':1.,'alpha':1.,'fill_alpha':1.,'font_size':12.,'text_mode':0,'text_matrix':IDENTITY})
        stack=[];path=False;path_transform=None;segments=False
        for index,(args,op) in enumerate(ContentStream(stream,self.reader).operations):
            if op==b'q':stack.append(copy.deepcopy(state))
            elif op==b'Q':
                if stack:state=stack.pop()
                else:self.unsupported.append({'page':page,'reason':'unbalanced_Q','stream':label})
            elif op==b'cm':
                state['ctm']=compose(state['ctm'],tuple(float(x) for x in args))
                if path:self.unsupported.append({'page':page,'reason':'CTM_changed_during_path','stream':label})
            elif op==b'w':state['width']=float(args[0])
            elif op==b'gs':
                ext=resources.get('/ExtGState',{}).get_object() if resources.get('/ExtGState') else {}
                gs=ext.get(args[0]);gs=gs.get_object() if gs else {}
                if '/LW' in gs:state['width']=float(gs['/LW'])
                if '/CA' in gs:state['alpha']=float(gs['/CA'])
                if '/ca' in gs:state['fill_alpha']=float(gs['/ca'])
                if '/SMask' in gs and gs['/SMask']!='/None':self.unsupported.append({'page':page,'reason':'softmask_visibility_not_resolved','stream':label})
            elif op==b'BT':state['text_matrix']=IDENTITY
            elif op==b'Tf':state['font_size']=float(args[1])
            elif op==b'Tm':state['text_matrix']=tuple(float(x) for x in args)
            elif op==b'Tr':state['text_mode']=int(args[0])
            elif op in (b'Tj',b'TJ',b"'",b'"'):
                # Td/T*/TJ advances affect position, not the vertical font vector.
                # Inherit the parent CTM through Form XObjects instead of using
                # pypdf's text visitor, whose nested-form CTM is not composed.
                values=args[0] if op==b'TJ' else [args[-1]]
                text=''.join(str(value) for value in values if isinstance(value,(str,bytes)) and str(value).strip())
                mode=state['text_mode']
                visible=(mode in (0,2,4,6) and state['fill_alpha']>0) or (mode in (1,2,5,6) and state['alpha']>0)
                if text and visible:
                    matrix=compose(state['ctm'],state['text_matrix'])
                    height=abs(state['font_size'])*math.hypot(matrix[2],matrix[3])
                    self.font_samples.append({'page':page,'stream':label,'effective_font_height_pt':round(height,7),'declared_font_pt':state['font_size'],'text_sample':text[:100],'nonuniform':abs(scales(matrix)[0]-scales(matrix)[1])>1e-7})
            elif op in (b'm',b'l',b'c',b'v',b'y',b're'):
                if not path:path_transform=state['ctm']
                path=True
                if op!=b'm':segments=True
            elif op in (b'S',b's',b'B',b'B*',b'b',b'b*'):
                if path and segments and state['alpha']>0:
                    lo,hi=scales(state['ctm']);raw=abs(state['width']);low=raw*lo;high=raw*hi
                    uniform=abs(lo-hi)<1e-7
                    status='BELOW_MINIMUM' if high<.75-1e-7 else 'ORIENTATION_DEPENDENT' if low<.75-1e-7 else 'AT_OR_ABOVE_MINIMUM'
                    self.strokes.append({'page':page,'stream':label,'operation_index':index,'paint':op.decode(),'raw_width':raw,'effective_width_lower_pt':round(low,7),'effective_width_upper_pt':round(high,7),'uniform_transform':uniform,'status':status,'stroke_alpha':state['alpha'],'path_CTM_unchanged':path_transform==state['ctm']})
                path=False;path_transform=None;segments=False
            elif op in (b'n',b'f',b'F',b'f*'):path=False;path_transform=None;segments=False;segments=False
            elif op==b'Do':
                xobjects=resources.get('/XObject',{});xobjects=xobjects.get_object() if xobjects else {}
                obj=xobjects.get(args[0]);obj=obj.get_object() if obj else None
                if obj is not None and obj.get('/Subtype')=='/Form':
                    identity=id(obj)
                    if identity in active:
                        self.unsupported.append({'page':page,'reason':'recursive_form','stream':label});continue
                    nested=copy.deepcopy(state);nested['ctm']=compose(state['ctm'],tuple(float(x) for x in obj.get('/Matrix',IDENTITY)))
                    self.walk(obj,obj.get('/Resources',resources).get_object(),page,nested,label+'/'+str(args[0]),active+(identity,))
        if stack:self.unsupported.append({'page':page,'reason':'unbalanced_q','stream':label})

def selftest():
    writer=PdfWriter();page=writer.add_blank_page(100,100)
    commands=b'.1 w 1 w 0 0 m 20 20 l S q .5 w 2 0 0 2 0 0 cm 0 0 m 20 20 l S Q q .5 w 0 1 -1 0 0 0 cm 0 0 m 20 20 l S Q q .5 w 2 0 0 1 0 0 cm 0 0 m 20 20 l S Q .1 w'
    content=DecodedStreamObject();content.set_data(commands);page[NameObject('/Contents')]=content
    screen=Screen(writer);screen.walk(content,{},1)
    assert len(screen.strokes)==4
    assert [x['status'] for x in screen.strokes]==['AT_OR_ABOVE_MINIMUM','AT_OR_ABOVE_MINIMUM','BELOW_MINIMUM','ORIENTATION_DEPENDENT']
    assert screen.strokes[1]['effective_width_lower_pt']==1.
    assert not screen.unsupported


def scan_pdf(path):
    """Screen painted strokes/text with composed form and text transforms.

    Position-only text advances are irrelevant to font height. Type3 glyph
    internals, clipping visibility and raster line thickness remain outside
    this screen; unsupported graphics cases are explicitly returned.
    """
    reader=PdfReader(path);screen=Screen(reader)
    for number,page in enumerate(reader.pages,1):
        screen.walk(page.get_contents(),page.get('/Resources',{}).get_object(),number)
    samples=[row for row in screen.font_samples if row['effective_font_height_pt']>0]
    return {"pages":len(reader.pages),"strokes":screen.strokes,"unsupported":screen.unsupported,
            "font_min_effective_height_pt":min((row['effective_font_height_pt'] for row in samples),default=None),
            "font_below_7pt_samples":[row for row in samples if row['effective_font_height_pt']<7.-1e-7],
            "font_extraction_errors":[],"nonuniform_font_samples_count":sum(row['nonuniform'] for row in samples)}
