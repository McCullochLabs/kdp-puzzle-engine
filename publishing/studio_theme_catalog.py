"""Read-only saved-theme identities; exact aliases retain every source file."""
import hashlib,json
from pathlib import Path


def saved_theme_catalog(directory, excluded=()):
    directory=Path(directory)
    excluded=tuple(Path(path) for path in excluded)
    groups={}
    for path in sorted(directory.rglob('*.json'),key=lambda p:(str(p.parent).casefold(),p.name.casefold(),str(p))):
        if any(folder in path.parents for folder in excluded):continue
        try:
            data=json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(data,dict) or data.get('draft') or not isinstance(data.get('puzzles'),list):continue
            raw=json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False)
        except (OSError,UnicodeError,ValueError):continue
        identity=hashlib.sha256(raw.encode()).hexdigest()
        if identity not in groups:
            groups[identity]={'theme_id':identity,'path':path,'aliases':[],
                'title':str(data.get('title') or path.stem),'puzzles':len(data['puzzles'])}
        groups[identity]['aliases'].append(path)
    return list(groups.values())


def project_theme_catalog(root):
    themes=Path(root)/'themes'
    return saved_theme_catalog(themes,[themes/name for name in ('Used Themes','_Archive','_Research','_Drafts')])


def theme_catalog_text(records,duplicates=False):
    copies=sum(len(row['aliases'])-1 for row in records)
    if duplicates:
        selected=[row for row in records if len(row['aliases'])>1]
        lines=[f'Exact duplicate saved themes: {len(selected)} groups, {copies} extra source copies. Files are preserved; equivalent copies share one catalog entry.']
        for row in selected:
            lines.append(row['title']+' ('+row['theme_id'][:12]+'): '+', '.join(str(path) for path in row['aliases']))
    else:
        lines=[f'Saved themes: {len(records)} distinct full-content records; {copies} exact duplicate copies hidden. Legitimate variants remain separate.']
        for row in records[:60]:lines.append(f"- {row['title']} — {row['puzzles']} puzzles [{row['theme_id'][:12]}]")
        if len(records)>60:lines.append(f'Showing the first60 of{len(records)}. The corrected full catalog is also used by saved-theme pickers.')
    return '\n'.join(lines)


def unique_theme_label(label,title,path,directory,used):
    if label not in used:return label
    try:source=str(Path(path).relative_to(directory))
    except ValueError:source=str(path)
    base=f'{title} ({source})';candidate=base;counter=2
    while candidate in used:
        candidate=f'{base} [{counter}]';counter+=1
    return candidate
