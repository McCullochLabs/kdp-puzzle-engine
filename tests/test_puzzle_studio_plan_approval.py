import inspect

import puzzle_book_studio


def test_puzzle_studio_creation_passes_persisted_plan_approval():
    source=inspect.getsource(puzzle_book_studio.PuzzleBookStudio._create)
    assert "Approve this book plan" in source
    assert "puzzle_studio.operator_confirmation" in source
    assert "content_plan_approval" not in source  # passed positionally to the established builder


def test_package_builder_accepts_real_plan_approval_evidence():
    signature=inspect.signature(puzzle_book_studio.create_package)
    assert "content_plan_approval" in signature.parameters


def test_visible_puzzle_type_buttons_are_refreshed_from_route_state():
    source=inspect.getsource(puzzle_book_studio.PuzzleBookStudio._choose_kind)
    assert "_refresh_kind_buttons" in source


def test_changing_puzzle_type_reapplies_the_selected_format():
    source=inspect.getsource(puzzle_book_studio.PuzzleBookStudio._changed)
    assert "_format_changed" in source
    assert "_next_name_idea" in source
