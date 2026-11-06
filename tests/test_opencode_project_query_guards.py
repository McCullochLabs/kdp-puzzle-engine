from publishing.studio_project_queries import project_query
import pytest


@pytest.mark.parametrize("input_text,expected_output", [
    ("Show my saved themes", "themes"),
    ("Preview my cover", "cover"),
    ("Do not show my cover", None),
    ("Show my cover and publish it", None),
    ("Show me the interior and export it", None),
    ("Never show saved themes", None),
    ("Find duplicate themes and delete them", None),
    ("Show project status then run a command", None),
])
def test_project_query(input_text, expected_output):
    assert project_query(input_text) == expected_output
