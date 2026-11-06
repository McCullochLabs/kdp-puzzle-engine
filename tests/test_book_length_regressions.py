import json
from pathlib import Path
from puzzle_book_studio import make_interior
from publishing.product_qa import inspect_product
import wordsearch
from holiday_combo import load_source,build_plan

def test_every_holiday_partition_obeys_the_actual_placement_contract():
    rows,_=build_plan(load_source(),20261106)
    assert len(rows)==100
    for row in rows:wordsearch.validate_word_set(list(row.words),15)

def test_hyphenated_fact_answer_is_same_scramble_solution(tmp_path):
    pdf=tmp_path/"interior.pdf"
    make_interior("Word Scramble + Trivia","Roadside Word Discoveries","Fact clues and answers","Jordan M. Slade",60,"Mixed",20261104,pdf,"Travel & Adventure")
    report=inspect_product(tmp_path,tmp_path,{"puzzle_count":60})
    result=next(r for r in report.findings if r.check_id=="puzzle.answer_integrity")
    assert result.passed,result.message
