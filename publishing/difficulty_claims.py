"""Public difficulty claims supported by existing generation mechanics."""
UNRATED = frozenset(('Cryptogram', 'Word Scramble + Trivia'))


def difficulty_description(kind, difficulty):
    if kind in UNRATED:
        return 'Not difficulty-rated'
    if kind == 'Mixed Brain Games':
        return f'Sudoku: {difficulty}; Cryptograms and word scrambles are not difficulty-rated'
    return str(difficulty)


def difficulty_sentence(kind, difficulty):
    if kind in UNRATED:
        return 'These puzzles are not difficulty-rated.'
    if kind == 'Mixed Brain Games':
        return f'The Sudoku section uses {str(difficulty).lower()} difficulty; Cryptograms and word scrambles are not difficulty-rated.'
    return f'These puzzles use {str(difficulty).lower()} difficulty.'


def cover_difficulty(kind, difficulty):
    # The existing chip always implies a whole-book rating. Omit it when that
    # promise is unsupported; scoped detail belongs in back/listing copy.
    return '' if kind in UNRATED or kind == 'Mixed Brain Games' else str(difficulty)
