from educational_value import educator_back_cover_section, is_educational_context


def test_grade_and_vocabulary_books_are_educational():
    assert is_educational_context("Grade 5 Word Quest")
    assert is_educational_context("Advanced Vocabulary")
    assert not is_educational_context("National Parks")


def test_educator_copy_is_specific_and_conservative():
    copy = educator_back_cover_section("Grade School Vocabulary")
    assert "FOR FAMILIES AND EDUCATORS" in copy
    assert "spelling" in copy
    assert "standards" not in copy.casefold()
    assert educator_back_cover_section("Ocean Life") == ""
