"""Independent, size-neutral checks shared by generators and final QA."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1), (0, -1), (-1, 0), (-1, -1), (-1, 1))
POLICY_REVISION = 'puzzle_integrity_20261102_v4'
# A bounded screen, not a guarantee against every objectionable substring.
DENYLIST = ("FUCK", "SHIT", "CUNT", "NIGGER", "FAGGOT")


def occurrences(grid, word):
    found = {}
    if not word:
        return []
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            if grid[r][c] != word[0]:
                continue
            for dr, dc in DIRECTIONS:
                end_r, end_c = r+dr*(len(word)-1), c+dc*(len(word)-1)
                if 0<=end_r<len(grid) and 0<=end_c<len(grid[end_r]):
                    if all(grid[r+dr*k][c+dc*k]==ch for k,ch in enumerate(word)):
                        cells = [(r+dr*k,c+dc*k) for k in range(len(word))]
                        found[tuple(sorted(cells))] = cells
    return list(found.values())


def verify_wordsearch(grid, placements, words, intended=None, directions=None, *, content_policy="general"):
    if content_policy not in ("general", "adult_intended_profanity"):
        return ["Unsupported word-search content policy."]
    if content_policy == "adult_intended_profanity" and intended is None:
        return ["Adult content policy requires explicit intended targets."]
    errors = []
    n = len(grid)
    if not n or any(len(row) != n for row in grid):
        return ['Grid must be a nonempty square.']
    if any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' or len(ch) != 1 for row in grid for ch in row):
        return ['Grid contains an invalid letter.']
    if not words or len(words) != len(set(words)) or len(placements) != len(words):
        errors.append('Target uniqueness or placement count mismatch.')
    if intended is not None and Counter(words) != Counter(intended):
        errors.append('Not every intended target was placed.')
    for word, cells in zip(words, placements):
        if len(cells) != len(word) or not all(0 <= r < n and 0 <= c < n for r,c in cells):
            errors.append(f'Invalid placement: {word}'); continue
        steps = {(b[0]-a[0], b[1]-a[1]) for a,b in zip(cells, cells[1:])}
        if len(word) > 1 and (len(steps) != 1 or not steps <= {tuple(d) for d in (directions or DIRECTIONS)}):
            errors.append(f'Invalid direction: {word}')
        if ''.join(grid[r][c] for r,c in cells) != word:
            errors.append(f'Incorrect answer: {word}')
        if len(occurrences(grid, word)) != 1:
            errors.append(f'Target must occur exactly once: {word}')
    # Adult mode exempts only intentional profanity on a target's own path.
    # Unrelated filler occurrences and hateful slurs remain blocked in all modes.
    adult_profanity = {"FUCK", "SHIT", "CUNT"}
    for term in DENYLIST:
        for path in occurrences(grid, term):
            intentional = (
                content_policy == "adult_intended_profanity"
                and term in adult_profanity
                and any(
                    word in intended
                    and (term in word or term[::-1] in word)
                    and set(path).issubset(set(map(tuple, cells)))
                    for word, cells in zip(words, placements)
                )
            )
            if not intentional:
                errors.append('Accidental denylist match.')
                break
    return errors


def wordsearch_difficulty(grid, placements, words):
    """Transparent mechanics estimate, not a validated reading-age measure."""
    cells = {tuple(cell) for line in placements for cell in line}
    letters = sum(map(len, words)) or 1
    diagonal = sum(len(p)>1 and p[1][0]!=p[0][0] and p[1][1]!=p[0][1] for p in placements)/max(1,len(words))
    backward = sum(len(p)>1 and (p[1][0]<p[0][0] or (p[1][0]==p[0][0] and p[1][1]<p[0][1])) for p in placements)/max(1,len(words))
    density = len(cells)/max(1,len(grid)**2)
    overlap = 1-len(cells)/letters
    mean_length = letters/max(1,len(words))
    score = min(100, round(25*diagonal + 30*backward + 15*overlap + 10*min(1,len(grid)/21) + 10*min(1,mean_length/12) + 10*(1-density)))
    return dict(label='easy' if score<30 else 'medium' if score<55 else 'hard', score=score,
                basis='mechanics_v1', diagonal_share=round(diagonal,3), backward_share=round(backward,3),
                density=round(density,3), overlap=round(overlap,3), mean_length=round(mean_length,2))


def write_manifest(pdf, records, layout_regions=None):
    pdf = Path(pdf)
    target = pdf.with_suffix('.puzzles.json')
    target.write_text(json.dumps({'schema_version':1, 'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
                                  'puzzle_count':len(records), 'puzzles':records,
                                  'layout_regions':layout_regions or []}, indent=2), encoding='utf-8')
    return target


def verify_rendered_grids(manifest, geometry):
    """Read glyphs back into cells; compare actual PDF puzzles AND solutions.

    Vector-only symbol Sudoku is reported as unmeasured instead of certified.
    """
    errors=[]; skipped=[]; checked=0
    regions=manifest.get('layout_regions',[])
    for page_number,page in enumerate(geometry,1):
        for role,field in (('puzzle','puzzle_page'),('solution','solution_page')):
            rows=sorted((r for r in manifest['puzzles'] if r.get(field)==page_number and
                         r['type'] in ('word_search','sudoku')),key=lambda r:r['number'])
            boxes=sorted((r for r in regions if r['page']==page_number and r['role']==role),
                         key=lambda r:(-r['bounds'][3],r['bounds'][0]))
            if len(rows)!=len(boxes):
                if rows: errors.append(f'Page {page_number}: missing or extra {role} grid regions.')
                continue
            for row,region in zip(rows,boxes):
                if row.get('display_style')=='shapes':
                    skipped.append(row['number']); continue
                expected=row['grid'] if role=='puzzle' else row['solution_grid']
                n=len(expected); is_word=row['type']=='word_search'
                actual=[['' if is_word else 0 for _ in range(n)] for _ in range(n)]
                left,bottom,right,top=region['bounds']; cw=(right-left)/n; ch=(top-bottom)/n
                for char,x0,y0,x1,y1 in page['glyphs']:
                    x,y=(x0+x1)/2,(y0+y1)/2
                    if not (left<x<right and bottom<y<top): continue
                    r,c=int((top-y)/ch),int((x-left)/cw)
                    value=char
                    if not is_word:
                        if row.get('display_style')=='letters' and char in 'ABCDEFGHI': value=ord(char)-64
                        elif char in '123456789': value=int(char)
                        else: errors.append(f"Puzzle {row['number']}: unexpected Sudoku glyph."); continue
                    if actual[r][c] not in ('',0):
                        errors.append(f"Puzzle {row['number']}: multiple glyphs in one {role} cell.")
                    actual[r][c]=value
                if actual!=expected:
                    errors.append(f"Puzzle {row['number']}: rendered {role} grid differs from its verified record.")
                else: checked+=1
    return dict(errors=errors,grids_checked=checked,unmeasured_symbol_puzzles=sorted(set(skipped)))


def verify_manifest(pdf, manifest, page_count):
    """Verify puzzle math, artifact binding, and explicit solution correspondence."""
    errors = []
    if manifest.get('schema_version') != 1:
        errors.append('Unsupported puzzle manifest version.')
    if hashlib.sha256(Path(pdf).read_bytes()).hexdigest() != manifest.get('pdf_sha256'):
        errors.append('Puzzle record does not match the current PDF.')
    rows = manifest.get('puzzles', [])
    if not rows or len(rows) != manifest.get('puzzle_count'):
        errors.append('Puzzle count mismatch.')
    ids = [row.get('number') for row in rows]
    if ids != list(range(1,len(rows)+1)):
        errors.append('Puzzle IDs must be consecutive and unique.')
    for row in rows:
        number = row.get('number')
        for key in ('puzzle_page','solution_page'):
            if not isinstance(row.get(key), int) or not 1 <= row[key] <= page_count:
                errors.append(f'Puzzle {number}: missing or invalid {key}.')
        if row.get('type') == 'word_search':
            errors.extend(f'Puzzle {number}: {e}' for e in verify_wordsearch(row['grid'],row['placements'],row['words'],row.get('intended_words',row['words']),row.get('directions'),content_policy=row.get('content_policy','general')))
            if row.get('solution_grid') != row['grid'] or row.get('solution_placements') != row['placements']:
                errors.append(f'Puzzle {number}: solution differs from puzzle.')
        elif row.get('type') == 'sudoku':
            import sudoku
            p, s = row['grid'], row['solution_grid']
            if len(s)!=9 or any(len(r)!=9 for r in s) or len(p)!=9 or any(len(r)!=9 for r in p):
                errors.append(f'Puzzle {number}: Sudoku grid shape is invalid.'); continue
            units = s + [list(c) for c in zip(*s)] + [[s[r+i][c+j] for i in range(3) for j in range(3)] for r in (0,3,6) for c in (0,3,6)]
            if len(s)!=9 or any(len(r)!=9 for r in s) or any(set(u)!=set(range(1,10)) for u in units):
                errors.append(f'Puzzle {number}: invalid Sudoku solution.')
            if len(p)!=9 or any(len(r)!=9 for r in p) or any(p[r][c] and p[r][c]!=s[r][c] for r in range(9) for c in range(9)) or sudoku.count_solutions([r[:] for r in p],2)!=1:
                errors.append(f'Puzzle {number}: Sudoku givens or uniqueness failed.')
        elif row.get('type') == 'cryptogram':
            mapping=row.get('mapping',{})
            plain=row.get('plaintext',''); coded=row.get('ciphertext','')
            alphabet=set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
            if (not plain or not any(ch in alphabet for ch in plain) or set(mapping)!=alphabet or set(mapping.values())!=alphabet or any(mapping[ch]==ch for ch in alphabet) or ''.join(mapping.get(ch,ch) for ch in plain)!=coded or row.get('solution_plaintext')!=plain):
                errors.append(f'Puzzle {number}: cryptogram mapping or answer mismatch.')
        elif row.get('type') == 'scramble_trivia':
            word=row.get('word',''); shown=row.get('scrambled','')
            if (not isinstance(word, str) or not word or any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' for ch in word) or Counter(word)!=Counter(shown) or word==shown or not isinstance(row.get('fact_answer'), str) or not row['fact_answer'].strip() or row.get('solution_word')!=word or row.get('solution_fact_answer')!=row.get('fact_answer')):
                errors.append(f'Puzzle {number}: scramble letters or answer mismatch.')
        else:
            errors.append(f'Puzzle {number}: unsupported puzzle type.')
    return errors
