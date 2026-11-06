"""Deterministic human-technique rating; unresolved logic is labelled honestly."""
from __future__ import annotations

UNITS = ([[(r,c) for c in range(9)] for r in range(9)] +
         [[(r,c) for r in range(9)] for c in range(9)] +
         [[(r+i,c+j) for i in range(3) for j in range(3)] for r in (0,3,6) for c in (0,3,6)])
PEERS = {cell:set().union(*(set(u) for u in UNITS if cell in u))-{cell}
         for cell in [(r,c) for r in range(9) for c in range(9)]}


def rate_sudoku(puzzle):
    if len(puzzle)!=9 or any(len(r)!=9 for r in puzzle) or any(type(v)!=int or not 0<=v<=9 for r in puzzle for v in r):
        raise ValueError('Sudoku must be 9 x 9 with integer digits 0–9.')
    grid = [r[:] for r in puzzle]
    for unit in UNITS:
        values=[grid[r][c] for r,c in unit if grid[r][c]]
        if len(values)!=len(set(values)):
            raise ValueError('Sudoku contains conflicting givens.')
    candidates = {(r,c):set(range(1,10))-{grid[y][x] for y,x in PEERS[r,c]}
                  for r in range(9) for c in range(9) if not grid[r][c]}
    steps=[]; advanced=False
    while candidates:
        if any(not v for v in candidates.values()):
            raise ValueError('Sudoku has a contradiction.')
        singles=[(cell,next(iter(values)),'naked single') for cell,values in sorted(candidates.items()) if len(values)==1]
        if not singles:
            for unit in UNITS:
                for value in range(1,10):
                    places=[cell for cell in unit if value in candidates.get(cell,set())]
                    if len(places)==1:
                        singles=[(places[0],value,'hidden single')]; break
                if singles: break
        if singles:
            cell,value,technique=singles[0]
            grid[cell[0]][cell[1]]=value
            del candidates[cell]
            for peer in PEERS[cell]:
                if peer in candidates: candidates[peer].discard(value)
            steps.append(technique); continue
        changed=False
        # Naked pairs eliminate both digits from other cells in their unit.
        for unit in UNITS:
            pairs={tuple(sorted(candidates[cell])) for cell in unit if len(candidates.get(cell,()))==2}
            for pair in sorted(pairs):
                holders=[cell for cell in unit if candidates.get(cell)==set(pair)]
                if len(holders)!=2: continue
                for cell in unit:
                    if cell in candidates and cell not in holders and candidates[cell].intersection(pair):
                        candidates[cell].difference_update(pair); changed=True
            if changed: break
        if changed:
            steps.append('naked pair'); advanced=True; continue
        # Box/line interactions: locked candidates, in either direction.
        for source in UNITS:
            for value in range(1,10):
                holders={cell for cell in source if value in candidates.get(cell,set())}
                if len(holders)<2: continue
                for destination in UNITS:
                    if source==destination or not holders <= set(destination): continue
                    for cell in destination:
                        if cell not in source and value in candidates.get(cell,set()):
                            candidates[cell].remove(value); changed=True
                    if changed: break
                if changed: break
            if changed: break
        if changed:
            steps.append('locked candidate'); advanced=True; continue
        break
    solved=not candidates
    return dict(label=('medium' if advanced else 'easy') if solved else 'hard',
                basis='human_techniques_v1', solved_by_supported_logic=solved,
                techniques=sorted(set(steps)), steps=len(steps), remaining_cells=len(candidates),
                explanation='Solved with singles, locked candidates and naked pairs.' if solved else
                            'Requires techniques beyond the supported logic set; no claim that guessing is required.')
