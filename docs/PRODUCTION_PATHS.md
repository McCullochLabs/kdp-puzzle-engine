# Supported Production Paths

## Use these for every new book

1. Open **Start Word Search Creator**.
2. Create a Word Search through its guided book flow, or open **Sudoku books** for Sudoku, Cryptograms, Scramble + Trivia, and Mixed Brain Games.
3. Let the app complete its normal package, proof, release-contract, and Publishing Center steps.
4. Use Publishing Center only to prepare the marketplace handoff you chose.

These are the supported production paths. They use the current package layout,
one-book-at-a-time safeguard, recovery checkpoints, release contract, and
catalog connection.

## Historical builder scripts

Root-level files named `build_*.py`, `rebuild_*.py`, and similar one-time
repair scripts are retained for historical recovery and reference only. They
are not normal production tools and may create older flat-layout folders or
skip newer release steps. Do not use them to start a new book.

If an older package must be recovered, open **Publishing Center → Recovery
Center** or recreate it through the supported studio. Nothing in this note
deletes, moves, or changes legacy scripts or your existing packages.
