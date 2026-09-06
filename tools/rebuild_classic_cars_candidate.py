"""Rebuild only the Classic Cars commercial candidate after visual review."""
from build_commercial_baseline import WORD_SEARCHES, build_word_search


if __name__ == "__main__":
    print(build_word_search(WORD_SEARCHES[0]))
