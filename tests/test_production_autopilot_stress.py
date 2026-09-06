"""Safe coordinator stress coverage; no real package, API, or art call occurs."""
from publishing.production_autopilot import ProductionAutopilot, canonical_facts


def _facts(kind, index):
    book = {"book_id": f"{kind}-{index}", "source_key": "", "package_path": "", "metadata": {"title": f"{kind} test {index}", "author": "Jordan M. Slade", "puzzle_type": kind, "puzzle_count": 48, "files": {}}}
    return canonical_facts(book)


def test_safe_batch_simulates_mixed_types_repairs_and_isolated_failure(tmp_path):
    kinds = ["Word Search", "Word Search", "Sudoku", "Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"]
    outcomes = {}
    for index, kind in enumerate(kinds):
        calls = {"cover": 0}
        def cover():
            calls["cover"] += 1
            return {"repair": True, "detail": "cover safe-area repair"} if index == 1 and calls["cover"] == 1 else "cover checked"
        stages = {"validate": lambda: "capacity checked", "generate": lambda: "generated", "cover": cover, "listing": lambda: "Gemini unavailable; local listing used", "package": lambda: "package", "handoffs": lambda: "local handoffs"}
        if index == 0:
            stages["validate"] = lambda: (_ for _ in ()).throw(RuntimeError("insufficient high-quality word capacity"))
        outcomes[kind + str(index)] = ProductionAutopilot(tmp_path, f"{index}").run(_facts(kind, index), stages)
    assert outcomes["Word Search0"]["status"] == "needs_human_review"
    assert outcomes["Word Search1"]["status"] == "complete"
    assert outcomes["Word Search1"]["repairs"]
    assert all(value["status"] == "complete" for key, value in outcomes.items() if key != "Word Search0")
