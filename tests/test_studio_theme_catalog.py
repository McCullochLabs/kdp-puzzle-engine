import json,importlib
from pathlib import Path
from publishing.studio_theme_catalog import saved_theme_catalog,theme_catalog_text


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data),encoding='utf-8');return path


def test_exact_aliases_and_legitimate_variants(tmp_path):
    data={'title':'Space','author':'Owner','approved':True,'puzzles':[{'words':['STAR','MOON']}]}
    first=write(tmp_path/'Space.json',data)
    second=write(tmp_path/'legacy/SPACE copy.json',dict(reversed(list(data.items()))))
    variant=write(tmp_path/'Space revised.json',{**data,'puzzles':[{'words':['STAR','VENUS']}]})
    metadata_variant=write(tmp_path/'Different approval.json',{**data,'approved':False})
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    rows=saved_theme_catalog(tmp_path)
    assert len(rows)==3
    exact=next(row for row in rows if len(row['aliases'])==2)
    assert set(exact['aliases'])=={first,second}
    assert len({row['theme_id'] for row in rows})==3
    assert '1 groups, 1 extra source copies' in theme_catalog_text(rows,True)
    for _ in range(3):assert saved_theme_catalog(tmp_path)==rows
    import publishing.studio_theme_catalog as catalog
    assert importlib.reload(catalog).saved_theme_catalog(tmp_path)==rows
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    # Adding another identical import extends aliases, not the visible catalog.
    write(tmp_path/'imported/space.json',data)
    again=catalog.saved_theme_catalog(tmp_path)
    assert len(again)==3 and next(row for row in again if row['theme_id']==exact['theme_id'])['theme_id']==exact['theme_id']


def test_excluded_draft_invalid_and_nonobject(tmp_path):
    good={'title':'A','puzzles':[]}
    write(tmp_path/'good.json',good)
    write(tmp_path/'_Archive/copy.json',good)
    write(tmp_path/'draft.json',{**good,'draft':True})
    write(tmp_path/'nonobject.json',[])
    write(tmp_path/'nonpuzzle.json',{'title':'A'})
    (tmp_path/'bad.json').write_bytes(b'\xff')
    assert len(saved_theme_catalog(tmp_path,[tmp_path/'_Archive']))==1


def test_picker_uses_same_catalog(tmp_path,monkeypatch):
    import word_search_creator as studio
    write(tmp_path/'a.json',{'title':'A','puzzles':[]})
    write(tmp_path/'copies/b.json',{'title':'A','puzzles':[]})
    monkeypatch.setattr(studio,'THEMES_DIR',tmp_path)
    assert studio.saved_theme_files()==[row['path'] for row in saved_theme_catalog(tmp_path)]
    assert len(studio.saved_theme_files())==1


def test_three_same_title_stem_variants_cannot_replace_display_entry(tmp_path):
    from publishing.studio_theme_catalog import unique_theme_label
    used={}
    for directory in ('one','two','three'):
        path=tmp_path/directory/'same.json'
        label=unique_theme_label('Same book','Same',path,tmp_path,used)
        used[label]=path
    assert len(used)==3
    assert set(used.values())=={tmp_path/name/'same.json' for name in ('one','two','three')}
