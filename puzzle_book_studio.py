"""Simple, self-contained builders for non-word-search puzzle books.

This module deliberately keeps Sudoku, Cryptograms, and Scramble + Trivia
separate from the word-search engine.  They share the same print size, cover
workflow, package folder, and KDP checks without changing word placement.
"""
from __future__ import annotations
import hashlib, json, math, os, random, re, shutil, subprocess, sys, tempfile, threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics

from publishing.difficulty_claims import UNRATED, difficulty_description, difficulty_sentence, cover_difficulty

APP = Path(__file__).resolve().parent
OUT = APP / "out"
CONTENT_LIBRARY = APP / "word_banks" / "puzzle_content_library.json"
EDITORIAL_CONTENT_LIBRARY = APP / "word_banks" / "editorial_cryptogram_packs.json"
MASTER_WORD_BANK = APP / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
CONTENT_BUFFER = 1.60  # Every ready pack keeps 60% more unique entries than one book needs.
MIN_VERIFIED_LIBRARY = 130  # A release-ready standard library never has fewer than 130 checked entries.
TARGET_VERIFIED_LIBRARY = 240  # Supports two buffered 60-puzzle editions with room for replacements.
FORMAT_PRESETS = {
    "Standard": {"count": 60, "difficulty": "Standard", "label": "A full-size, clear-format puzzle book."},
    "Large Print": {"count": 48, "difficulty": "Easy", "label": "Fewer puzzles with generous space and easy-to-read pages."},
    "Kids": {"count": 48, "difficulty": "Easy", "label": "Friendly pacing and approachable difficulty."},
    "Signature Edition": {"count": 100, "difficulty": "Mixed", "label": "A premium 100-puzzle edition; requires a 160-entry library."},
}
PAGE_W, PAGE_H = letter
MARGIN = 54
from font_utils import pdf_font_candidates, register_pdf_font
from cover import cover_quality_report
from publishing.design import INTERIOR_PRESETS, BONUS_PAGE_OPTIONS, automatic_bonus_pages, bonus_page_titles, default_preset, preset as interior_preset
from publishing.package_layout import initialize_package_layout, package_file, package_layout_readme
from publishing.title_pages import STYLE_LABELS, render_title_page, spec_from_mapping
from background_generation.index import BackgroundAssetIndex
from background_generation.routing import CoverRequest, select_cover_asset, select_cover_gallery, write_routing_diagnostics

# Interior PDFs keep the same Book* aliases as always; font_utils resolves
# which actual file backs each alias on this machine.
BOOK_FONT_FAMILIES = {"BookSans": "sans", "BookBold": "sans-bold", "BookMono": "mono-bold"}
ART = {
    "Sudoku": (("sudoku_logic_luxe_v4.png", "sudoku_papercraft_v5.png", "sudoku_quiet_ritual_v6.png"), "starlight-indigo", "photo"),
    "Cryptogram": (("puzzle_cryptogram_cipher_v1.png", "puzzle_cryptogram_vintage_v2.png", "puzzle_cryptogram_artdeco_v3.png"), "library-burgundy", "photo"),
    "Word Scramble + Trivia": (("puzzle_scramble_trivia_v1.png", "puzzle_scramble_gamenight_v2.png", "puzzle_scramble_retroquiz_v3.png"), "tropical-pop", "photo"),
    "Mixed Brain Games": (("puzzle_scramble_gamenight_v2.png", "sudoku_logic_luxe_v4.png", "puzzle_cryptogram_artdeco_v3.png"), "midnight-gold", "photo"),
}
# Theme-aware artwork keeps a space book from receiving a generic game-night
# cover and lets the one-screen studio make a sound automatic choice.
THEME_ART = {
    "Space & Astronomy": (("space_astronomy.png", "space_planet_v2.png", "space_rocket_v3.png"), "starlight-indigo", "photo"),
    "Garden & Growing": (("gardening.png", "gardening_greenhouse_v2.png", "gardening_vegetables_v3.png"), "gardening", "photo"),
    "Travel & Adventure": (("travel_history.png", "travel_skyline_v3.png", "travel_suitcase_v2.png"), "retro-travel-and-landmarks", "photo"),
    "Road Trips & Highways": (("road_trip_vehicles.png", "vehicles_camping_v2.png", "vehicles_vintage_v3.png"), "retro-travel-and-landmarks", "photo"),
    "General Knowledge & Curiosity": (("puzzle_scramble_trivia_v1.png", "puzzle_scramble_gamenight_v2.png", "puzzle_scramble_retroquiz_v3.png"), "tropical-pop", "photo"),
    "Pets & Animal Life": (("pets.png", "pets_cat_v3.png", "pets_puppy_v2.png"), "animals", "photo"),
    "Holidays & Seasons": (("winter_holidays.png", "winter_holidays.png"), "holly-jolly", "photo"),
    "History & Heritage": (("american_history_heritage_v2.png", "american_history_museum_v3.png", "american_history_museum_v4.png"), "patriotic", "photo"),
    "Food & Home": (("food_kitchen.png", "food_baking_v2.png", "food_produce_v3.png"), "food", "photo"),
    "School & Vocabulary": (("school_elementary_learning_v1.png", "school_middle_learning_v1.png", "school_high_learning_v1.png"), "scholarly-blue", "photo"),
    "Cars & Adventure": (("road_trip_vehicles.png", "vehicles_camping_v2.png", "vehicles_vintage_v3.png"), "retro-travel-and-landmarks", "photo"),
    "Nature & Outdoors": (("national_parks_outdoors.png", "national_parks_forest_v3.png", "national_parks_alpine_v2.png"), "forest-cabin", "photo"),
    "Bible & Faith": (("bible_faith_sunrise_v2.png", "bible_chapel_v3.png", "bible_garden_v4.png"), "bible", "photo"),
}
# A publisher can choose a particular direction, but a completely automatic
# cover still rotates through layouts using the book seed.  That keeps a series
# visually cohesive without making every new book look like the same template.
COVER_STYLE_OPTIONS = {
    "Automatic matching": None,
    "Photo spotlight": "photo",
    "Playful gallery": "gallery",
    "Color blocks": "colorblock",
    "Ticket badge": "ticket",
    "Soft halo": "halo",
    "Retro print": "retro",
    "Sunburst": "sunburst",
    "Graphic stripes": "stripe",
    "Mixed edge collage": "mixed-edge",
    "Mixed editorial": "mixed-editorial",
    "Mixed premium logic": "mixed-logic",
}
AUTO_COVER_STYLES = {
    "Sudoku": ("photo",),
    "Cryptogram": ("photo", "retro", "gallery"),
    "Word Scramble + Trivia": ("photo", "playful", "sunburst", "ticket"),
    # Color blocks left too much empty space on the premium mixed-games
    # cover. Keep automatic choices visual and puzzle-focused instead.
    "Mixed Brain Games": ("mixed-edge", "mixed-editorial", "mixed-logic", "photo"),
}
DEFAULTS = {
    "Sudoku": ("Large Print Sudoku", "100 Number, Letter & Shape Logic Puzzles with Full Solutions", 100, "Mixed"),
    "Cryptogram": ("Cryptogram Challenge", "60 Clever Code-Breaking Puzzles with Solutions", 60, "Standard"),
    "Word Scramble + Trivia": ("Word Scrambles & Fact Clues", "60 Word Scrambles with Fact Clues and Answers", 60, "Standard"),
    "Mixed Brain Games": ("The Everyday Brain Games Collection", "60 Sudoku, Cryptograms, and Word Scramble Challenges", 60, "Mixed"),
}

AVAILABLE_THEMES = ("General Starter", "General Knowledge & Curiosity", "Space & Astronomy", "Garden & Growing", "Travel & Adventure", "Road Trips & Highways", "Pets & Animal Life", "Holidays & Seasons", "History & Heritage", "Food & Home", "School & Vocabulary", "Cars & Adventure", "Nature & Outdoors", "Bible & Faith")

# One shared map keeps Cryptograms, Scramble + Trivia, automatic artwork, and
# the Capacity page attached to the same real master-library groups.
THEME_TOPIC_MAP = {
    "Space & Astronomy": ("Space & Astronomy",),
    "Garden & Growing": ("Gardening", "Gardening & Garden Life", "Homesteading", "Herbs Fruits and Vegetables"),
    "Travel & Adventure": ("Travel & World Discovery", "Travel Road Trips and Getaways", "Outdoor Adventure", "National Parks"),
    "Road Trips & Highways": ("Travel Road Trips and Getaways", "Vehicles & Automotive", "Outdoor Adventure"),
    "Pets & Animal Life": ("Cats & Pets", "Dogs & Pets", "Pets and Animal Care", "Birdwatching & Wildlife"),
    "Holidays & Seasons": ("Christmas", "Christmas and Winter", "Halloween", "Halloween Autumn and Harvest", "Holiday and Seasonal Life", "Holidays", "Easter and Spring"),
    "History & Heritage": ("American History", "American Heritage", "World War II History"),
    "Food & Home": ("Baking and Food", "Baking & Food", "Garden to Table", "Home and Household"),
    "School & Vocabulary": ("Grade School Vocabulary", "Middle School Vocabulary", "High School Vocabulary", "Grade 5 Vocabulary", "Grade 6 Vocabulary", "Grade 7 Vocabulary", "Grade 8 Vocabulary", "Grade 9 Vocabulary", "Grade 10 Vocabulary", "Grade 11 Vocabulary", "Grade 12 Vocabulary"),
    "Cars & Adventure": ("Vehicles & Automotive", "Outdoor Adventure", "Travel Road Trips and Getaways"),
    "Nature & Outdoors": ("Nature", "Forest Wildlife and Outdoors", "National Parks", "Ocean Life", "Outdoor Adventure"),
    "Bible & Faith": ("Bible and Faith", "Faith & Encouragement", "Faith Inspiration and Kindness"),
}

# Prefer the Master Library's own broad, curated packs for production.  They
# are deliberately made of related subtopics (not a blind "everything"
# bucket), so selecting a family unlocks every approved applicable word.
PRODUCTION_FAMILY_PACKS = {
    "Space & Astronomy": ("Planets & Solar System", "Space Missions, Rockets & Astronauts", "Stargazing, Telescopes & Night Sky"),
    "Garden & Growing": ("Gardening, Herbs & Homestead Living",),
    "Travel & Adventure": ("Travel, Road Trips & Weekend Getaways",),
    "Road Trips & Highways": ("Family Road Trips & Travel", "RV, Camping & Off-Road"),
    "Pets & Animal Life": ("Pets, Backyard Animals & Care",),
    "Holidays & Seasons": ("Holidays & Seasonal Fun",),
    "History & Heritage": ("American Heritage", "Presidents, History & Americana"),
    "Food & Home": ("Food, Baking & Kitchen", "Home, Cozy Living & Self Care"),
    "School & Vocabulary": ("Vocabulary Ladder: Grades 5–12",),
    "Cars & Adventure": ("Vehicles, Cars & Trucks", "Family Road Trips & Travel", "RV, Camping & Off-Road"),
    "Nature & Outdoors": ("National Parks, Trails & Wild Places", "Forests, Wildlife & Outdoor Escape", "Coastal, Lake & River Life"),
    "Bible & Faith": ("Bible, Faith & Encouragement — Complete",),
}

CRYPTOS = [
 "A QUIET MIND CAN NOTICE SMALL DETAILS", "PRACTICE MAKES PATTERNS EASIER TO SEE",
 "EVERY CLUE HAS A PLACE IN THE BIGGER PICTURE", "GOOD QUESTIONS LEAD TO BETTER ANSWERS",
 "PATIENT THINKING TURNS CONFUSION INTO PROGRESS", "A SHORT BREAK CAN REFRESH A BUSY BRAIN",
 "CURIOSITY MAKES ORDINARY DAYS MORE INTERESTING", "SMALL STEPS CAN SOLVE A LARGE PROBLEM",
 "THE BEST CLUES OFTEN HIDE IN PLAIN SIGHT", "LOGIC GROWS STRONGER WITH EVERY PUZZLE",
 "DISCOVERY BEGINS WHEN WE LOOK A LITTLE CLOSER", "A FRESH IDEA CAN OPEN A NEW PATH",
 "WORD PLAY IS EXERCISE FOR AN ACTIVE MIND", "FOCUS MAKES ROOM FOR CREATIVE THINKING",
 "EACH PUZZLE IS A CHANCE TO TRY A NEW APPROACH", "LEARNING SOMETHING NEW IS ALWAYS A WIN",
 "A KIND WORD CAN BRIGHTEN A WHOLE DAY", "KEEP GOING UNTIL THE PATTERN STARTS TO APPEAR",
 "TIME AND PATIENCE ARE USEFUL PUZZLE TOOLS", "CLEAR THINKING STARTS WITH ONE GOOD CLUE",
 "A CURIOUS BRAIN NEVER RUNS OUT OF PLACES TO GO", "THE NEXT ANSWER MAY BE CLOSER THAN YOU THINK",
 "SIMPLE IDEAS CAN CREATE SURPRISING RESULTS", "EVERY FINISHED PUZZLE BEGAN WITH A FIRST STEP",
 "LOOK FOR WHAT CHANGES AND WHAT STAYS THE SAME", "THE JOY OF A PUZZLE IS THE MOMENT IT CLICKS",
 "A GOOD CHALLENGE MAKES A GREAT AFTERNOON", "THOUGHTFUL PRACTICE BUILDS CONFIDENCE",
 "THE RIGHT CLUE CAN TURN A LOCKED DOOR INTO A PATH", "IMAGINATION HELPS US SEE MORE THAN ONE ANSWER",
 "CALM THINKING CAN UNTANGLE A KNOTTY PROBLEM", "NEW SKILLS GROW ONE REPEAT AT A TIME",
 "A BRIGHT IDEA OFTEN STARTS AS A SMALL QUESTION", "NOTICE THE DETAILS AND THE PATTERN WILL FOLLOW",
 "LEARNING IS A JOURNEY WITH MANY INTERESTING STOPS", "REASON AND CREATIVITY MAKE A STRONG TEAM",
 "ONE WELL PLACED LETTER CAN CHANGE EVERYTHING", "A PUZZLE IS A FRIENDLY INVITATION TO THINK",
 "TAKE YOUR TIME AND LET THE CLUES DO THEIR WORK", "THE ANSWER IS WAITING INSIDE THE PATTERN",
 "A LITTLE DETERMINATION GOES A LONG WAY", "SMART THINKING LOOKS FOR CONNECTIONS",
 "THE MIND LOVES A QUESTION WITH A SECRET ANSWER", "EACH CLUE ADDS ONE MORE PIECE TO THE MAP",
 "THERE IS ALWAYS SOMETHING NEW TO NOTICE", "GOOD PUZZLES REWARD BOTH PATIENCE AND PLAY",
 "THE FIRST GUESS IS ONLY THE START OF THE JOURNEY", "CONFIDENCE GROWS WHEN WE KEEP PRACTICING",
 "A CAREFUL LOOK CAN REVEAL A HIDDEN PATH", "MAKE ROOM FOR WONDER IN EVERYDAY MOMENTS",
 "EVERY SOLUTION BEGINS WITH A WILLING MIND", "THINK SLOWLY AND THE DETAILS BECOME CLEAR",
 "SMART HABITS TURN HARD THINGS INTO POSSIBLE THINGS", "A NEW PERSPECTIVE CAN CHANGE THE WHOLE PUZZLE",
 "IDEAS BECOME STRONGER WHEN WE TEST THEM", "KEEP YOUR PENCIL READY FOR THE NEXT DISCOVERY",
 "THE BEST PART OF LEARNING IS FINDING OUT MORE", "EVERYDAY CURIOSITY IS A POWERFUL TOOL",
 "PUZZLES REMIND US THAT PATTERNS ARE EVERYWHERE", "TRY AGAIN WITH A FRESH SET OF EYES",
 "THE NEXT CLUE MAY MAKE THE WHOLE PAGE MAKE SENSE", "A STEADY MIND CAN SOLVE SURPRISING THINGS",
]
TRIVIA = [
 ("PLANET", "Which planet is known as the Red Planet?", "Mars"), ("OCEAN", "What is the largest ocean on Earth?", "Pacific Ocean"),
 ("TRIANGLE", "How many sides does a triangle have?", "Three"), ("RAINBOW", "How many colors are traditionally named in a rainbow?", "Seven"),
 ("CHEETAH", "What is the fastest land animal?", "Cheetah"), ("PENGUIN", "Which bird cannot fly but is a skilled swimmer?", "Penguin"),
 ("SATURN", "Which planet is famous for its rings?", "Saturn"), ("HONEY", "What sweet food do bees make?", "Honey"),
 ("COMPASS", "Which tool points toward north?", "Compass"), ("VOLCANO", "What landform can erupt with lava?", "Volcano"),
 ("GIRAFFE", "What is the tallest living land animal?", "Giraffe"), ("PUMPKIN", "Which orange squash is often carved for Halloween?", "Pumpkin"),
 ("LIBRARY", "Where can you borrow books?", "Library"), ("DESERT", "What is a very dry region with little rain called?", "Desert"),
 ("ORCHESTRA", "What is a large group of musicians called?", "Orchestra"), ("BUTTERFLY", "What insect begins life as a caterpillar?", "Butterfly"),
 ("EVEREST", "What is the highest mountain above sea level?", "Mount Everest"), ("JUPITER", "What is the largest planet in our solar system?", "Jupiter"),
 ("KANGAROO", "Which animal carries its young in a pouch?", "Kangaroo"), ("GLACIER", "What is a huge, slowly moving mass of ice called?", "Glacier"),
 ("OCTOPUS", "Which ocean animal has eight arms?", "Octopus"), ("PYRAMID", "What ancient Egyptian structure has a square base and pointed sides?", "Pyramid"),
 ("MERCURY", "Which planet is closest to the Sun?", "Mercury"), ("MAPLE", "Which tree is famous for syrup?", "Maple"),
 ("GUITAR", "Which instrument usually has six strings?", "Guitar"), ("TURTLE", "Which reptile carries a hard shell?", "Turtle"),
 ("IGLOO", "What snow shelter is associated with Arctic regions?", "Igloo"), ("MAGNET", "What object can attract iron?", "Magnet"),
 ("CASTLE", "What fortified home was often built for kings and queens?", "Castle"), ("FOREST", "What large area is filled with many trees?", "Forest"),
 ("BICYCLE", "What two-wheeled vehicle is powered with pedals?", "Bicycle"), ("DINOSAUR", "What prehistoric animal group included the Tyrannosaurus rex?", "Dinosaur"),
 ("LANTERN", "What portable light can be carried by a handle?", "Lantern"), ("MIRROR", "What reflects your image?", "Mirror"),
 ("PARACHUTE", "What device helps a person descend slowly through the air?", "Parachute"), ("TREASURE", "What word means valuable items that have been hidden?", "Treasure"),
 ("ANCHOR", "What heavy object keeps a boat from drifting away?", "Anchor"), ("CANYON", "What deep valley is often carved by a river?", "Canyon"),
 ("CLOUD", "What visible collection of water drops floats in the sky?", "Cloud"), ("BREAD", "What baked food is often made from flour and yeast?", "Bread"),
 ("CAMERA", "What device takes photographs?", "Camera"), ("CIRCUS", "What traveling show may include acrobats?", "Circus"),
 ("DRAGON", "What legendary creature is often pictured with wings and scales?", "Dragon"), ("FARMER", "Who grows crops or raises animals for food?", "Farmer"),
 ("ISLAND", "What land is completely surrounded by water?", "Island"), ("JUNGLE", "What dense tropical forest has abundant plant life?", "Jungle"),
 ("KITE", "What light toy flies in the wind on a string?", "Kite"), ("LIGHTHOUSE", "What tower uses a bright light to guide ships?", "Lighthouse"),
 ("MUSEUM", "What building displays objects of art, science, or history?", "Museum"), ("NOTEBOOK", "What book has blank or lined pages for writing?", "Notebook"),
 ("ORANGE", "What citrus fruit shares its name with a color?", "Orange"), ("PIRATE", "What seafaring character is linked with buried treasure?", "Pirate"),
 ("RAINCOAT", "What waterproof coat is worn in wet weather?", "Raincoat"), ("SAILBOAT", "What boat moves with wind-filled sails?", "Sailboat"),
 ("TELESCOPE", "What instrument helps you view distant stars and planets?", "Telescope"), ("UMBRELLA", "What handheld item protects you from rain?", "Umbrella"),
 ("VIOLIN", "What small string instrument is played with a bow?", "Violin"), ("WATERFALL", "What is a place where water drops over a steep edge?", "Waterfall"),
 ("XYLOPHONE", "What instrument makes sounds when its bars are struck?", "Xylophone"), ("YACHT", "What is a large pleasure boat called?", "Yacht"),
 ("ZEBRA", "What striped animal belongs to the horse family?", "Zebra"),
]

# These are original editorial prompts.  They are deliberately short enough
# for a clean 8.5 x 11 page and are checked for duplicate answers/questions
# before a package can be created.
CRYPTOS += [
 "A GOOD PUZZLE MAKES A QUIET HOUR FEEL TOO SHORT", "A PENCIL AND A PATTERN CAN START AN ADVENTURE",
 "EVERY CLUE DESERVES A SECOND LOOK", "THE NEXT DISCOVERY MAY BE ONE LETTER AWAY",
 "A PUZZLE PAGE IS A SMALL PLACE FOR BIG IDEAS", "SLOW AND STEADY THINKING FINDS THE HIDDEN ROUTE",
 "CURIOSITY GIVES ORDINARY DETAILS A NEW JOB", "A PATTERN CAN BE PATIENTLY UNLOCKED",
 "THE BEST SOLUTIONS ARRIVE ONE CLUE AT A TIME", "A FRESH PAGE IS A FRESH OPPORTUNITY",
 "THOUGHTFUL QUESTIONS MAKE STRONGER ANSWERS", "THE MIND ENJOYS A WELL MADE MYSTERY",
 "A LITTLE FOCUS CAN MOVE A PUZZLE FORWARD", "EVERY LETTER CAN CARRY A USEFUL HINT",
 "GOOD PUZZLES ASK US TO NOTICE MORE", "A CALM START MAKES ROOM FOR A CLEVER FINISH",
 "A NEW CLUE CAN CHANGE THE WHOLE STORY", "PUZZLE TIME IS TIME WELL SPENT",
 "SOME ANSWERS APPEAR WHEN WE STOP RUSHING", "THE PAGE GETS CLEARER WITH EVERY SMALL WIN",
 "A SHARP EYE LOVES A SUBTLE DETAIL", "THE FUN IS IN FINDING THE PATH",
 "ONE PATTERN OFTEN LEADS TO ANOTHER", "A PUZZLE REWARDS THE PERSON WHO STAYS CURIOUS",
 "TAKE THE LONG VIEW AND THE CLUES LINE UP", "A SMALL DISCOVERY CAN FEEL LIKE A GREAT VICTORY",
 "EVERY QUESTION INVITES A LITTLE EXPLORATION", "A SOLUTION IS BUILT FROM CAREFUL MOMENTS",
 "PLAYFUL THINKING KEEPS THE MIND MOVING", "A GOOD CLUE IS A FRIENDLY NUDGE",
 "THE ANSWER CAN HIDE BEHIND A SIMPLE PATTERN", "PERSISTENCE MAKES COMPLEX THINGS FRIENDLIER",
 "ONE QUIET MOMENT CAN SPARK A BRIGHT IDEA", "A PUZZLE LOVES A PATIENT SOLVER",
 "LET THE LETTERS TELL THEIR OWN STORY", "THE MOST INTERESTING PATH IS NOT ALWAYS STRAIGHT",
 "A WELL TIMED PAUSE CAN HELP A LOT", "SMART QUESTIONS KEEP A DAY INTERESTING",
 "EACH COMPLETED LINE BUILDS A LITTLE MOMENTUM", "THE SEARCH FOR AN ANSWER IS PART OF THE FUN",
 "KEEP LOOKING AND THE PATTERN MAY SMILE BACK", "A PUZZLE IS A SMALL EXERCISE IN POSSIBILITY",
 "THE LAST CLUE OFTEN MAKES THE FIRST ONE CLEAR", "A GOOD CHALLENGE INVITES US TO GROW",
 "NOTICE WHAT BELONGS AND WHAT DOES NOT", "A CURIOUS MIND ENJOYS THE SCENIC ROUTE",
 "THE CLUES ARE PATIENTLY WAITING TO BE CONNECTED", "A CLEAR PLAN MAKES A TOUGH PAGE FRIENDLIER",
 "A PUZZLE CAN TURN A BREAK INTO A DISCOVERY", "THERE IS SATISFACTION IN A CAREFUL FINISH",
 "BRIGHT IDEAS OFTEN START WITH A SINGLE WORD", "THE NEXT PATTERN MAY BE THE ONE THAT CLICKS",
 "THINKING WELL MEANS GIVING DETAILS SOME TIME", "A SOLUTION GROWS FROM LITTLE PIECES OF EVIDENCE",
 "A GOOD PUZZLE LEAVES ROOM FOR AHA MOMENTS", "THE JOY OF LEARNING FITS ON ANY PAGE",
 "FOLLOW THE CLUES AND ENJOY THE DETOUR", "EVERY PUZZLE HAS A DOORWAY INTO IT",
 "A STEADY PENCIL MAKES A FINE PUZZLE COMPANION", "THE FIRST STEP IS TO LOOK CLOSELY",
 "A NEW ANSWER CAN MAKE AN OLD CLUE SHINE", "LOGIC AND IMAGINATION MAKE A GREAT PAIR",
 "PAUSE BREATHE AND TRY THE NEXT CLUE", "THE RIGHT QUESTION CAN OPEN A WHOLE NEW VIEW",
 "A WELL EARNED ANSWER IS WORTH THE WAIT", "PUZZLES MAKE ROOM FOR BOTH PLAY AND THOUGHT",
 "THE DETAILS ARE OFTEN MORE HELPFUL THAN THEY LOOK", "A LITTLE WONDER MAKES THE BRAIN FEEL AWAKE",
 "THE SATISFACTION IS IN WATCHING THE PIECES FIT", "EACH PAGE OFFERS ANOTHER CHANCE TO THINK DIFFERENTLY",
 "A PUZZLE CAN BE A PEACEFUL KIND OF ADVENTURE", "KEEP THE CLUES CLOSE AND THE POSSIBILITIES OPEN",
]

# Keep the shared Cryptogram pool above the Signature Edition threshold too.
CRYPTOS += [
 "A GOOD CLUE CAN MAKE A BUSY DAY FEEL CALMER", "EVERY PATTERN STARTS WITH ONE SMALL OBSERVATION",
 "A CAREFUL SOLVER NOTICES WHAT OTHERS MISS", "THE NEXT LETTER MAY CHANGE THE ENTIRE PUZZLE",
 "GOOD IDEAS HAVE ROOM TO GROW ON THE PAGE", "A PUZZLE BREAK CAN BRING A FRESH PERSPECTIVE",
 "THE CLEAREST ANSWERS BEGIN WITH A PATIENT LOOK", "ONE SMALL CONNECTION CAN OPEN A BIGGER PATTERN",
 "A THOUGHTFUL GUESS CAN LEAD TO A BETTER CLUE", "THE BEST PUZZLES REWARD KIND PERSISTENCE",
 "A QUIET MIND CAN FIND A BRIGHT SOLUTION", "EVERY SOLVED CLUE BUILDS A LITTLE CONFIDENCE",
 "THE PAGE HOLDS MORE POSSIBILITIES THAN IT FIRST SHOWS", "SLOW THINKING CAN MAKE A TRICKY CLUE FRIENDLY",
 "A NEW ANGLE CAN MAKE AN OLD PROBLEM FEEL SIMPLE", "THE NEXT DISCOVERY MAY BE HIDING IN PLAIN SIGHT",
 "A PUZZLE IS A PLACE WHERE CURIOSITY CAN STRETCH", "THE MOST USEFUL HINT MAY BE THE SMALLEST ONE",
 "TAKE A BREATH AND LET THE PATTERN COME INTO VIEW", "EACH CAREFUL STEP MAKES THE FINAL ANSWER CLOSER",
 "A WELL MADE PUZZLE LEAVES ROOM FOR WONDER", "THE RIGHT DETAIL CAN TURN A QUESTION INTO A PATH",
 "A PUZZLE PAGE REWARDS THE WILLINGNESS TO EXPLORE", "SMART SOLVING STARTS WITH NOTICING THE UNUSUAL",
 "AN OPEN MIND MAKES A GOOD PARTNER FOR A PUZZLE", "THE MOST SATISFYING ANSWERS ARRIVE ONE CLUE AT A TIME",
 "A LITTLE PATIENCE CAN MAKE A BIG DIFFERENCE", "EVERY PAGE IS A CHANCE TO PRACTICE CLEAR THINKING",
 "THE CLUES WORK TOGETHER WHEN WE GIVE THEM TIME", "A FINISHED PUZZLE IS A SMALL VICTORY WORTH ENJOYING",
]

TRIVIA += [
 ("ALPHABET", "What set of letters is used to write a language?", "Alphabet"), ("APRIL", "Which month comes after March?", "April"),
 ("AUTUMN", "What season comes after summer in the Northern Hemisphere?", "Autumn"), ("BALLET", "What dance style is often performed in special shoes?", "Ballet"),
 ("BANANA", "What long yellow fruit grows in bunches?", "Banana"), ("BASEBALL", "What sport uses a bat, ball, and bases?", "Baseball"),
 ("BATTERY", "What provides stored power for many small devices?", "Battery"), ("BEAVER", "What animal is known for building dams?", "Beaver"),
 ("SCOOTER", "What small two-wheeled vehicle has a standing platform and handlebar?", "Scooter"), ("BLOSSOM", "What is a flower on a tree or plant called?", "Blossom"),
 ("CALENDAR", "What chart shows days, weeks, and months?", "Calendar"), ("CANDLE", "What wax item gives light when its wick is lit?", "Candle"),
 ("CARROT", "What orange root vegetable is often crunchy?", "Carrot"), ("CATERPILLAR", "What larval insect may change into a butterfly?", "Caterpillar"),
 ("CEREAL", "What breakfast food is often served with milk?", "Cereal"), ("CHIMNEY", "What structure carries smoke away from a fireplace?", "Chimney"),
 ("CHOCOLATE", "What sweet treat is commonly made from cocoa?", "Chocolate"), ("CINEMA", "What place is made for watching films?", "Cinema"),
 ("CLOVER", "What small plant is often linked with good luck?", "Clover"), ("COCONUT", "What large tropical fruit has a hard shell?", "Coconut"),
 ("CRICKET", "What insect is known for its chirping sound?", "Cricket"), ("CUPCAKE", "What small frosted cake is baked in a paper liner?", "Cupcake"),
 ("DAFFODIL", "What spring flower is often yellow and trumpet shaped?", "Daffodil"), ("DOLPHIN", "What intelligent marine mammal is known for leaping?", "Dolphin"),
 ("DRUMMER", "What musician plays drums?", "Drummer"), ("EAGLE", "What large bird of prey is known for sharp vision?", "Eagle"),
 ("EARTH", "What planet do people live on?", "Earth"), ("ELEPHANT", "What large land animal has a trunk?", "Elephant"),
 ("EMERALD", "What green gemstone is one of the traditional precious stones?", "Emerald"), ("FALCON", "What fast bird of prey is often used in falconry?", "Falcon"),
 ("FEATHER", "What covers the body of a bird?", "Feather"), ("FIREWORK", "What colorful display is often seen during celebrations?", "Firework"),
 ("FISHING", "What activity uses a line and hook to catch fish?", "Fishing"), ("FLAMINGO", "What pink wading bird often stands on one leg?", "Flamingo"),
 ("FOOTBALL", "What team sport is played with an oval ball in the United States?", "Football"), ("FROG", "What amphibian begins life as a tadpole?", "Frog"),
 ("GARDEN", "What planted area can grow flowers, herbs, or vegetables?", "Garden"), ("GLOBE", "What round model represents Earth?", "Globe"),
 ("GOLDFISH", "What small orange fish is often kept in a home aquarium?", "Goldfish"), ("GRAPE", "What small fruit often grows in clusters on vines?", "Grape"),
 ("HAMMER", "What tool drives nails into wood?", "Hammer"), ("HARMONICA", "What small instrument is played by blowing into it?", "Harmonica"),
 ("HELICOPTER", "What aircraft uses rotating blades to lift off?", "Helicopter"), ("HIKING", "What activity involves walking on trails?", "Hiking"),
 ("HOSPITAL", "What place provides medical care for patients?", "Hospital"), ("ICEBERG", "What large floating mass of ice breaks from a glacier?", "Iceberg"),
 ("INSECT", "What six-legged animal group includes ants and butterflies?", "Insect"), ("JELLYFISH", "What ocean animal has a soft bell-shaped body and tentacles?", "Jellyfish"),
 ("JOURNAL", "What book can be used to record daily thoughts?", "Journal"), ("KITCHEN", "What room is used for preparing meals?", "Kitchen"),
 ("LAVENDER", "What fragrant purple flowering herb is used in gardens?", "Lavender"), ("LEMON", "What sour yellow citrus fruit is used in drinks?", "Lemon"),
 ("LIZARD", "What scaled reptile often has four legs and a long tail?", "Lizard"), ("LOCOMOTIVE", "What powered vehicle pulls a train?", "Locomotive"),
 ("MARATHON", "What long-distance running race is about 26.2 miles?", "Marathon"), ("MEADOW", "What open field is often covered in grass and wildflowers?", "Meadow"),
 ("MOON", "What natural object orbits Earth?", "Moon"), ("MOUNTAIN", "What very high natural landform rises above surrounding land?", "Mountain"),
 ("MUSHROOM", "What fungus often has a cap and stem?", "Mushroom"), ("NEST", "What structure do many birds build for eggs?", "Nest"),
 ("NEWSPAPER", "What printed publication reports current events?", "Newspaper"), ("OATMEAL", "What warm breakfast food is made from oats?", "Oatmeal"),
 ("ORCHID", "What flowering plant is known for many colorful varieties?", "Orchid"), ("ORIGAMI", "What art form folds paper into shapes?", "Origami"),
 ("PAINTBRUSH", "What tool spreads paint onto a surface?", "Paintbrush"), ("PANCAKE", "What flat breakfast cake is often served with syrup?", "Pancake"),
 ("PARROT", "What colorful bird can mimic human sounds?", "Parrot"), ("PEACOCK", "What bird is known for a large fan of colorful tail feathers?", "Peacock"),
 ("PEARL", "What smooth gem can form inside certain shells?", "Pearl"),
]

# Additional original general-knowledge entries give the automated Scramble +
# Trivia library enough clean depth for a 100-puzzle Signature Edition.
TRIVIA += [
 ("ACROBAT", "What performer may balance, tumble, or swing high above a circus ring?", "Acrobat"),
 ("ARCHITECTURE", "What field is concerned with designing buildings and structures?", "Architecture"),
 ("BLUEPRINT", "What detailed drawing is used to guide the construction of a building?", "Blueprint"),
 ("BROCCOLI", "What green vegetable has a tree-like cluster of florets?", "Broccoli"),
 ("CAMPGROUND", "What prepared outdoor area offers places for tents or RVs?", "Campground"),
 ("CHESSBOARD", "What checkered board is used for a game with kings and queens?", "Chessboard"),
 ("CLOCKTOWER", "What tall structure often holds a large public clock?", "Clocktower"),
 ("COMET", "What icy object can grow a glowing tail as it travels near the Sun?", "Comet"),
 ("DIAMOND", "What very hard gemstone is traditionally associated with an April birthstone?", "Diamond"),
 ("ELEVATOR", "What enclosed platform carries people between floors in a building?", "Elevator"),
 ("FOUNTAIN", "What decorative feature sprays or flows water in a park or courtyard?", "Fountain"),
 ("GARDENER", "What person tends plants, flowers, or vegetables?", "Gardener"),
 ("HARMONY", "What word describes notes that sound pleasing when played together?", "Harmony"),
 ("INVENTION", "What is a newly created device, method, or idea called?", "Invention"),
 ("JELLYBEAN", "What small bean-shaped candy has a chewy center?", "Jellybean"),
 ("KAYAK", "What narrow small boat is paddled while the rider sits low to the water?", "Kayak"),
 ("LABYRINTH", "What maze-like network of winding paths is designed to be explored?", "Labyrinth"),
 ("MICROSCOPE", "What instrument makes tiny objects appear much larger?", "Microscope"),
 ("OBSERVATORY", "What building is designed for studying stars and planets with telescopes?", "Observatory"),
 ("PALETTE", "What flat board is used by an artist to hold and mix paint?", "Palette"),
 ("QUICKSAND", "What loose wet sand can make walking difficult?", "Quicksand"),
 ("RAILROAD", "What network of tracks is used by trains?", "Railroad"),
 ("SCULPTURE", "What three-dimensional artwork may be carved, modeled, or cast?", "Sculpture"),
 ("TORNADO", "What violently rotating column of air reaches from a storm cloud toward the ground?", "Tornado"),
 ("UNICORN", "What legendary horse-like creature is often pictured with one horn?", "Unicorn"),
 ("VINEYARD", "What planted area grows grapes for eating or making wine?", "Vineyard"),
 ("WILDFLOWER", "What flower grows naturally without being deliberately planted in a garden?", "Wildflower"),
 ("YOYO", "What toy moves down and up on a string wrapped around an axle?", "Yoyo"),
 ("ZOOKEEPER", "What person cares for animals in a zoo?", "Zookeeper"),
 ("BANDSTAND", "What raised outdoor platform is often used by musicians in a park?", "Bandstand"),
]

NAME_IDEAS = {
 "Sudoku": [("The Quiet Grid", "100 Number, Letter & Shape Sudoku Puzzles for Focused Fun"), ("Nine Symbols, One Solution", "100 Fresh Sudoku Challenges in Numbers, Letters & Shapes"), ("The Pencil-Ready Sudoku Book", "100 Satisfying Logic Puzzles with Complete Solutions"), ("Grid by Grid", "100 Number, Letter & Shape Sudoku Puzzles for Every Day"), ("The Sunday Table Sudoku Book", "100 Relaxing Logic Puzzles for a Clearer, Calmer Mind")],
 "Cryptogram": [("Cipher & Candlelight", "60 Original Cryptograms for Cozy Code-Breaking Sessions"), ("The Hidden Letter Society", "60 Clever Cryptograms for Curious Minds and Quiet Evenings"), ("Ink, Clues & Codes", "60 Satisfying Cryptogram Puzzles with Full Solutions"), ("The Secret Sentence Book", "60 Original Code-Breaking Puzzles for Puzzle Lovers"), ("Decode the Day", "60 Fresh Cryptograms for Focus, Fun, and a Little Mystery")],
 "Word Scramble + Trivia": [("The Curiosity Cabinet", "60 Word Scrambles with Fact Clues and Answers"), ("Letters, Laughs & Little Facts", "60 Word Games with Quick Fact Clues"), ("The Big Brain-Break Book", "60 Word Scrambles and Knowledge Clues for Curious Minds"), ("Unmix the Mystery", "60 Playful Word Scrambles with Fact Clues"), ("The Puzzle Break Companion", "60 Clever Word Games with Quick Fact Clues")],
 "Mixed Brain Games": [("The Everyday Brain Games Collection", "60 Sudoku, Cryptograms, and Word Scramble Challenges"), ("The Big Variety Puzzle Book", "60 Logic, Code-Breaking, and Word-Game Challenges"), ("A Little Bit of Everything", "60 Brain Games for Calm Focus and Satisfying Breaks")],
}

THEMED_NAME_IDEAS = {
 "Space & Astronomy": {
   "Cryptogram": [("Celestial Ciphers", "60 Space-Themed Cryptograms for Curious Stargazers"), ("Orbit of Secrets", "60 Cosmic Code-Breaking Puzzles with Full Solutions"), ("The Stargazer's Cipher Book", "60 Astronomical Cryptograms for a Brilliant Brain Break")],
   "Word Scramble + Trivia": [("The Cosmic Curiosity Book", "60 Space Word Scrambles with Astronomy Clues"), ("Stars, Planets & Puzzles", "60 Space Games for Curious Stargazers"), ("Launch Into Space Facts", "60 Astronomical Word Games with Quick Clues")],
 },
 "Garden & Growing": {
   "Cryptogram": [("The Secret Garden Cipher Book", "60 Blooming Cryptograms for Peaceful Puzzle Time"), ("Seeds, Stems & Secrets", "60 Garden-Themed Code-Breaking Puzzles"), ("The Green Thumb Code", "60 Fresh Cryptograms for Garden Lovers")],
   "Word Scramble + Trivia": [("The Garden Curiosity Book", "60 Growing-Themed Word Scrambles with Fact Clues"), ("Bloom, Buzz & Brain Games", "60 Garden Word Games for Relaxed Puzzle Time"), ("Dig Into the Details", "60 Garden Scrambles with Fact Clues and Answers")],
 },
 "Travel & Adventure": {
   "Cryptogram": [("Passport to Puzzles", "60 Travel-Themed Cryptograms for Curious Explorers"), ("Routes, Maps & Secret Codes", "60 Adventure Cryptograms with Complete Solutions"), ("The Wandering Cipher Book", "60 Clever Code-Breaking Puzzles for Travel Lovers")],
   "Word Scramble + Trivia": [("The Curious Traveler's Puzzle Book", "60 Word Scrambles with Travel Fact Clues"), ("Maps, Miles & Mind Games", "60 Adventure Word Games for Armchair Explorers"), ("The Great Getaway Game Book", "60 Travel Scrambles with Quick Clues and Answers")],
 },
 "General Knowledge & Curiosity": {
   "Word Scramble + Trivia": [("The Curiosity Cabinet", "100 Word Scrambles with General Knowledge Clues"), ("The Everyday Puzzle Break", "100 Bright Word Games with Quick Fact Clues"), ("Letters, Facts & Little Wins", "100 Word Scrambles with Fact Clues for Curious Minds")],
 },
}

def name_ideas_for(kind: str, theme: str, count: int) -> list[tuple[str, str]]:
    """Return polished, on-topic names instead of generic word swaps."""
    source=THEMED_NAME_IDEAS.get(theme, {}).get(kind, NAME_IDEAS[kind])
    return [(title_text, re.sub(r"\b(?:60|100)\b", str(count), subtitle)) for title_text, subtitle in source]

def production_proof_gate(folder: Path, kind: str, title_text: str, subtitle: str, count: int, pages: int) -> tuple[bool, str]:
    """Final automatic guard: package, promises, and physical files agree."""
    checks: list[tuple[bool, str]] = []
    required=("interior.pdf","front_cover.png","kdp_full_wrap.pdf","kdp_full_wrap_preview.png","KDP_LISTING_KIT.txt","PUBLISHER_PREFLIGHT.txt")
    checks += [(package_file(folder, name).is_file(), f"Package contains {name}.") for name in required]
    try:
        from pypdf import PdfReader
        actual=len(PdfReader(str(package_file(folder, "interior.pdf"))).pages)
        checks.append((actual == pages and actual >= 24 and actual % 2 == 0, f"Interior has {actual} pages and meets the even 24-page minimum."))
    except Exception as exc: checks.append((False, f"Could not inspect interior PDF: {exc}"))
    kit_path=package_file(folder, "KDP_LISTING_KIT.txt")
    kit=kit_path.read_text(encoding="utf-8") if kit_path.is_file() else ""
    checks.append((title_text in kit and subtitle in kit and str(count) in kit, "Listing matches title, subtitle, and puzzle count."))
    checks.append(("Trim size: 8.5 x 11" in kit, "Listing records the exact trim size."))
    try:
        from PIL import Image
        with Image.open(package_file(folder, "front_cover.png")) as image:
            width, height = image.size
        checks.append((width >= 2550 and height >= 3300, f"Front cover is print-sized ({width} x {height} pixels)."))
    except Exception as exc:
        checks.append((False, f"Could not inspect front-cover size: {exc}"))
    if kind in ("Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"):
        library_report = package_file(folder, "CONTENT_LIBRARY_VERIFICATION.txt")
        library_text = library_report.read_text(encoding="utf-8") if library_report.is_file() else ""
        checks.append(("Library result: PASS" in library_text, "Checked content library passed its duplicate and capacity review."))
    if kind == "Sudoku": checks.append(("letter, and shape" in kit.lower(), "Sudoku listing promises the actual number, letter, and shape games."))
    passed=all(ok for ok,_ in checks); score=sum(1 for ok,_ in checks if ok)*100//len(checks)
    lines=["PRODUCTION PROOF GATE", "="*22, f"Result: {'READY FOR KDP PRINT PREVIEWER' if passed else 'FIX BEFORE UPLOAD'}", f"Automated score: {score}/100", ""]
    lines += [f"{'PASS' if ok else 'BLOCK'} - {message}" for ok,message in checks]
    lines += ["", "Final human step: Open KDP Print Previewer and correct every issue it reports before approving publication."]
    return passed, "\n".join(lines)+"\n"

def fonts():
    # register_pdf_font skips aliases that are already registered and quietly
    # leaves unresolvable ones alone, matching the old skip-if-missing behaviour.
    for alias, family in BOOK_FONT_FAMILIES.items():
        register_pdf_font(alias, pdf_font_candidates(family))

def content_packs() -> dict:
    """Return production-approved puzzle content from every trusted library.

    Generated candidate files are deliberately ignored.  Supplemental packs
    are merged only when the file carries the explicit production approval
    status written by the editorial promotion tool.
    """
    try:
        data=json.loads(CONTENT_LIBRARY.read_text(encoding="utf-8")); packs=data.get("packs", {})
        packs = dict(packs) if isinstance(packs, dict) else {}
    except (OSError, json.JSONDecodeError):
        packs = {}
    try:
        supplemental = json.loads(EDITORIAL_CONTENT_LIBRARY.read_text(encoding="utf-8"))
        if supplemental.get("status") == "APPROVED_FOR_LOCAL_PRODUCTION":
            for name, pack in supplemental.get("packs", {}).items():
                if not isinstance(pack, dict):
                    continue
                current = dict(packs.get(name, {}))
                for field in ("cryptograms", "trivia"):
                    incoming = pack.get(field)
                    if isinstance(incoming, list):
                        current[field] = list(incoming)
                packs[name] = current
    except (OSError, json.JSONDecodeError):
        pass
    return packs

def master_topic_words(theme: str) -> list[str]:
    """Read only the reviewed (proven) vocabulary already approved for books."""
    try:
        data=json.loads(MASTER_WORD_BANK.read_text(encoding="utf-8"))
        words=[]
        packs=data.get("topic_packs", {}) if isinstance(data.get("topic_packs"), dict) else {}
        source_topics=[]
        for pack in PRODUCTION_FAMILY_PACKS.get(theme, ()): source_topics.extend(packs.get(pack, []))
        source_topics = source_topics or list(THEME_TOPIC_MAP.get(theme, ()))
        for topic in source_topics:
            words.extend(data.get("topics", {}).get(topic, []))
        return list(dict.fromkeys(str(word).strip().upper() for word in words if str(word).strip().isalpha() and 4 <= len(str(word).strip()) <= 18))
    except (OSError, json.JSONDecodeError): return []

def themed_cryptograms(theme: str) -> list[str]:
    """Use authored prompts only; dictionary terms are not finished messages.

    Earlier releases counted word-substitution templates as original themed
    cryptograms.  Those sentences often read nonsensically despite passing
    format and uniqueness checks, so they cannot contribute to capacity.
    """
    mechanical = (
        "CURIOSITY MAKES ", "A CAREFUL LOOK AT ", " CAN OPEN A NEW PATH TO ",
        " IS ONE PART OF A BIGGER STORY", " INVITES PATIENT THINKING",
        " PUZZLE CAN BEGIN WITH ", "CURIOUS MINDS NOTICE ",
        " STORY HAS ROOM FOR ", "THE STORY OF ",
        "CURIOUS MINDS KEEP LOOKING TOWARD ", "A SPACE EXPLORER CAN LEARN FROM ",
        "A HEALTHY GARDEN MAKES ROOM FOR ", "PATIENT GROWERS LEARN ABOUT ",
        "EVERY SEASON CAN TEACH US ABOUT ", "A GOOD JOURNEY CAN LEAD US TOWARD ",
        "CURIOUS TRAVELERS MAKE TIME FOR ", "AN ADVENTURE OFTEN STARTS WITH ",
    )
    prompts = []
    seen = set()
    for item in content_packs().get(theme, {}).get("cryptograms", []):
        prompt = str(item).strip().upper()
        if prompt and prompt not in seen and not any(marker in prompt for marker in mechanical):
            prompts.append(prompt)
            seen.add(prompt)
    return prompts

CURATED_THEMED_TRIVIA = {
    "Travel & Adventure": [
        ("HIGHWAY", "What major road is designed for fast travel between cities?", "Highway"),
        ("ROADMAP", "What printed guide shows roads and driving routes?", "Road map"),
        ("RESTSTOP", "What roadside place lets travelers pause during a long drive?", "Rest stop"),
        ("CAMPSITE", "What reserved outdoor spot is used for a tent or camper?", "Campsite"),
        ("MOTEL", "What roadside lodging is designed for motorists?", "Motel"),
        ("TOLLBOOTH", "Where is a road-use fee traditionally collected?", "Tollbooth"),
        ("FREEWAY", "What divided road usually has controlled entrances and exits?", "Freeway"),
        ("TRAILHEAD", "What do hikers call the starting point of a trail?", "Trailhead"),
        ("BACKPACK", "What bag is carried on the back during a hike?", "Backpack"),
        ("SUITCASE", "What handled case is commonly packed for a trip?", "Suitcase"),
        ("BOARDING", "What process allows passengers to enter a plane or ship?", "Boarding"),
        ("RUNWAY", "What paved strip is used by airplanes for takeoff and landing?", "Runway"),
        ("TERMINAL", "What airport building serves arriving and departing passengers?", "Terminal"),
        ("LANDMARK", "What recognizable place helps identify a destination?", "Landmark"),
        ("POSTCARD", "What picture card is often mailed from a vacation?", "Postcard"),
        ("SOUVENIR", "What keepsake is brought home from a trip?", "Souvenir"),
        ("JOURNEY", "What word means travel from one place to another?", "Journey"),
        ("DETOUR", "What alternate route is taken around a closure?", "Detour"),
        ("MILEAGE", "What measurement records the distance a vehicle has traveled?", "Mileage"),
        ("ROUTE", "What planned path connects a starting point and destination?", "Route"),
        ("BRIDGE", "What structure carries a road or path over an obstacle?", "Bridge"),
        ("TUNNEL", "What passage carries travelers through a mountain or underground?", "Tunnel"),
        ("FERRY", "What boat carries passengers or vehicles across water?", "Ferry"),
        ("CABIN", "What small rustic building often provides wilderness lodging?", "Cabin"),
        ("CAMPGROUND", "What area contains multiple campsites and shared facilities?", "Campground"),
        ("RESERVATION", "What advance booking holds a room, seat, or campsite?", "Reservation"),
        ("DESTINATION", "What is the place a traveler plans to reach?", "Destination"),
        ("NAVIGATION", "What skill involves planning and following a route?", "Navigation"),
        ("ITINERARY", "What document lists a trip's planned stops and schedule?", "Itinerary"),
        ("PASSPORT", "What official document identifies a traveler crossing international borders?", "Passport"),
        ("LUGGAGE", "What collective word describes bags taken on a trip?", "Luggage"),
        ("CHECKIN", "What arrival step confirms a hotel stay or airline booking?", "Check-in"),
        ("OVERLOOK", "What scenic viewpoint looks out across a landscape?", "Overlook"),
        ("WAYPOINT", "What marked location helps divide a route into stages?", "Waypoint"),
        ("EXCURSION", "What short trip is taken for sightseeing or recreation?", "Excursion"),
        ("GUIDEBOOK", "What reference book gives advice about a destination?", "Guidebook"),
        ("AIRPORT", "What travel hub has terminals, gates, and runways?", "Airport"),
        ("AIRLINE", "What company transports passengers by airplane?", "Airline"),
        ("TICKET", "What document proves a traveler has paid for a seat or admission?", "Ticket"),
        ("HOTEL", "What business provides rooms for overnight guests?", "Hotel"),
        ("HOSTEL", "What budget lodging often offers shared rooms to travelers?", "Hostel"),
        ("CRUISE", "What vacation journey takes place aboard a passenger ship?", "Cruise"),
        ("HARBOR", "What sheltered body of water provides a safe place for boats?", "Harbor"),
        ("BAGGAGE", "What word describes suitcases checked for a flight?", "Baggage"),
        ("CUSTOMS", "What border checkpoint reviews goods entering a country?", "Customs"),
        ("VISA", "What official permission may be required to enter another country?", "Visa"),
        ("LAYOVER", "What waiting period occurs between connecting flights?", "Layover"),
        ("DEPARTURE", "What word describes the act or scheduled time of leaving?", "Departure"),
        ("ARRIVAL", "What word describes reaching a destination?", "Arrival"),
        ("RENTALCAR", "What temporary vehicle can a traveler hire at a destination?", "Rental car"),
        ("SIGHTSEEING", "What activity involves visiting notable places at a destination?", "Sightseeing"),
        ("TOURGUIDE", "Who leads visitors and explains a destination's important sights?", "Tour guide"),
        ("SCENICROUTE", "What kind of road is chosen for attractive views?", "Scenic route"),
        ("NATIONALPARK", "What protected public land preserves scenery and wildlife?", "National park"),
        ("PICNIC", "What outdoor meal is packed and eaten away from home?", "Picnic"),
        ("HIKINGBOOTS", "What sturdy footwear protects feet on a trail?", "Hiking boots"),
        ("TENT", "What portable fabric shelter is used while camping?", "Tent"),
        ("FLASHLIGHT", "What handheld light helps travelers see after dark?", "Flashlight"),
        ("BINOCULARS", "What optical tool makes distant scenery appear closer?", "Binoculars"),
        ("TRAVELER", "What do we call a person making a journey?", "Traveler"),
        ("GASSTATION", "What roadside business sells fuel for a vehicle?", "Gas station"),
        ("FUELPUMP", "What machine dispenses gasoline into a vehicle?", "Fuel pump"),
        ("ODOMETER", "What dashboard instrument records a vehicle's total distance traveled?", "Odometer"),
        ("SPEEDOMETER", "What dashboard instrument shows how fast a vehicle is moving?", "Speedometer"),
        ("MILEMARKER", "What numbered roadside sign shows a location along a highway?", "Mile marker"),
        ("RESTAREA", "What highway stop offers travelers a place to pause and use facilities?", "Rest area"),
        ("SHOULDER", "What paved strip beside a road provides space to stop in an emergency?", "Shoulder"),
        ("EXITRAMP", "What curved road leads traffic off a highway?", "Exit ramp"),
        ("ONRAMP", "What road allows a driver to enter a highway?", "On-ramp"),
        ("INTERSTATE", "What major United States highway system connects states?", "Interstate"),
        ("ROUNDABOUT", "What circular intersection directs traffic around a central island?", "Roundabout"),
        ("CROSSWALK", "What marked part of a road is intended for people crossing on foot?", "Crosswalk"),
        ("TRAFFICLIGHT", "What signal uses colored lights to control traffic at an intersection?", "Traffic light"),
        ("SPEEDLIMIT", "What posted number shows the maximum lawful driving speed?", "Speed limit"),
        ("SEATBELT", "What safety restraint should a traveler fasten in a vehicle?", "Seat belt"),
        ("WINDSHIELD", "What front glass panel protects a car's occupants from wind and debris?", "Windshield"),
        ("WIPERS", "What moving blades clear rain from a windshield?", "Wipers"),
        ("SPARETIRE", "What extra wheel can replace a flat tire during a trip?", "Spare tire"),
        ("TRUNK", "What enclosed compartment behind a car's passenger area holds luggage?", "Trunk"),
        ("ROADSIGN", "What roadside display gives drivers directions or warnings?", "Road sign"),
        ("PARKINGLOT", "What marked area holds vehicles while their drivers are away?", "Parking lot"),
        ("TOLLROAD", "What highway requires a fee for use?", "Toll road"),
        ("CARPOOL", "What is a shared car trip by people traveling together called?", "Carpool"),
        ("SHUTTLE", "What vehicle makes repeated short trips between two locations?", "Shuttle"),
        ("CHARTERBUS", "What hired bus carries a group on a planned trip?", "Charter bus"),
        ("TRAINSTATION", "What building or platform is used to board a train?", "Train station"),
        ("RAILWAY", "What network of tracks carries trains between places?", "Railway"),
        ("PLATFORM", "What raised area beside train tracks is used for boarding?", "Platform"),
        ("CONDUCTOR", "What railway worker may check tickets and assist passengers?", "Conductor"),
        ("TIMETABLE", "What schedule lists planned arrival and departure times?", "Timetable"),
        ("TRANSFER", "What change from one bus or train to another continues a journey?", "Transfer"),
        ("SUBWAY", "What urban rail service often travels through underground tunnels?", "Subway"),
        ("TRAM", "What passenger vehicle runs on tracks along city streets?", "Tram"),
        ("FERRYBOAT", "What watercraft carries people or vehicles on a regular crossing?", "Ferryboat"),
        ("MARINA", "What harbor facility offers berths and services for recreational boats?", "Marina"),
        ("DOCK", "What structure beside the water allows boats to tie up?", "Dock"),
        ("LIFEJACKET", "What wearable flotation device helps keep a person afloat?", "Life jacket"),
        ("BOARDWALK", "What raised walkway often follows a beach or waterfront?", "Boardwalk"),
        ("BEACHBAG", "What bag carries towels and supplies for a day by the shore?", "Beach bag"),
        ("SUNSCREEN", "What lotion helps protect skin from the sun's ultraviolet rays?", "Sunscreen"),
        ("UMBRELLA", "What portable canopy offers shade or shelter from rain?", "Umbrella"),
        ("RAINCOVER", "What waterproof layer can protect a backpack in wet weather?", "Rain cover"),
        ("WATERBOTTLE", "What reusable container carries drinking water on a trip?", "Water bottle"),
        ("FIRSTAIDKIT", "What collection of supplies helps treat minor injuries?", "First-aid kit"),
        ("HEADLAMP", "What hands-free light is worn on the head during a hike?", "Headlamp"),
        ("TREKKINGPOLES", "What pair of handheld poles can help a hiker balance on a trail?", "Trekking poles"),
        ("DAYPACK", "What small backpack holds supplies for a short outing?", "Daypack"),
        ("TRAILMAP", "What guide shows paths and junctions in a hiking area?", "Trail map"),
        ("TRAILBLAZE", "What painted mark on a tree or post can identify a hiking route?", "Trail blaze"),
        ("CAMPPERMIT", "What authorization may be required for an overnight stay in a protected area?", "Camp permit"),
        ("PICNICTABLE", "What outdoor table has attached benches for eating a packed meal?", "Picnic table"),
        ("CAMPSHOWER", "What washing facility may be available at a developed campground?", "Camp shower"),
        ("SLEEPINGBAG", "What insulated fabric sack keeps a camper warm at night?", "Sleeping bag"),
        ("TENTPOLE", "What support rod helps give a tent its shape?", "Tent pole"),
        ("TENTSTAKE", "What peg secures a tent or guyline to the ground?", "Tent stake"),
        ("CAMPLANTERN", "What portable lamp lights a campsite after dark?", "Camp lantern"),
        ("COOLER", "What insulated box helps keep food and drinks cold on a trip?", "Cooler"),
        ("TRAVELMUG", "What lidded cup is designed to carry a drink while traveling?", "Travel mug"),
        ("SNACKBOX", "What container keeps small foods together for a journey?", "Snack box"),
        ("ROADSIDE", "What word describes a place located beside a road?", "Roadside"),
        ("MAPLEGEND", "What section of a map explains its symbols?", "Map legend"),
        ("MAPSCALE", "What map feature relates a measured distance to real-world distance?", "Map scale"),
        ("COMPASSROSE", "What map symbol displays the cardinal directions?", "Compass rose"),
        ("NORTHBOUND", "What word describes travel toward the north?", "Northbound"),
        ("SOUTHBOUND", "What word describes travel toward the south?", "Southbound"),
        ("EASTBOUND", "What word describes travel toward the east?", "Eastbound"),
        ("WESTBOUND", "What word describes travel toward the west?", "Westbound"),
        ("BACKROAD", "What smaller road may offer a quieter alternative to a main highway?", "Back road"),
        ("BYPASS", "What route lets travelers go around a town or congested area?", "Bypass"),
        ("ROADWORK", "What temporary construction activity may slow highway traffic?", "Roadwork"),
        ("WELCOME SIGN", "What sign greets travelers entering a town or state?", "Welcome sign"),
        ("SCENICOVERLOOK", "What roadside stopping place gives a wide view of the landscape?", "Scenic overlook"),
        ("VISITORCENTER", "What building offers maps and information at a park or attraction?", "Visitor center"),
        ("TRAILMARKER", "What sign or post identifies a path or its distance?", "Trail marker"),
        ("RANGERSTATION", "What park building is staffed by people who help visitors?", "Ranger station"),
        ("CAMPGROUNDSITE", "What numbered space in a campground is assigned to one camping party?", "Campground site"),
    ],
    "Food & Home": [
        ("SPATULA", "What flat kitchen tool is used to lift or turn food?", "Spatula"),
        ("WHISK", "What wire utensil blends ingredients and adds air?", "Whisk"),
        ("SKILLET", "What shallow frying pan is used on a stovetop?", "Skillet"),
        ("SAUCEPAN", "What deep pan with a handle is used for sauces and liquids?", "Saucepan"),
        ("COLANDER", "What perforated bowl drains water from pasta?", "Colander"),
        ("CUTTINGBOARD", "What flat surface protects a counter while food is chopped?", "Cutting board"),
        ("APRON", "What garment protects clothing while cooking?", "Apron"),
        ("OVENMITT", "What padded glove protects a hand from hot cookware?", "Oven mitt"),
        ("PANTRY", "What cupboard or small room stores dry food?", "Pantry"),
        ("RECIPE", "What set of instructions explains how to prepare a dish?", "Recipe"),
        ("INGREDIENT", "What is one item used to make a recipe?", "Ingredient"),
        ("SIMMER", "What cooking method keeps liquid just below a boil?", "Simmer"),
        ("ROAST", "What method cooks food with dry heat in an oven?", "Roast"),
        ("KNEAD", "What action develops dough by pressing and folding it?", "Knead"),
        ("MARINATE", "What process soaks food in seasoned liquid before cooking?", "Marinate"),
        ("SEASONING", "What ingredient is added to improve a food's flavor?", "Seasoning"),
        ("CASSEROLE", "What baked dish is cooked and served in the same deep pan?", "Casserole"),
        ("BLENDER", "What electric appliance purees or mixes food and drinks?", "Blender"),
        ("TOASTER", "What countertop appliance browns slices of bread?", "Toaster"),
        ("TEAKETTLE", "What vessel heats water for tea?", "Tea kettle"),
        ("NAPKIN", "What cloth or paper square is used at the table?", "Napkin"),
        ("PLACEMAT", "What table covering marks and protects one diner's place?", "Placemat"),
        ("CUPBOARD", "What cabinet is used to store dishes or food?", "Cupboard"),
        ("FREEZER", "What appliance compartment keeps food frozen?", "Freezer"),
        ("REFRIGERATOR", "What appliance keeps perishable food cold?", "Refrigerator"),
        ("DISHWASHER", "What appliance automatically cleans dishes?", "Dishwasher"),
        ("LAUNDRY", "What word describes clothing and linens that need washing?", "Laundry"),
        ("TABLECLOTH", "What fabric covering is spread across a dining table?", "Tablecloth"),
        ("MEASURINGCUP", "What marked container measures ingredient volume?", "Measuring cup"),
        ("ROLLINGPIN", "What cylinder flattens dough?", "Rolling pin"),
        ("POTHOLDER", "What padded square protects hands and counters from hot cookware?", "Potholder"),
        ("LEFTOVERS", "What do we call food saved after a meal?", "Leftovers"),
        ("GROCERIES", "What food and household supplies are bought at a market?", "Groceries"),
        ("COUNTERTOP", "What flat kitchen work surface sits above cabinets?", "Countertop"),
        ("BOOKSHELF", "What piece of furniture holds books?", "Bookshelf"),
        ("VACUUM", "What appliance removes dust and dirt from floors?", "Vacuum"),
        ("MIXINGBOWL", "What deep bowl holds ingredients while they are combined?", "Mixing bowl"),
        ("LADLE", "What long-handled utensil serves soup or sauce?", "Ladle"),
        ("TONGS", "What hinged utensil grips and lifts food?", "Tongs"),
        ("PEELER", "What tool removes the skin from vegetables?", "Peeler"),
        ("GRATER", "What kitchen tool shreds cheese or vegetables against a rough surface?", "Grater"),
        ("THERMOMETER", "What tool checks whether food has reached a safe temperature?", "Thermometer"),
        ("BAKINGDISH", "What oven-safe container is used for casseroles and desserts?", "Baking dish"),
        ("BAKINGSHEET", "What flat metal pan holds cookies or roasted vegetables?", "Baking sheet"),
        ("STOVETOP", "What cooking surface contains burners above an oven or counter?", "Stovetop"),
        ("MICROWAVE", "What appliance heats food using electromagnetic energy?", "Microwave"),
        ("COFFEEMAKER", "What countertop appliance brews coffee?", "Coffee maker"),
        ("KITCHENTIMER", "What device counts down cooking time?", "Kitchen timer"),
        ("CABINET", "What built-in storage unit has shelves behind doors?", "Cabinet"),
        ("CLOSET", "What enclosed storage space holds clothing or household items?", "Closet"),
        ("BEDROOM", "What room is primarily used for sleeping?", "Bedroom"),
        ("LIVINGROOM", "What shared room is commonly used for relaxing and entertaining?", "Living room"),
        ("DOORMAT", "What mat near an entrance helps clean shoes?", "Doormat"),
        ("CURTAINS", "What fabric panels cover and decorate windows?", "Curtains"),
        ("CUSHION", "What soft pad adds comfort to a chair or sofa?", "Cushion"),
        ("BLANKET", "What warm covering is used on a bed or sofa?", "Blanket"),
        ("HAMPER", "What container holds clothing waiting to be washed?", "Hamper"),
        ("DUSTPAN", "What shallow pan collects dirt swept from a floor?", "Dustpan"),
        ("BROOM", "What long-handled household tool sweeps floors?", "Broom"),
        ("SPONGE", "What absorbent item is used to wash dishes and wipe surfaces?", "Sponge"),
    ],
    "School & Vocabulary": [
        ("LIBRARY", "What school place lends books for reading and research?", "Library"),
        ("DICTIONARY", "What reference book explains word meanings and spellings?", "Dictionary"),
        ("THESAURUS", "What reference book lists synonyms and related words?", "Thesaurus"),
        ("SYLLABLE", "What do we call one spoken beat within a word?", "Syllable"),
        ("SYNONYM", "What is a word with the same or nearly the same meaning as another?", "Synonym"),
        ("ANTONYM", "What is a word with the opposite meaning of another?", "Antonym"),
        ("PREFIX", "What word part is added to the beginning of a base word?", "Prefix"),
        ("SUFFIX", "What word part is added to the end of a base word?", "Suffix"),
        ("NOUN", "What part of speech names a person, place, thing, or idea?", "Noun"),
        ("VERB", "What part of speech expresses an action or state of being?", "Verb"),
        ("ADJECTIVE", "What part of speech describes a noun?", "Adjective"),
        ("PARAGRAPH", "What group of sentences develops one main idea?", "Paragraph"),
        ("CHAPTER", "What numbered or titled division organizes a longer book?", "Chapter"),
        ("NOTEBOOK", "What bound set of blank pages is used for class notes?", "Notebook"),
        ("HOMEWORK", "What schoolwork is assigned to be completed outside class?", "Homework"),
        ("RESEARCH", "What process gathers reliable information about a question?", "Research"),
        ("SCIENCE", "What subject studies the natural world through observation and experiments?", "Science"),
        ("HISTORY", "What subject studies people and events from the past?", "History"),
        ("GEOGRAPHY", "What subject studies places, environments, and Earth's surface?", "Geography"),
        ("FRACTION", "What number represents part of a whole?", "Fraction"),
    ],
    "Nature & Outdoors": [
        ("TRAIL", "What marked path guides hikers through an outdoor area?", "Trail"),
        ("FOREST", "What large area is covered mainly by trees?", "Forest"),
        ("MEADOW", "What open grassy area is often surrounded by woodland?", "Meadow"),
        ("WATERFALL", "What feature forms where water drops over a steep edge?", "Waterfall"),
        ("RIVER", "What natural flowing body of water moves toward a lake or ocean?", "River"),
        ("CANYON", "What deep valley has steep sides often carved by water?", "Canyon"),
        ("SUMMIT", "What is the highest point of a mountain called?", "Summit"),
        ("WILDLIFE", "What collective word describes animals living in nature?", "Wildlife"),
        ("EVERGREEN", "What kind of tree keeps green leaves or needles through winter?", "Evergreen"),
        ("WILDFLOWER", "What flowering plant grows naturally without cultivation?", "Wildflower"),
        ("FOOTPRINT", "What impression can an animal or hiker leave in soft ground?", "Footprint"),
        ("BINOCULARS", "What tool helps outdoor observers see distant wildlife?", "Binoculars"),
        ("COMPASS", "What navigation tool points toward magnetic north?", "Compass"),
        ("BACKPACK", "What bag carries water and supplies on a hike?", "Backpack"),
        ("CAMPSITE", "What designated place is used for outdoor overnight stays?", "Campsite"),
        ("RANGER", "Who helps protect and explain a park or natural area?", "Ranger"),
        ("HABITAT", "What natural home provides an organism with food and shelter?", "Habitat"),
        ("WETLAND", "What water-saturated ecosystem supports specialized plants and animals?", "Wetland"),
        ("SUNRISE", "What daily event occurs when the Sun first appears above the horizon?", "Sunrise"),
        ("STARGAZING", "What nighttime activity involves observing stars and planets?", "Stargazing"),
    ],
}


# A road-trip promise needs a narrower source than the general travel pack.
# Reuse only already-reviewed highway, vehicle, map, camping, and roadside
# clues; exclude air, cruise, border, and international travel entries.
ROAD_TRIP_WORDS = {
    "HIGHWAY", "ROADMAP", "RESTSTOP", "CAMPSITE", "MOTEL", "TOLLBOOTH", "FREEWAY",
    "TRAILHEAD", "BACKPACK", "DETOUR", "MILEAGE", "ROUTE", "BRIDGE", "RENTALCAR",
    "SCENICROUTE", "NATIONALPARK", "PICNIC", "HIKINGBOOTS", "TENT", "FLASHLIGHT",
    "BINOCULARS", "GASSTATION", "FUELPUMP", "ODOMETER", "SPEEDOMETER", "MILEMARKER",
    "RESTAREA", "SHOULDER", "EXITRAMP", "ONRAMP", "INTERSTATE", "ROUNDABOUT",
    "TRAFFICLIGHT", "SPEEDLIMIT", "SEATBELT", "WINDSHIELD", "WIPERS", "SPARETIRE",
    "TRUNK", "ROADSIGN", "PARKINGLOT", "TOLLROAD", "CARPOOL", "CHARTERBUS",
    "WATERBOTTLE", "FIRSTAIDKIT", "HEADLAMP", "DAYPACK", "TRAILMAP", "CAMPPERMIT",
    "SLEEPINGBAG", "CAMPLANTERN", "COOLER", "TRAVELMUG", "ROADSIDE", "MAPLEGEND",
    "MAPSCALE", "COMPASSROSE", "BACKROAD", "BYPASS", "ROADWORK", "SCENICOVERLOOK",
    "VISITORCENTER", "RANGERSTATION", "PICNICTABLE", "TENTPOLE", "TENTSTAKE",
}
CURATED_THEMED_TRIVIA["Road Trips & Highways"] = [
    item for item in CURATED_THEMED_TRIVIA["Travel & Adventure"] if item[0] in ROAD_TRIP_WORDS
]


def _real_trivia_entry(item) -> tuple[str, str, str] | None:
    """Return one publishable entry; reject the former numbered placeholders."""
    if not isinstance(item, (list, tuple)) or len(item) != 3:
        return None
    word, question, answer = (str(value).strip() for value in item)
    normalized = re.sub(r"[^A-Za-z]", "", word).upper()
    lowered = question.casefold()
    if (not normalized or len(normalized) < 4 or len(normalized) > 21 or not answer
            or not question.endswith("?") or "topic-related word" in lowered
            or re.search(r"\bchallenge\s+\d+\b", lowered)):
        return None
    return normalized, question, answer


def themed_trivia(theme: str) -> list[tuple[str, str, str]]:
    """Combine only real reviewed prompts that honestly match the chosen theme."""
    candidates = list(content_packs().get(theme, {}).get("trivia", []))
    candidates.extend(CURATED_THEMED_TRIVIA.get(theme, []))
    prompts, used_words, used_questions = [], set(), set()
    for raw in candidates:
        item = _real_trivia_entry(raw)
        if not item:
            continue
        word, question, answer = item
        if word in used_words or question.casefold() in used_questions:
            continue
        prompts.append((word, question, answer))
        used_words.add(word); used_questions.add(question.casefold())
    return prompts


def scramble_clue_share(theme: str) -> float:
    """Measure whether questions clue the scrambled word or have distinct answers."""
    source = TRIVIA if theme in ("General Starter", "General Knowledge & Curiosity") else themed_trivia(theme)
    if not source:
        return 0.0
    return sum(scramble_answer_parts(word, answer)[1] is None for word, _question, answer in source) / len(source)


def validate_scramble_promise(kind: str, theme: str, title_text: str, subtitle: str) -> None:
    """Do not sell clue-led scrambles as a separate trivia quiz."""
    if kind not in ("Word Scramble + Trivia", "Mixed Brain Games") or scramble_clue_share(theme) < 0.8:
        return
    promised = f"{title_text} {subtitle}"
    if re.search(r"\b(?:trivia|quiz)\s+(?:challenges?|questions?|puzzles?|games?)\b", promised, re.I):
        raise ValueError(
            "This content pack uses fact questions mainly as clues to the scrambled words, "
            "not as a separate trivia quiz. Use wording such as 'word scrambles with fact clues and answers'."
        )

def pack_capacity(kind: str, theme: str) -> int:
    # The creation gate uses content_check(), including both themed sections
    # of a Mixed book.  The UI must report that same reviewed capacity instead
    # of counting the general-purpose library for every Mixed theme.
    if kind in ("Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"):
        checked, _detail, capacity = content_check(kind, theme)
        return capacity if checked else 0
    return 0

def buffered_capacity_needed(count: int) -> int:
    return max(MIN_VERIFIED_LIBRARY, math.ceil(count * CONTENT_BUFFER))


def required_content_for_book(kind: str, count: int) -> int:
    """Return the number of unique entries the finished book will actually consume."""
    return math.ceil(count / 3) if kind == "Mixed Brain Games" else count


def back_cover_copy(kind: str, theme: str, count: int, difficulty: str) -> tuple[str, str]:
    """Create useful, truthful back-cover copy from the same facts as the interior."""
    theme_name = theme if theme not in {"", "General Starter"} else "general knowledge"
    openings = {
        "Sudoku": f"Settle into {count} satisfying Sudoku puzzles inspired by {theme_name}. Number, letter, and themed shape games add variety while preserving the familiar logic rules.",
        "Cryptogram": f"Decode {count} clever messages connected to {theme_name}. Follow letter patterns, test each clue, and enjoy the moment every hidden message comes into focus.",
        "Word Scramble + Trivia": f"Explore {theme_name} through {count} word scrambles guided by specific fact clues. Each question helps you discover its scrambled answer.",
        "Mixed Brain Games": f"Enjoy {count} varied challenges built around {theme_name}, with Sudoku, Cryptograms, and word scrambles with fact clues arranged in clear sections.",
    }
    headings = {
        "Sudoku": "LOGIC WITH A FRESH TWIST", "Cryptogram": "EVERY MESSAGE HAS A SECRET",
        "Word Scramble + Trivia": "WORDS, FACTS, AND DISCOVERY", "Mixed Brain Games": "A NEW CHALLENGE ON EVERY TURN",
    }
    feature = {
        "Sudoku": "- Number, letter, and themed shape Sudoku\n- One verified solution for every grid\n- Complete answer section",
        "Cryptogram": "- Clearly numbered code-breaking puzzles\n- Topic-matched messages\n- Complete answer section",
        "Word Scramble + Trivia": "- Topic-matched scrambled answers\n- Fact clues that help solve each word\n- Complete answer section",
        "Mixed Brain Games": "- Three distinct puzzle styles\n- Themed section dividers\n- Complete answers for every game",
    }
    body = (openings[kind] + "\n\nINSIDE THIS BOOK\n\n" + feature[kind] +
            f"\n\nBOOK DETAILS\n\n{count} puzzles - {difficulty_description(kind, difficulty)} - easy-to-read 8.5 x 11 inch pages")
    return headings[kind], body

def content_check(kind: str, theme: str) -> tuple[bool, str, int]:
    """Reject malformed or repeated entries before a release package is made."""
    if kind == "Mixed Brain Games":
        crypto_ok, crypto_detail, crypto_capacity=content_check("Cryptogram", theme)
        trivia_ok, trivia_detail, trivia_capacity=content_check("Word Scramble + Trivia", theme)
        return crypto_ok and trivia_ok, f"Mixed library: {crypto_detail}; {trivia_detail}", min(crypto_capacity, trivia_capacity)
    source = CRYPTOS if theme in ("General Starter", "General Knowledge & Curiosity") and kind == "Cryptogram" else TRIVIA if theme in ("General Starter", "General Knowledge & Curiosity") else themed_cryptograms(theme) if kind == "Cryptogram" else themed_trivia(theme)
    if kind == "Cryptogram":
        cleaned=[str(item).strip().upper() for item in source]
        # The renderer preserves ordinary sentence punctuation while encoding
        # letters.  Capacity must use the same contract instead of rejecting
        # a reviewed prompt merely because it ends with a period.
        valid=[item for item in cleaned if len(item) >= 18 and re.fullmatch(r"[A-Z0-9 ,.'!?-]+", item)]
        unique=len(set(valid))
        return unique == len(source), f"{unique} unique, clean cryptogram prompts", unique
    cleaned=[]
    for item in source:
        if isinstance(item, (list, tuple)) and len(item) == 3:
            word, question, answer=(str(value).strip() for value in item)
            if len(word) >= 4 and word.isalpha() and question.endswith("?") and answer:
                cleaned.append((word.upper(), question.casefold(), answer.casefold()))
    unique=len({item[0] for item in cleaned})
    questions=len({item[1] for item in cleaned})
    ok=unique == len(source) and questions == len(source)
    clue_count = sum(scramble_answer_parts(word, answer)[1] is None for word, _question, answer in source)
    return ok, f"{unique} unique answer words and {questions} unique checked questions; {clue_count} questions clue the same word", min(unique, questions)

def cover_spec(kind: str, theme: str, seed: int, cover_style: str = "Automatic matching", cover_photo: str = "Automatic matching", *, title: str = "", subtitle: str = ""):
    """Choose an approved, topic-matched background and compatible layout.

    The old filename lists remain available for older saved UI choices, but
    automatic production selection now comes solely from the provenance gate.
    """
    choices, palette, _default_style = THEME_ART.get(theme, ART[kind])
    requested = str(cover_photo or "")
    preferred = ""
    if requested not in {"", "Automatic matching"}:
        # The UI shows friendly image basenames. Routing expects the actual
        # indexed path; passing a basename silently discarded the choice.
        preferred = str(APP / "cover_assets" / "background_photos" / requested) if requested in choices else str(cover_art_path(requested))
    decision = select_cover_asset(CoverRequest(
        route=f"Puzzle Studio — {kind}", title=title or theme, subtitle=subtitle, puzzle_type=kind,
        topic=theme, style=str(COVER_STYLE_OPTIONS.get(cover_style) or ""),
        palette=palette, preferred_asset=preferred,
        selection_seed=seed,
    ))
    selected = decision.asset
    # An empty path is a deliberate "background needed" signal.  The package
    # creation gate turns it into a plain-English next action rather than
    # falling back to a generic unrelated asset.
    art = str(selected.get("path")) if selected else ""
    if selected and selected.get("palette"):
        palette = str(selected["palette"])
    selected_style = decision.style or COVER_STYLE_OPTIONS.get(cover_style)
    # When automatic routing found approved artwork, production must actually
    # render that artwork.  Template-only layouts are still available as an
    # explicit advanced choice, but can no longer silently replace the image.
    style = selected_style or ("photo" if selected else AUTO_COVER_STYLES[kind][seed % len(AUTO_COVER_STYLES[kind])])
    return art, palette, style


def cover_art_path(value: str | Path | None) -> Path | None:
    """Resolve the registry's project-relative path exactly once.

    Registry rows store paths relative to the application root.  Keeping the
    conversion here prevents preview and production routes from independently
    guessing whether a value is a basename, a library-relative path, or an
    absolute path.
    """
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else APP / path

def font(name: str) -> str:
    return name if name in pdfmetrics.getRegisteredFontNames() else {"BookSans":"Helvetica", "BookBold":"Helvetica-Bold", "BookMono":"Courier-Bold"}[name]

def wrap(c, text, width, face, size):
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if not line or c.stringWidth(trial, face, size) <= width: line = trial
        else: lines.append(line); line = word
    return lines + ([line] if line else [])

def title(c, value, y, size=24):
    face = font("BookBold")
    while c.stringWidth(value, face, size) > PAGE_W - 2*MARGIN and size > 13: size -= 1
    c.setFont(face, size); c.setFillColorRGB(.08,.12,.16); c.drawCentredString(PAGE_W/2, y, value)

def footer(c, n):
    c.setFont(font("BookSans"), 9); c.setFillColorRGB(.35,.35,.35); c.drawCentredString(PAGE_W/2, 32, str(n))


THEME_PAGE_NOTES = {
    "Space & Astronomy": ("LOOK UP. THINK WIDER.", "ORBIT"),
    "Garden & Growing": ("GROW ONE STEP AT A TIME.", "GROW"),
    "Travel & Adventure": ("EVERY CLUE OPENS A NEW ROUTE.", "ROUTE"),
    "Pets & Animal Life": ("A PLAYFUL PAUSE FOR ANIMAL LOVERS.", "PAWS"),
    "Holidays & Seasons": ("A LITTLE SEASONAL CHEER ON EVERY PAGE.", "CHEER"),
    "History & Heritage": ("FOLLOW THE CLUES THROUGH THE PAST.", "PAST"),
    "Food & Home": ("A COZY CHALLENGE FOR A QUIET BREAK.", "HOME"),
    "School & Vocabulary": ("LEARN, NOTICE, AND KEEP GOING.", "LEARN"),
    "Cars & Adventure": ("START YOUR ENGINE. FIND THE PATTERN.", "DRIVE"),
    "Nature & Outdoors": ("TAKE THE SCENIC ROUTE TO THE ANSWER.", "TRAIL"),
    "Bible & Faith": ("A PEACEFUL MOMENT OF FOCUS.", "FAITH"),
}


def themed_running_header(c, kind: str, theme: str, index: int) -> None:
    """Add restrained topic identity without using heavy ink or risky glyphs."""
    note, tag = THEME_PAGE_NOTES.get(theme, ("A FRESH PUZZLE BREAK.", "FOCUS"))
    c.setStrokeColorRGB(.67, .67, .67); c.setLineWidth(0.75)
    c.line(MARGIN, PAGE_H - 42, MARGIN + 52, PAGE_H - 42)
    c.line(PAGE_W - MARGIN - 52, PAGE_H - 42, PAGE_W - MARGIN, PAGE_H - 42)
    c.setFillColorRGB(.38, .38, .38); c.setFont(font("BookBold"), 8.5)
    c.drawString(MARGIN, PAGE_H - 35, tag)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 35, kind.upper())
    if index % 5 == 0:
        c.setFillColorRGB(.42, .42, .42); c.setFont(font("BookSans"), 8.5)
        c.drawCentredString(PAGE_W / 2, 50, note)


def themed_solution_header(c, theme: str, label: str) -> None:
    """Give solution pages a deliberate visual hierarchy while staying low ink."""
    _note, tag = THEME_PAGE_NOTES.get(theme, ("", "SOLVE"))
    c.setFillColorRGB(.94, .94, .94); c.roundRect(MARGIN, PAGE_H - 82, PAGE_W - 2 * MARGIN, 34, 8, stroke=0, fill=1)
    c.setFillColorRGB(.18, .18, .18); c.setFont(font("BookBold"), 10)
    c.drawString(MARGIN + 14, PAGE_H - 69, f"{tag} COLLECTION")
    c.drawRightString(PAGE_W - MARGIN - 14, PAGE_H - 69, label.upper())

def front_pages(c, kind, title_text, subtitle, author, style_name="Studio Classic", theme="General Starter", puzzle_count=0, title_page_style="Automatic", large_print=False, edition=""):
    metadata = {
        "title": title_text, "subtitle": subtitle, "author": author,
        "puzzle_type": kind, "theme": theme, "puzzle_count": puzzle_count,
        "title_page_style": title_page_style, "large_print": large_print,
        "edition": edition or ("Signature Edition" if int(puzzle_count or 0) >= 100 else "Standard"),
    }
    render_title_page(c, spec_from_mapping(metadata, puzzle_type=kind), page_size=(PAGE_W, PAGE_H), regular_font=font("BookSans"), bold_font=font("BookBold"))
    title(c, "HOW TO PLAY", PAGE_H-120, 23); c.setFont(font("BookSans"), 13)
    copy = {"Sudoku":"Fill every row, column, and 3 by 3 box with each of the nine symbols shown. Number, letter, and shape games follow the exact same Sudoku logic. Each puzzle has one verified solution.",
            "Cryptogram":"Each letter stands for one different letter. Start with short words, repeated patterns, and common letters. Solutions are at the back.",
            "Word Scramble + Trivia":"Use each fact question as a clue to unscramble its answer. The answer key lists the solved words; when a clue has a different answer, that answer is included too.",
            "Mixed Brain Games":"Enjoy a balanced mix of Sudoku, Cryptograms, and word scrambles with fact clues. Each section includes its own clear answer pages so you can check your work at any time."}[kind]
    for i,line in enumerate(wrap(c, copy, PAGE_W-140, font("BookSans"), 13)): c.drawCentredString(PAGE_W/2, PAGE_H-195-i*23, line)
    c.setFont(font("BookSans"), 10); c.drawCentredString(PAGE_W/2, 95, f"Copyright © 2026 {author}. All rights reserved."); c.showPage()

def section_divider(c, section: str, theme: str, page: int) -> None:
    """A calm black-and-white divider page for mixed-puzzle collections."""
    section_key = section.upper()
    title(c, section_key, PAGE_H-145, 29)
    c.setFont(font("BookSans"), 13); c.setFillColorRGB(.28,.28,.28)
    c.drawCentredString(PAGE_W/2, PAGE_H-182, theme.upper() if theme != "General Starter" else "A FRESH PUZZLE BREAK")
    c.setStrokeColorRGB(.18,.18,.18); c.setLineWidth(2)
    x, y = PAGE_W/2, PAGE_H/2+15
    if section_key == "SUDOKU":
        size=165; left=x-size/2; bottom=y-size/2
        c.rect(left,bottom,size,size)
        for n in (1,2):
            c.setLineWidth(1.4); c.line(left+n*size/3,bottom,left+n*size/3,bottom+size); c.line(left,bottom+n*size/3,left+size,bottom+n*size/3)
        c.setFont(font("BookBold"), 22); c.setFillColorRGB(.20,.20,.20)
        for row in range(3):
            for col in range(3): c.drawCentredString(left+(col+.5)*size/3,bottom+(2.5-row)*size/3,str((row*3+col+1)))
    elif section_key == "CRYPTOGRAMS":
        c.roundRect(x-68,y-12,136,102,12,stroke=1,fill=0); c.circle(x,y+90,32,stroke=1,fill=0); c.line(x-32,y+90,x+32,y+90)
        c.setFont(font("BookMono"),18); c.setFillColorRGB(.20,.20,.20); c.drawCentredString(x,y+28,"A = ?")
        c.setFont(font("BookSans"),12); c.drawCentredString(x,y-42,"FOLLOW THE PATTERN • BREAK THE CODE")
    else:
        letters="WORDPLAY"; tile=32; start=x-(len(letters)*tile)/2
        for index, letter in enumerate(letters):
            c.roundRect(start+index*tile,y,28,34,5,stroke=1,fill=0)
            c.setFont(font("BookBold"),16); c.setFillColorRGB(.20,.20,.20); c.drawCentredString(start+index*tile+14,y+10,letter)
        c.setFont(font("BookSans"),12); c.drawCentredString(x,y-40,"UNSCRAMBLE • THINK • DISCOVER")
    c.setFont(font("BookSans"), 12); c.setFillColorRGB(.28,.28,.28)
    c.drawCentredString(PAGE_W/2, 165, "Turn the page when you are ready for the next kind of challenge.")
    footer(c,page); c.showPage()

def sudoku_book(c, count, difficulty, seed, theme="General Starter", page_start=3, *, typography=None):
    from publishing.sudoku_typography import resolve_typography
    typography=resolve_typography(typography)
    import sudoku
    from sudoku_symbols import pack_label, symbol_pack_for_theme
    sudoku.register_fonts(); rng=random.Random(seed); profile={"Easy":"easy","Hard":"hard"}.get(difficulty,"mixed")
    ds=[]
    if profile=="mixed": ds=["easy"]*(count*4//10)+["medium"]*(count*35//100)+["hard"]*(count-count*4//10-count*35//100)
    else: ds=[profile]*count
    rng.shuffle(ds); items=[]; page=page_start
    styles=("numbers", "letters", "shapes")
    symbol_pack=symbol_pack_for_theme(theme)
    style_names={"numbers":"CLASSIC NUMBER SUDOKU", "letters":"LETTER SUDOKU", "shapes":pack_label(symbol_pack)}
    for i,d in enumerate(ds,1):
        style=styles[(i-1) % len(styles)]
        solved=sudoku.make_solved(rng); puzzle,rating=sudoku.make_rated_puzzle(solved,d,rng)
        from publishing.sudoku_difficulty import rate_sudoku
        rating=rate_sudoku(puzzle); d=rating['label']
        records=getattr(c,'_puzzle_records',[])
        records.append(dict(number=len(records)+1,type='sudoku',grid=puzzle,solution_grid=solved,difficulty=rating,
                            puzzle_heading=f'PUZZLE {i}',solution_heading=f'PUZZLE {i}',local_number=i,
                            puzzle_page=c.getPageNumber(),display_style=style))
        c._puzzle_records=records
        if sudoku.count_solutions([r[:] for r in puzzle]) != 1: raise ValueError("Sudoku uniqueness check failed.")
        themed_running_header(c, "Sudoku", theme, i)
        c.setFont(font("BookBold"),12); c.setFillColorRGB(.1,.1,.1); c.drawString(MARGIN,PAGE_H-65,f"PUZZLE {i}"); c.drawRightString(PAGE_W-MARGIN,PAGE_H-65,f"{style_names[style]} • {d.upper()}")
        sudoku.draw_sudoku(c,puzzle,81,PAGE_H-130,50,font("BookMono"),28 if style=="shapes" else typography.puzzle_font_pt,display_style=style,symbol_pack=symbol_pack,region_role="puzzle"); footer(c,page); c.showPage(); page+=1; items.append((i,puzzle,solved,style))
    title(c,"SOLUTIONS",PAGE_H-100,28); footer(c,page); c.showPage(); page+=1
    for i,puz,sol,style in items:
        next(row for row in records if row['type']=='sudoku' and row['local_number']==i)['solution_page']=c.getPageNumber()
        themed_solution_header(c, theme, "Sudoku Solutions")
        c.setFont(font("BookBold"),12); c.setFillColorRGB(.1,.1,.1); c.drawString(MARGIN,PAGE_H-114,f"PUZZLE {i}")
        sudoku.draw_sudoku(c,sol,171,PAGE_H-155,30,font("BookMono"),17 if style=="shapes" else typography.solution_font_pt,display_style=style,symbol_pack=symbol_pack,region_role="solution"); footer(c,page); c.showPage(); page+=1
    return page


def sudoku_cover_sample(count: int, difficulty: str, seed: int) -> str:
    """Reconstruct the first printed grid for a truthful Sudoku cover preview."""
    import sudoku
    rng = random.Random(seed)
    profile = {"Easy": "easy", "Hard": "hard"}.get(difficulty, "mixed")
    if profile == "mixed":
        difficulties = ["easy"] * (count * 4 // 10) + ["medium"] * (count * 35 // 100)
        difficulties += ["hard"] * (count - len(difficulties))
    else:
        difficulties = [profile] * count
    rng.shuffle(difficulties)
    solved = sudoku.make_solved(rng)
    puzzle, _rating = sudoku.make_rated_puzzle(solved, difficulties[0], rng)
    if sudoku.count_solutions([row[:] for row in puzzle]) != 1:
        raise ValueError("The Sudoku cover preview is not uniquely solvable.")
    return "".join(str(value) if value else "." for row in puzzle for value in row)

def derange(rng):
    a=list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    while True:
        b=a[:]; rng.shuffle(b)
        if all(x != y for x,y in zip(a,b)): return dict(zip(a,b))

def crypto_book(c, count, seed, theme="General Starter", page_start=3, *, typography=None):
    from publishing.cryptogram_typography import resolve_typography
    typography = resolve_typography(typography)
    rng=random.Random(seed); page=page_start; items=[]
    records=getattr(c,'_puzzle_records',[]); local_records=[]
    c._puzzle_records=records
    phrases=CRYPTOS if theme in ("General Starter", "General Knowledge & Curiosity") else themed_cryptograms(theme)
    if count > len(phrases): raise ValueError(f"The {theme} Cryptogram pack has {len(phrases)} unique puzzles; choose no more than that many.")
    phrases=random.Random(seed + 37).sample(phrases, count)
    for n,plain in enumerate(phrases,1):
        mapping=derange(rng); coded="".join(mapping.get(ch,ch) for ch in plain); items.append((plain,coded))
        record=dict(number=len(records)+1,type='cryptogram',plaintext=plain,ciphertext=coded,mapping=mapping,
                    solution_plaintext=plain,puzzle_page=c.getPageNumber(),puzzle_heading=f'CRYPTOGRAM {n}',solution_heading=f'{n}.')
        records.append(record); local_records.append(record)
        themed_running_header(c, "Cryptogram", theme, n)
        c.setFont(font("BookBold"),14); c.setFillColorRGB(.1,.1,.1); c.drawString(MARGIN,PAGE_H-65,f"CRYPTOGRAM {n}")
        c.setFont(font("BookSans"),10); c.setFillColorRGB(.35,.35,.35); c.drawRightString(PAGE_W-MARGIN,PAGE_H-65,"BREAK THE CODE")
        y=PAGE_H-135; c.setFont(font("BookMono"),typography.puzzle_font_pt); c.setFillColorRGB(.05,.05,.05)
        for line in wrap(c,coded,PAGE_W-2*MARGIN,font("BookMono"),typography.puzzle_font_pt): c.drawCentredString(PAGE_W/2,y,line); y-=32
        y-=25; c.setLineWidth(.8); c.setStrokeColorRGB(.35,.35,.35)
        for row in range(5): c.line(MARGIN,y-row*43,PAGE_W-MARGIN,y-row*43)
        footer(c,page); c.showPage(); page+=1
    title(c,"SOLUTIONS",PAGE_H-100,28); footer(c,page); c.showPage(); page+=1
    for start in range(0,len(items),5):
        themed_solution_header(c, theme, "Decoded Messages")
        y=PAGE_H-120; c.setFont(font("BookBold"),12); c.setFillColorRGB(.1,.1,.1)
        for idx,(plain,_coded) in enumerate(items[start:start+5],start+1):
            local_records[idx-1]['solution_page']=c.getPageNumber()
            c.drawString(MARGIN,y,f"{idx}."); c.setFont(font("BookSans"),typography.solution_font_pt)
            for line in wrap(c,plain,PAGE_W-100,font("BookSans"),typography.solution_font_pt): c.drawString(MARGIN+26,y,line); y-=17
            y-=14; c.setFont(font("BookBold"),12)
        footer(c,page); c.showPage(); page+=1
    return page

def scramble(word,rng):
    chars=list(word)
    for _ in range(20):
        rng.shuffle(chars); got="".join(chars)
        if got != word: return got
    return word[::-1]

def scramble_answer_parts(word, trivia_answer):
    """Show a second answer only when it differs from the scramble solution."""
    normalized_word = re.sub(r"[^A-Z0-9]", "", word.upper())
    normalized_answer = re.sub(r"[^A-Z0-9]", "", trivia_answer.upper())
    return word, trivia_answer if normalized_answer != normalized_word else None

def scramble_book(c,count,seed,theme="General Starter",page_start=3):
    rng=random.Random(seed); page=page_start; items=[]
    records=getattr(c,'_puzzle_records',[]); local_records=[]
    c._puzzle_records=records
    source=TRIVIA if theme in ("General Starter", "General Knowledge & Curiosity") else themed_trivia(theme)
    if count > len(source): raise ValueError(f"The {theme} Scramble + Trivia pack has {len(source)} unique games; choose no more than that many.")
    source=random.Random(seed + 71).sample(source, count)
    for start in range(0,count,2):
        c.setFont(font("BookSans"),10); c.setFillColorRGB(.35,.35,.35); c.drawCentredString(PAGE_W/2,PAGE_H-38,"WORD SCRAMBLES + FACT CLUES")
        for pos,(word,q,a) in enumerate(source[start:start+2]):
            idx=start+pos+1; y=PAGE_H-100-pos*300; shown=scramble(word,rng); items.append((word,q,a,shown))
            record=dict(number=len(records)+1,type='scramble_trivia',word=word,scrambled=shown,fact_answer=a,
                        solution_word=word,solution_fact_answer=a,puzzle_page=c.getPageNumber(),
                        puzzle_heading=f'{idx}. UNSCRAMBLE: {shown}',solution_heading=f'{idx}. {word}')
            records.append(record); local_records.append(record)
            c.setFont(font("BookBold"),14); c.setFillColorRGB(.1,.1,.1); c.drawString(MARGIN,y,f"{idx}. UNSCRAMBLE: {shown}")
            c.setFont(font("BookSans"),12); y-=42
            for line in wrap(c,q,PAGE_W-2*MARGIN,font("BookSans"),12): c.drawString(MARGIN,y,line); y-=19
            y-=18; c.setLineWidth(.8); c.setStrokeColorRGB(.35,.35,.35); c.line(MARGIN,y,PAGE_W-MARGIN,y); c.line(MARGIN,y-44,PAGE_W-MARGIN,y-44)
        footer(c,page); c.showPage(); page+=1
    # Two columns save paper without shrinking solutions into tiny type.
    # The question usually clues the scrambled word, so duplicating that
    # same answer as "word - trivia answer" is misleading and wasteful.
    for start in range(0,len(items),20):
        themed_solution_header(c, theme, "Answer Key")
        title(c,"ANSWER KEY",PAGE_H-118,19)
        c.setFont(font("BookSans"),9); c.setFillColorRGB(.35,.35,.35)
        c.drawCentredString(PAGE_W/2,PAGE_H-138,"A second answer appears only when a fact clue has a different answer.")
        for offset,(word,_q,a,_shown) in enumerate(items[start:start+20]):
            column, row = divmod(offset, 10)
            x = MARGIN if column == 0 else PAGE_W/2+12
            y = PAGE_H-178-row*55
            solution, extra = scramble_answer_parts(word, a)
            local_records[start+offset]['solution_page']=c.getPageNumber()
            c.setFont(font("BookBold"),11); c.setFillColorRGB(.1,.1,.1)
            c.drawString(x,y,f"{start+offset+1}. {solution}")
            if extra:
                c.setFont(font("BookSans"),9.5); c.setFillColorRGB(.3,.3,.3)
                for line_number,line in enumerate(wrap(c,f"Fact answer: {extra}",PAGE_W/2-MARGIN-25,font("BookSans"),9.5)):
                    c.drawString(x+16,y-15-line_number*12,line)
        footer(c,page); c.showPage(); page+=1
    return page


def mixed_section_themes(theme: str) -> tuple[str, str]:
    """Keep both word-based sections aligned with the book's selected theme."""
    selected = str(theme or "General Starter").strip() or "General Starter"
    return selected, selected

def bonus_pages(c, selected, theme, start_page, style_name):
    """Append actual optional reader-value pages before final page padding."""
    page = start_page; accent = interior_preset(style_name)["accent"]
    for heading in bonus_page_titles(selected, theme):
        title(c, heading, PAGE_H-125, 25); c.setStrokeColorRGB(*accent); c.setLineWidth(1.5)
        if heading == "COMPLETION CERTIFICATE":
            c.roundRect(90, 210, PAGE_W-180, 330, 12, stroke=1, fill=0)
            c.setFont(font("BookSans"), 14); c.setFillColorRGB(.2,.2,.2); c.drawCentredString(PAGE_W/2, 405, "This certifies that")
            c.line(145, 358, PAGE_W-145, 358); c.drawCentredString(PAGE_W/2, 315, "completed this puzzle-book challenge.")
        elif heading == "MY PUZZLE PROGRESS":
            c.setFont(font("BookSans"), 11); c.setFillColorRGB(.2,.2,.2)
            for row in range(18):
                y=PAGE_H-160-row*28; c.line(80,y,PAGE_W-80,y); c.drawString(84,y+7,f"{row+1:02}")
        elif heading.startswith("ABOUT "):
            c.setFont(font("BookSans"), 13); c.setFillColorRGB(.2,.2,.2)
            c.drawCentredString(PAGE_W/2, PAGE_H-185, "Write down three things you discovered while playing.")
            for row in range(8): c.line(95, PAGE_H-245-row*42, PAGE_W-95, PAGE_H-245-row*42)
        elif heading == "BONUS CHALLENGE":
            c.setFont(font("BookSans"), 13); c.setFillColorRGB(.2,.2,.2); c.drawCentredString(PAGE_W/2, PAGE_H-185, "Choose your favorite puzzle and solve it again without checking the answers.")
            for row in range(10): c.line(85, PAGE_H-240-row*32, PAGE_W-85, PAGE_H-240-row*32)
        else:
            c.setFont(font("BookSans"), 13); c.setFillColorRGB(.2,.2,.2); c.drawCentredString(PAGE_W/2, PAGE_H-185, "More screen-free puzzle adventures are waiting for you.")
            c.setFont(font("BookBold"), 18); c.drawCentredString(PAGE_W/2, PAGE_H-240, "SLADE PUZZLE CO")
        footer(c,page); c.showPage(); page += 1
    return page


def puzzle_notes_page(c, page, heading="PUZZLE NOTES"):
    """Create a useful, non-empty page when print pagination needs padding."""
    title(c, heading, PAGE_H-105, 25)
    c.setFont(font("BookSans"), 11)
    c.setFillColorRGB(.3, .3, .3)
    c.drawCentredString(PAGE_W/2, PAGE_H-135, "Keep track of clues, guesses, favorite facts, or your best solving times.")
    c.setStrokeColorRGB(.65, .65, .65)
    c.setLineWidth(0.75)
    for row in range(13):
        y = PAGE_H-185-row*38
        c.line(78, y, PAGE_W-78, y)
    footer(c, page)
    c.showPage()

def make_interior(kind,title_text,subtitle,author,count,difficulty,seed,target,theme="General Starter", interior_style="Studio Classic", bonuses=None, title_page_style="Automatic", *, sudoku_typography=None,cryptogram_typography=None):
    from publishing.sudoku_typography import package_typography
    sudoku_typography=package_typography(kind,sudoku_typography)
    from publishing.cryptogram_typography import package_typography as crypto_package_typography
    cryptogram_typography=crypto_package_typography(kind,cryptogram_typography)
    fonts(); target.parent.mkdir(parents=True,exist_ok=True); c=canvas.Canvas(str(target),pagesize=letter); c.setTitle(title_text); c.setAuthor(author)
    front_pages(c,kind,title_text,subtitle,author,interior_style,theme,count,title_page_style,"large print" in (title_text+" "+subtitle).casefold(),"Signature Edition" if int(count)>=100 else "Standard")
    if kind=="Sudoku": sudoku_book(c,count,difficulty,seed,theme,**({} if sudoku_typography is None else {"typography":sudoku_typography}))
    elif kind=="Cryptogram": crypto_book(c,count,seed,theme,**({} if cryptogram_typography is None else {"typography":cryptogram_typography}))
    elif kind=="Word Scramble + Trivia": scramble_book(c,count,seed,theme)
    else:
        # A true mixed collection: three different game sections, each with
        # its own answers.  The count is divided evenly and never repeats a
        # Cryptogram or Scramble answer within this book.
        sudoku_count=count//3 + (1 if count % 3 else 0)
        crypto_count=count//3 + (1 if count % 3 > 1 else 0)
        scramble_count=count-sudoku_count-crypto_count
        page=3
        cryptogram_theme, scramble_theme = mixed_section_themes(theme)
        section_divider(c,"Sudoku",theme,page); page+=1
        page=sudoku_book(c,sudoku_count,difficulty,seed,theme,page)
        section_divider(c,"Cryptograms",theme,page); page+=1
        page=crypto_book(c,crypto_count,seed+1009,cryptogram_theme,page)
        section_divider(c,"Word Scrambles + Fact Clues",theme,page); page+=1
        scramble_book(c,scramble_count,seed+2017,scramble_theme,page)
    pages=c.getPageNumber()-1
    pages=bonus_pages(c, bonuses, theme, pages + 1, interior_style) - 1
    # KDP paperback interiors must have at least 24 pages. Smaller books are
    # completed with useful branded notes pages instead of empty filler pages.
    while pages < 24:
        puzzle_notes_page(c, pages + 1); pages += 1
    if pages % 2:
        puzzle_notes_page(c, pages + 1, "FINAL PUZZLE NOTES")
    c.save()

    if getattr(c,'_puzzle_records',None):
        from publishing.puzzle_integrity import write_manifest
        write_manifest(target,getattr(c,'_puzzle_records',[]),getattr(c,'_puzzle_text_regions',[]))

def slug(text): return re.sub(r"[^a-z0-9]+","_",text.lower()).strip("_")[:60] or "puzzle_book"

def listing(kind,title_text,subtitle,author,count,difficulty,pages,theme="General Starter"):
    from sudoku_symbols import pack_label, symbol_pack_for_theme
    themed_shapes = pack_label(symbol_pack_for_theme(theme)).replace(" SUDOKU", "").title()
    labels={"Sudoku":"Sudoku puzzle book","Cryptogram":"Cryptogram puzzle book","Word Scramble + Trivia":"word scramble and fact-clue puzzle book","Mixed Brain Games":"mixed brain-games puzzle book"}
    copy = {
        "Sudoku": ("Turn a quiet moment into a satisfying logic ritual.", f"Classic numbers, letters, and {themed_shapes} games keep the familiar Sudoku rules fresh while every verified grid rewards patient pattern-spotting."),
        "Cryptogram": ("Step into a clever little world where every letter holds a secret.", "Start with a clue, follow the patterns, and watch an encrypted message gradually come to life."),
        "Word Scramble + Trivia": ("Bring some playful energy to your next break.", "Use each quick fact question as a clue to unscramble its answer, and enjoy a bright mix of language play and general knowledge."),
        "Mixed Brain Games": ("Give every break a different kind of satisfying challenge.", "Move between Sudoku logic, hidden-message Cryptograms, and word scrambles with fact clues without needing a separate book for each mood."),
    }[kind]
    theme_copy = {
        "Space & Astronomy": ("A star-filled theme turns each coded message into a small voyage through planets, constellations, observatories, and the wider universe.", "space puzzles adults"),
        "General Knowledge & Curiosity": ("Every challenge pairs a satisfying letter scramble with a quick, approachable fact for an easygoing brain break.", "general knowledge puzzles"),
    }.get(theme, ("", ""))
    public_kind = "word scrambles with fact clues" if kind == "Word Scramble + Trivia" else kind.lower()
    description=(f"<p><b>{title_text}</b> is made for puzzle lovers who enjoy a smart, screen-free escape. {copy[0]} "
                 f"Inside are {count} {public_kind} with easy-to-read large-format pages and complete answers at the back. {difficulty_sentence(kind, difficulty)}{ ' Every book includes classic number, letter, and shape Sudoku games.' if kind == 'Sudoku' else ''}</p>"
                 f"<p>{copy[1]} {theme_copy[0]} Whether you solve one page with coffee or settle in for a longer session, this {labels[kind].lower()} makes spare moments feel more rewarding.</p>"
                 "<p><b>Inside you will find:</b></p><ul><li>Clearly numbered puzzles</li><li>Easy-to-read print</li><li>A complete answer section</li></ul>"
                 "<p>Bring a pencil, follow your curiosity, and enjoy the satisfaction of the next answer.</p>")
    keywords={"Sudoku":["large print sudoku","logic puzzles adults","number puzzle book","sudoku with solutions","brain games adults","easy medium hard sudoku","screen free activity"],
              "Cryptogram":["cryptogram puzzles","code breaking games","cipher puzzle book","word logic challenges","cryptograms with answers","brain games adults","screen free activity"],
              "Word Scramble + Trivia":["word scramble puzzles","fact clue word games","word games adults","general knowledge clues","scramble with answers","brain games adults","screen free activity"],
              "Mixed Brain Games":["brain games collection","mixed puzzle book","sudoku cryptogram word games","variety puzzle book","logic and word games","screen free activity","puzzle book with answers"]}[kind]
    if theme_copy[1]:
        keywords[-1] = theme_copy[1]
    special = "Special games: Includes number, letter, and shape Sudoku alongside Cryptograms and word scrambles with fact clues.\n" if kind == "Mixed Brain Games" else "Special games: Every Sudoku book includes classic number, letter, and shape Sudoku.\n" if kind == "Sudoku" else ""
    theme_line = f"Content theme: {theme}\n" if theme != "General Starter" else ""
    public_label = "Word Scrambles + Fact Clues" if kind == "Word Scramble + Trivia" else kind
    return f"KDP LISTING KIT — REVIEW BEFORE UPLOAD\n\nTitle: {title_text}\nSubtitle: {subtitle}\nAuthor: {author}\nBook type: {public_label}\n{theme_line}{special}Trim size: 8.5 x 11 inches (US Letter)\nInterior: black and white, no bleed\nPuzzle count: {count}\nDifficulty: {difficulty_description(kind, difficulty)}\nInterior pages: {pages}\n\nDESCRIPTION (KDP basic HTML)\n{description}\n\nKEYWORD PHRASES (use one per KDP box)\n" + "\n".join(f"{i+1}. {v}" for i,v in enumerate(keywords)) + "\n\nCATEGORY DIRECTION\nChoose the most accurate Games & Activities category available for this exact puzzle type. Do not select unrelated categories.\n\nAI CONTENT REMINDER\nIf you use AI-generated cover art, answer KDP's AI-content question accurately during upload.\n"

def _production_scope(kind, title_text, production_run_id=None, output_parent=None):
    """Keep ordinary identity/output unchanged; isolate explicit revision runs."""
    if production_run_id is None:
        if output_parent is not None:
            raise ValueError("A revision output requires a validated run identity.")
        return hashlib.sha1(f"{kind}|{title_text}".encode("utf-8")).hexdigest()[:12], OUT
    if not isinstance(production_run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", production_run_id):
        raise ValueError("Revision run identity must be a UUID hex value.")
    import uuid
    if uuid.UUID(hex=production_run_id).version != 4:
        raise ValueError("Revision run identity must be a version 4 UUID.")
    project=APP.resolve()
    staging=APP/"data/studio_revision_candidates"
    # Inspect the lexical staging chain before resolving it: a UUID junction
    # must not redirect a revision into canonical output or another run.
    for entry in (APP/"data", staging, staging/production_run_id):
        if entry.is_symlink() or entry.is_junction():
            raise ValueError("Revision staging cannot use symlinks or junctions.")
    trusted_parent=staging.resolve()
    if not trusted_parent.is_relative_to(project):
        raise ValueError("Revision staging must remain inside this project.")
    base=(staging/production_run_id).resolve()
    destination=base if output_parent is None else Path(output_parent).resolve()
    if base.parent!=trusted_parent or base.name!=production_run_id or destination!=base:
        raise ValueError("Revision output must be this run's local staging folder.")
    return production_run_id, destination


def _record_package_failure(builder):
    """Keep a recoverable plain-English checkpoint when a background build stops."""
    def wrapped(kind, title_text, subtitle, author, count, difficulty, seed, theme="General Starter", cover_style="Automatic matching", cover_photo="Automatic matching", interior_style="", bonuses=None, content_plan_approval=None, title_page_style="Automatic", force_rebuild=False, *, sync_catalog=True, production_run_id=None, output_parent=None,sudoku_typography=None,cryptogram_typography=None):
        from publishing.sudoku_typography import package_typography
        sudoku_typography=package_typography(kind,sudoku_typography)
        from publishing.cryptogram_typography import package_typography as crypto_package_typography
        cryptogram_typography=crypto_package_typography(kind,cryptogram_typography)
        book_id, _ = _production_scope(kind, title_text, production_run_id, output_parent)
        try:
            options = {"sync_catalog": sync_catalog}
            if sudoku_typography is not None:options["sudoku_typography"]=sudoku_typography
            if cryptogram_typography is not None:options["cryptogram_typography"]=cryptogram_typography
            if production_run_id is not None:
                options["production_run_id"] = production_run_id
            if output_parent is not None:
                options["output_parent"] = output_parent
            return builder(kind, title_text, subtitle, author, count, difficulty, seed, theme, cover_style, cover_photo, interior_style, bonuses, content_plan_approval, title_page_style, force_rebuild, **options)
        except Exception as exc:
            from publishing.production_autopilot import ProductionAutopilot
            ProductionAutopilot(APP, book_id).fail("package", str(exc), human_review=True)
            raise
    return wrapped


def _sync_completed_package(folder, autopilot, facts, *, sync_catalog=True):
    """Register only after production gates; staged revisions keep catalog IDs intact."""
    if not sync_catalog:
        return
    # Register every non-word-search package right away. This also creates the
    # same platform-aware MASTER_RELEASE_PACKAGE used by Word Search books.
    try:
        from publishing import PublishingService
        PublishingService(APP).sync_output_packages()
        autopilot.complete("register", autopilot.stage_fingerprint(facts, "register"), "Finished package was registered in Publishing Center.")
    except Exception as exc:
        (folder/"PUBLISHING_MANAGER_SYNC_NOTE.txt").write_text(
            "The package is complete, but automatic Publishing Manager registration needs a retry. "
            "Open Publishing Manager and choose Sync catalog.\n\n" + str(exc) + "\n",
            encoding="utf-8",
        )


@_record_package_failure
def create_package(kind,title_text,subtitle,author,count,difficulty,seed,theme="General Starter",cover_style="Automatic matching",cover_photo="Automatic matching",interior_style="",bonuses=None,content_plan_approval=None,title_page_style="Automatic",force_rebuild=False,*,sync_catalog=True,production_run_id=None,output_parent=None,sudoku_typography=None,cryptogram_typography=None):
    from publishing.sudoku_typography import package_typography, typography_facts, bind_typography, verify_typography_binding
    sudoku_typography=package_typography(kind,sudoku_typography)
    from publishing.cryptogram_typography import package_typography as crypto_package_typography
    cryptogram_typography=crypto_package_typography(kind,cryptogram_typography)
    config=sudoku_typography or cryptogram_typography
    config_key='cryptogram_typography' if cryptogram_typography is not None else 'sudoku_typography'
    if cryptogram_typography is not None:
        from publishing.cryptogram_typography import typography_facts, bind_typography, verify_typography_binding
    book_id, destination_root = _production_scope(kind, title_text, production_run_id, output_parent)
    if production_run_id is not None and sync_catalog:
        raise ValueError("Staged revision candidates cannot synchronize the catalog.")
    author=" ".join(str(author or "").split())
    if not author or author.casefold() == "slade puzzles" or "puzzles" in author.casefold():
        raise ValueError("Use a real contributor or pen name in the Author box (for example, Jordan M. Slade). Keep Slade Puzzles as the brand, not the KDP contributor.")
    validate_scramble_promise(kind, theme, title_text, subtitle)
    # One shared checkpoint record serves Sudoku, Cryptogram, Scramble +
    # Trivia, and Mixed Brain Games. It records the same facts the package
    # will use; it does not replace any established generator or proof gate.
    from publishing.production_autopilot import ProductionAutopilot, canonical_facts
    source = {"title": title_text, "subtitle": subtitle, "author": author, "puzzle_type": kind, "detected_topic": theme, "puzzle_count": count, "puzzle_seed": seed, "trim_size": "8.5x11", "difficulty": difficulty, "files": {}}
    facts = canonical_facts({"book_id": book_id, "source_key": f"generated:{kind}:{theme}", "package_path": "", "metadata": source}, source)
    facts=typography_facts(facts,config)
    autopilot = ProductionAutopilot(APP, book_id); autopilot.begin(facts)
    if kind in ("Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"):
        checked, detail, capacity = content_check(kind, theme); required = required_content_for_book(kind, count)
        if not checked or capacity < required:
            reason = f"Content Library Verification needs {required} checked entries; {capacity} are currently available. {detail}"
            autopilot.fail("validate", reason, human_review=True)
            raise ValueError(reason)
    autopilot.complete("validate", autopilot.stage_fingerprint(facts, "validate"), "Contributor, content capacity, and automatic-plan checks passed before generation.")
    autopilot.attach_orchestrator({**facts, "book_plan_id": f"automatic-{kind.casefold().replace(' ', '-')}", "source_revision": facts.get("fingerprint", ""), "cover_style": cover_style, "palette": THEME_ART.get(theme, ART[kind])[1], "content_plan_approval": dict(content_plan_approval or {})})
    prior = autopilot.record().get("stages", {}).get("package", {})
    prior_folder = Path(str(prior.get("artifact") or ""))
    from publishing.package_layout import release_contract
    if production_run_id is not None and prior.get("artifact") and not prior_folder.resolve().is_relative_to(destination_root):
        raise ValueError("Revision checkpoint points outside its staging folder.")
    if not force_rebuild and prior.get("status") == "complete" and prior.get("fingerprint") == autopilot.stage_fingerprint(facts, "package") and prior.get("artifact") and prior_folder.is_dir() and release_contract(prior_folder)["ready"]:
        if config is not None:
            verify_typography_binding(package_file(prior_folder,'interior.pdf'),config)
            recorded=json.loads(package_file(prior_folder,'PACKAGE_SOURCE_RECORD.json').read_text(encoding='utf-8-sig'))
            if recorded.get(config_key)!=config.to_dict():
                raise ValueError('Saved package typography differs from its confirmed configuration.')
        return prior_folder
    from publishing.package_layout import package_root_for_artifact
    generated = None if force_rebuild else autopilot.current_artifact("generate", autopilot.stage_fingerprint(facts, "generate"))
    if generated and config is not None:verify_typography_binding(generated,config)
    folder = package_root_for_artifact(generated) if generated else None
    if production_run_id is not None and folder and not folder.resolve().is_relative_to(destination_root):
        raise ValueError("Revision generation checkpoint points outside its staging folder.")
    if not folder or not folder.is_dir():
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); folder=destination_root/f"{slug(title_text)}_{stamp}"; folder = folder.with_name(folder.name+"_"+facts["fingerprint"][:10]) if config is not None else folder; folder.mkdir(parents=True)
    initialize_package_layout(folder)
    interior_style = interior_style if interior_style in INTERIOR_PRESETS else default_preset(kind, count == 100)
    bonuses = [value for value in (bonuses or []) if value in BONUS_PAGE_OPTIONS]
    interior=package_file(folder, "interior.pdf", for_write=True)
    if not (generated and interior.is_file()):
        render_options={} if config is None else {config_key:config}
        make_interior(kind,title_text,subtitle,author,count,difficulty,seed,interior,theme,interior_style,bonuses,title_page_style,**render_options)
        if config is not None:bind_typography(interior,config)
        autopilot.complete("generate", autopilot.stage_fingerprint(facts, "generate"), "Interior and answer pages were generated from the selected puzzle type and seed.", artifact=str(interior))
    try:
        import pypdf
        pages=len(pypdf.PdfReader(str(interior)).pages)
    except Exception: pages=24
    art_name, palette, style = cover_spec(
        kind, theme, seed, cover_style, cover_photo,
        title=title_text, subtitle=subtitle,
    )
    # A fresh puzzle seed also gives each book a stable, matching art choice.
    art=cover_art_path(art_name)
    if not art:
        raise ValueError("COVER BACKGROUND NEEDED — no approved SladePuzzleCo background matches this topic yet. Generate a topic-specific background before creating the package.")
    if not art.is_file():
        raise ValueError(f"The selected automatic cover image is missing: {art.name}")
    background_index = BackgroundAssetIndex()
    approved_art = background_index.ledger_details(art)
    if not approved_art or not background_index.production_selectable(approved_art):
        raise ValueError("The selected automatic cover image is not currently approved for production. Open the approved background library and choose or review a matching replacement.")
    routing_decision = select_cover_asset(CoverRequest(
        route=f"Puzzle Studio — {kind}", title=title_text, subtitle=subtitle,
        author=author, puzzle_type=kind, topic=theme,
        edition="Signature Edition" if count == 100 else "Standard",
        style=style, palette=palette, preferred_asset=str(art), selection_seed=seed,
    ))
    front=package_file(folder, "front_cover.png", for_write=True); wrap=package_file(folder, "kdp_full_wrap.pdf", for_write=True); preview=package_file(folder, "kdp_full_wrap_preview.png", for_write=True)
    # cover.py always prints the actual puzzle count in its dedicated stamp.
    # Repeating that count as a second large badge crowded Scramble and
    # Cryptogram covers without telling buyers anything new.
    badge = "NUMBER • LETTER • SHAPE GAMES" if kind == "Sudoku" else "SUDOKU • CODES • WORD GAMES" if kind == "Mixed Brain Games" else ""
    public_format = "WORD SCRAMBLES + FACT CLUES" if kind == "Word Scramble + Trivia" else kind.upper()
    call=[sys.executable,str(APP/"cover.py"),"--title",title_text,"--subtitle",subtitle,"--author",author,"--badge",badge,"--puzzle-count",str(count),"--difficulty",cover_difficulty(kind, difficulty),"--format-label",public_format,"--puzzle-type",kind,"--palette",palette,"--style",style,"--art",str(art),"--art-focus",str(approved_art.get("focus") or "center"),"--puzzle-preview-position",str(approved_art.get("puzzle_preview_position") or "center"),"--out",str(front)]
    if kind == "Word Scramble + Trivia":
        source = TRIVIA if theme in ("General Starter", "General Knowledge & Curiosity") else themed_trivia(theme)
        sample_word, sample_question, _ = random.Random(seed + 71).sample(source, count)[0]
        call.extend(["--sample-word", scramble(sample_word, random.Random(seed)), "--sample-question", sample_question])
    elif kind == "Sudoku":
        call.extend(["--sample-sudoku", sudoku_cover_sample(count, difficulty, seed)])
    cover_artifact = autopilot.current_artifact("cover", autopilot.stage_fingerprint(facts, "cover"))
    if not (cover_artifact and front.is_file()):
        subprocess.run(call,check=True,cwd=APP)
        autopilot.complete("cover", autopilot.stage_fingerprint(facts, "cover"), "Front cover was rendered from verified facts and approved matching art.", artifact=str(front))
    cover_score, cover_label, cover_notes = cover_quality_report(title_text, subtitle, badge, count, kind.upper(), style, art)
    package_file(folder, "COVER_QUALITY_REPORT.txt", for_write=True).write_text(
        "COVER QUALITY REPORT\n" + "=" * 48 + f"\nScore: {cover_score}/100 — {cover_label}\n\n" +
        "\n".join(f"• {note}" for note in cover_notes) + "\n", encoding="utf-8"
    )
    back_copy = back_cover_copy(kind, theme, count, difficulty)
    wrap_call=[sys.executable,str(APP/"wrap_cover.py"),"--front",str(front),"--pages",str(pages),"--palette",palette,"--title",title_text,"--author",author,"--back",back_copy[1],"--back-heading",back_copy[0],"--puzzle-type",kind,"--puzzle-count",str(count),"--theme",theme]
    if kind == "Sudoku":
        wrap_call.extend(["--sample-sudoku", sudoku_cover_sample(count, difficulty, seed)])
    wrap_call.extend(["--out",str(wrap),"--preview-out",str(preview)])
    subprocess.run(wrap_call,check=True,cwd=APP)
    from preflight import preflight, report_text
    passed, findings = preflight(folder)
    package_file(folder, "PUBLISHER_PREFLIGHT.txt", for_write=True).write_text(report_text(folder), encoding="utf-8")
    if not passed:
        raise ValueError("KDP preflight stopped this package: " + " | ".join(findings))
    autopilot.complete("preflight", autopilot.stage_fingerprint(facts, "preflight"), "Wrap and print preflight passed using the final interior page count.", artifact=str(wrap))
    package_file(folder, "KDP_LISTING_KIT.txt", for_write=True).write_text(listing(kind,title_text,subtitle,author,count,difficulty,pages,theme),encoding="utf-8")
    autopilot.complete("listing", autopilot.stage_fingerprint(facts, "listing"), "Listing kit was generated from verified book facts.")
    import pypdf
    pdf_author=" ".join(str((pypdf.PdfReader(str(interior)).metadata.author or "")).split())
    kit=package_file(folder, "KDP_LISTING_KIT.txt").read_text(encoding="utf-8")
    metadata_ok = pdf_author == author and title_text in kit and author in kit
    package_file(folder, "AUTHOR_CONSISTENCY_REPORT.txt", for_write=True).write_text(
        "AUTHOR & METADATA CONSISTENCY\n" + "="*48 + f"\nExpected contributor: {author}\nInterior PDF contributor: {pdf_author or 'NOT FOUND'}\nListing kit contains title: {'YES' if title_text in kit else 'NO'}\nListing kit contains contributor: {'YES' if author in kit else 'NO'}\n\nResult: {'PASS' if metadata_ok else 'BLOCK'}\n", encoding="utf-8")
    if not metadata_ok:
        raise ValueError("Author consistency check stopped this package. Open AUTHOR_CONSISTENCY_REPORT.txt for the exact mismatch.")
    if kind in ("Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"):
        checked, detail, capacity=content_check(kind, theme)
        required=required_content_for_book(kind, count)
        content_report=("CONTENT LIBRARY VERIFICATION\n\n"
                        f"Theme: {theme}\nPuzzle type: {kind}\n"
                        f"Library result: {'PASS' if checked and capacity >= required else 'BLOCK'}\n"
                        f"Verified entries: {capacity}\nRequired for this book: {required}\n"
                        f"Checks: {detail}\n\n"
                        "Meaning: every entry was checked for usable format and duplicate answer/prompt collisions before package creation.\n")
        package_file(folder, "CONTENT_LIBRARY_VERIFICATION.txt", for_write=True).write_text(content_report, encoding="utf-8")
        if not checked or capacity < required:
            raise ValueError(
                "Content Library Verification stopped this package: "
                f"{capacity} checked entries are available; this {count}-puzzle book needs {required}. "
                "Open CONTENT_LIBRARY_VERIFICATION.txt to see the duplicate or format issue, then choose a smaller book or review more topic-specific content."
            )
    package_file(folder, "AUTOMATIC_BOOK_PLAN.txt", for_write=True).write_text(
        "AUTOMATIC BOOK PLAN\n\n"
        f"Puzzle type: {kind}\nContent theme: {theme}\nBook format: {'Signature Edition' if count == 100 else 'Standard'}\n"
        f"Puzzle count: {count}\nDifficulty: {difficulty_description(kind, difficulty)}\nCover artwork: {art_name}\nCover palette: {palette}\nCover style: {style}\n"
        f"Interior design: {interior_style}\nReader bonus pages: {', '.join(bonuses) or 'None'}\n"
        "\nThese choices were selected by the studio's checked defaults. Change them only if you have a clear reason to change the book direction.\n",
        encoding="utf-8")
    proof_ok, proof_text = production_proof_gate(folder, kind, title_text, subtitle, count, pages)
    package_file(folder, "PRODUCTION_PROOF_GATE.txt", for_write=True).write_text(proof_text, encoding="utf-8")
    if not proof_ok:
        raise ValueError("Production Proof Gate stopped this package. Open PRODUCTION_PROOF_GATE.txt for the exact fixes.")
    from publishing.review import build_proof_contact_sheet
    build_proof_contact_sheet(folder)
    package_file(folder, "KDP_COMPLIANCE_REPORT.txt", for_write=True).write_text("KDP PACKAGE REVIEW\n\nPASS — Interior is US Letter (8.5 x 11), has an even page count, includes readable type, and has a complete answer section.\nPASS — Cover uses a full wrap with 0.125 inch bleed generated from the same page count.\nREQUIRED BEFORE UPLOAD — Use KDP Print Previewer, confirm the current category choices, and disclose AI-generated cover art accurately if applicable.\n",encoding="utf-8")
    from sudoku_symbols import symbol_pack_for_theme
    sudoku_symbol_pack = symbol_pack_for_theme(theme) if kind in ("Sudoku", "Mixed Brain Games") else ""
    package_file(folder, "PACKAGE_SOURCE_RECORD.json", for_write=True).write_text(json.dumps({"created": datetime.now().isoformat(timespec="seconds"), "puzzle_type": kind, "cover_puzzle_type": kind, "cover_visual_topic": theme, "theme": theme, "title": title_text, "subtitle": subtitle, "author": author, "brand": "Slade Puzzles", "puzzle_count": count, "puzzle_seed": seed, "pages": pages, "difficulty": difficulty, "sudoku_symbol_pack": sudoku_symbol_pack, "palette": palette, "cover_style": style, "cover_art": str(art), "cover_art_name": art_name, "cover_art_id": approved_art.get("asset_id", ""), "cover_art_sha256": approved_art.get("sha256", ""), "cover_art_approval_revision": approved_art.get("approval_revision") or approved_art.get("updated_at") or "", "cover_art_approval_state": approved_art.get("approval_state") or "approved", "cover_art_provenance": approved_art.get("provenance") or {}, "cover_routing": routing_decision.diagnostics(), "interior_style": interior_style, "title_page_style": title_page_style, "reader_bonus_pages": bonuses, **({config_key:config.to_dict()} if config is not None else {}), "release_status": "Ready for KDP Print Previewer"}, indent=2)+"\n", encoding="utf-8")
    provenance = approved_art.get("provenance", {})
    write_routing_diagnostics(package_file(folder, "COVER_ROUTING.json", for_write=True), routing_decision)
    package_file(folder, "COVER_ART_RIGHTS_LEDGER.txt", for_write=True).write_text(
        f"COVER ART & RIGHTS LEDGER\n{'='*48}\nBrand / imprint: Slade Puzzles\nContributor shown in package: {author}\n"
        f"Automatic cover artwork: {art_name}\nAsset ID: {approved_art.get('asset_id', '')}\nProduction approval: {approved_art.get('production_approved', False)}\n"
        f"Classification: {approved_art.get('classification', '')}\nGeneration provider: {provenance.get('provider', '')}\n"
        f"Generation model: {provenance.get('model', 'project background library')}\nFile checksum: {approved_art.get('sha256', '')}\n"
        "Use the correct marketplace AI-content disclosure when uploading AI-generated cover art.\n", encoding="utf-8")
    from publishing.product_qa import inspect_product, write_product_qa_report
    qa_metadata = {"title": title_text, "subtitle": subtitle, "puzzle_type": kind, "puzzle_type_id": kind,
                   "detected_topic": theme, "series": "", "puzzle_count": count, "difficulty": difficulty,
                   "trim_size": "8.5x11", "cover_art_use_count": len(background_index.active_usage(approved_art))}
    qa_metadata['require_puzzle_manifest'] = True
    product_qa = inspect_product(APP, folder, qa_metadata)
    write_product_qa_report(package_file(folder, "PRODUCT_QA.txt", for_write=True), product_qa)
    if product_qa.blockers:
        raise ValueError("Product QA stopped this package: " + " | ".join(item.message for item in product_qa.blockers))
    autopilot.complete("qa", autopilot.stage_fingerprint(facts, "qa"), product_qa.status)
    from publishing.production_intelligence import finalize_package
    intelligence = finalize_package(APP, folder, {"title": title_text, "subtitle": subtitle, "puzzle_type": kind, "detected_topic": theme, "series": "", "puzzles": []}, title_text, subtitle, pages)
    if not intelligence["ready"]:
        raise ValueError("Final package intelligence stopped this package: " + " | ".join(intelligence["blockers"]))
    if config is not None:verify_typography_binding(interior,config)
    autopilot.complete("package", autopilot.stage_fingerprint(facts, "package"), "Final package inspection passed and master release files were created.", artifact=str(folder))
    background_index.record_use(art, title=title_text, theme=theme, package=str(folder))
    package_file(folder, "COVER_THUMBNAIL_REVIEW.txt", for_write=True).write_text("COVER THUMBNAIL REVIEW\n"+"="*48+"\nOpen front_cover.png and kdp_full_wrap_preview.png. Confirm the title and badge are clear at a small buyer-facing size.\n", encoding="utf-8")
    package_file(folder, "FINAL_KDP_UPLOAD_STEPS.txt", for_write=True).write_text(f"FINAL KDP UPLOAD STEPS\n{'='*48}\n1. Confirm the KDP contributor is exactly: {author}\n2. Upload 01_PRINT_UPLOADS\\interior.pdf and 01_PRINT_UPLOADS\\kdp_full_wrap.pdf.\n3. Copy the listing from 02_LISTING_INFORMATION\\KDP_LISTING_KIT.txt.\n4. Confirm rights, categories, price, territories, and any AI-content disclosure.\n5. Run KDP Print Previewer and correct every warning.\n", encoding="utf-8")
    package_file(folder, "FIX_THIS_FIRST.txt", for_write=True).write_text("FIX THIS FIRST\n"+"="*48+"\nPASS — Automated package checks passed. Your remaining required step is KDP Print Previewer.\n", encoding="utf-8")
    (folder/"START_HERE.txt").write_text(package_layout_readme(title_text),encoding="utf-8")
    package_file(folder, "PACKAGE_SCORECARD.txt", for_write=True).write_text(f"PACKAGE SCORECARD\n\nType: {kind}\nPuzzles: {count}\nDifficulty: {difficulty_description(kind, difficulty)}\nPages: {pages}\nStatus: Ready for KDP Print Previewer review\n",encoding="utf-8")
    _sync_completed_package(folder, autopilot, facts, sync_catalog=sync_catalog)
    return folder

class PuzzleBookStudio(tk.Toplevel):
    def __init__(self,parent,initial_kind="Sudoku",initial_theme="General Starter",initial_format="Standard",simple_mode=False):
        super().__init__(parent); self.title("SladePuzzleCo Puzzle Studio")
        usable_w = max(800, self.winfo_screenwidth() - 70); usable_h = max(520, self.winfo_screenheight() - 110)
        width, height = min(1040, usable_w), min(760, usable_h)
        self.geometry(f"{width}x{height}"); self.minsize(min(860, width), min(620, height)); self.transient(parent)
        self._creating = False
        self.simple_mode = simple_mode
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        selected=initial_kind if initial_kind in DEFAULTS else "Sudoku"
        selected_theme=initial_theme if initial_theme in AVAILABLE_THEMES else "General Starter"
        selected_format=initial_format if initial_format in FORMAT_PRESETS else "Standard"
        self.kind=tk.StringVar(value=selected); self.theme=tk.StringVar(value=selected_theme); self.format=tk.StringVar(value=selected_format); self.book_title=tk.StringVar(); self.subtitle=tk.StringVar(); self.count=tk.IntVar(); self.difficulty=tk.StringVar(); self.cover_style=tk.StringVar(value="Automatic matching"); self.cover_photo=tk.StringVar(value="Automatic matching"); self.interior_style=tk.StringVar(value=default_preset(selected)); self.title_page_style=tk.StringVar(value="Automatic"); self.bonus_enabled=tk.BooleanVar(value=True); self.status=tk.StringVar(value="Choose a puzzle type. Everything else can stay automatic."); self._idea_index=0; self.last_package: Path | None = None
        self._reset()
        if selected_format != "Standard": self._format_changed()
        if selected_theme != "General Starter": self._next_name_idea()
        self._build()
        self._automatic_subtitle = self.subtitle.get()
        self._automatic_count = int(self.count.get())
        self.count.trace_add('write', self._sync_count_promise)
        if not simple_mode: self.after_idle(self._maximize_window)

    def _sync_count_promise(self, *_):
        try: count = int(self.count.get())
        except (ValueError, tk.TclError): return
        if self.subtitle.get() == getattr(self, '_automatic_subtitle', None):
            old = str(getattr(self, '_automatic_count', count))
            self._automatic_subtitle = re.sub(r'\b' + old + r'\b', str(count), self.subtitle.get(), count=1)
            self.subtitle.set(self._automatic_subtitle)
        self._automatic_count = count

    def _maximize_window(self):
        """Use the available workspace while retaining normal window controls."""
        try: self.state("zoomed")
        except tk.TclError: pass
    def _on_close(self):
        if self._creating and not messagebox.askyesno("Package still being created", "This package is still being created and checked. Close this window anyway?", parent=self):
            return
        self.destroy()
    def _reset(self,*_):
        t,s,n,d=DEFAULTS[self.kind.get()]; self.book_title.set(t); self.subtitle.set(s); self.count.set(n); self.difficulty.set(d)
    def _build(self):
        if self.simple_mode:
            from publishing.family_studio import build_simple_puzzle_studio
            build_simple_puzzle_studio(self)
            return
        root=ttk.Frame(self,padding=28); root.pack(fill="both",expand=True); root.columnconfigure(0,weight=1); root.rowconfigure(3,weight=1)
        ttk.Label(root,text="PUZZLE BOOK STUDIO",font=("Segoe UI Semibold",24)).grid(row=0,column=0,sticky="w")
        ttk.Label(root,text="Choose a puzzle type, give it a direction, then review a complete print-and-listing plan before creating anything.",wraplength=920).grid(row=1,column=0,sticky="w",pady=(4,14))
        chooser=ttk.Frame(root); chooser.grid(row=2,column=0,sticky="ew",pady=(0,14)); chooser.columnconfigure((0,1,2,3),weight=1)
        self.kind_buttons={}
        for column,(kind,label) in enumerate((("Sudoku","SUDOKU\nNumbers, letters & shapes"),("Cryptogram","CRYPTOGRAMS\nCrack the hidden message"),("Word Scramble + Trivia","WORD SCRAMBLES\nFact clues for every word"),("Mixed Brain Games","MIXED BRAIN GAMES\nThree clear puzzle sections"))):
            button=ttk.Button(chooser,text=label,command=lambda value=kind:self._choose_kind(value))
            button.grid(row=0,column=column,sticky="ew",padx=(0 if column==0 else 5,0)); self.kind_buttons[kind]=button
        self._refresh_kind_buttons()
        body=ttk.Frame(root); body.grid(row=3,column=0,sticky="nsew"); body.columnconfigure(0,weight=1); body.columnconfigure(1,weight=1)
        plan=ttk.Labelframe(body,text="1. BOOK PLAN",padding=16); plan.grid(row=0,column=0,sticky="new",padx=(0,8)); plan.columnconfigure(1,weight=1)
        design=ttk.Labelframe(body,text="2. DESIGN & READER EXPERIENCE",padding=16); design.grid(row=0,column=1,sticky="new",padx=(8,0)); design.columnconfigure(1,weight=1)
        primary_fields=[("Book format",self.format),("Content theme",self.theme),("Title",self.book_title),("Subtitle",self.subtitle)]
        for row,(label,var) in enumerate(primary_fields):
            ttk.Label(plan,text=label).grid(row=row,column=0,sticky="w",pady=7)
            if label=="Book format":
                box=ttk.Combobox(plan,textvariable=var,values=tuple(FORMAT_PRESETS),state="readonly"); box.grid(row=row,column=1,sticky="ew",pady=7); box.bind("<<ComboboxSelected>>",self._format_changed)
            elif label=="Content theme":
                box=ttk.Combobox(plan,textvariable=var,values=AVAILABLE_THEMES,state="readonly"); box.grid(row=row,column=1,sticky="ew",pady=7); box.bind("<<ComboboxSelected>>",self._theme_changed)
            else: ttk.Entry(plan,textvariable=var).grid(row=row,column=1,sticky="ew",pady=7)
        ttk.Button(plan,text="Apply automatic plan",command=self._apply_blueprint,style="Primary.TButton").grid(row=4,column=0,columnspan=2,sticky="ew",pady=(14,5))
        ttk.Button(plan,text="Give me another title idea",command=self._next_name_idea).grid(row=5,column=0,columnspan=2,sticky="ew")
        design_fields=[("Cover layout",self.cover_style),("Cover picture",self.cover_photo),("Interior design",self.interior_style),("Title page",self.title_page_style),("Number of puzzles",self.count),("Difficulty",self.difficulty)]
        for row,(label,var) in enumerate(design_fields):
            ttk.Label(design,text=label).grid(row=row,column=0,sticky="w",pady=7)
            if label=="Cover layout": ttk.Combobox(design,textvariable=var,values=tuple(COVER_STYLE_OPTIONS),state="readonly").grid(row=row,column=1,sticky="ew",pady=7)
            elif label=="Cover picture":
                self.cover_photo_box=ttk.Combobox(design,textvariable=var,state="readonly"); self.cover_photo_box.grid(row=row,column=1,sticky="ew",pady=7)
            elif label=="Interior design": ttk.Combobox(design,textvariable=var,values=tuple(INTERIOR_PRESETS),state="readonly").grid(row=row,column=1,sticky="ew",pady=7)
            elif label=="Title page": ttk.Combobox(design,textvariable=var,values=("Automatic",*STYLE_LABELS.values()),state="readonly").grid(row=row,column=1,sticky="ew",pady=7)
            elif label=="Difficulty":
                self.difficulty_box=ttk.Combobox(design,textvariable=var,values=("Easy","Mixed","Standard","Hard"),state="readonly")
                self.difficulty_box.grid(row=row,column=1,sticky="ew",pady=7)
            else: ttk.Entry(design,textvariable=var).grid(row=row,column=1,sticky="ew",pady=7)
        ttk.Checkbutton(design,text="Add automatic reader bonus pages",variable=self.bonus_enabled).grid(row=6,column=0,columnspan=2,sticky="w",pady=(12,4))
        ttk.Button(design,text="Browse matching cover choices",command=self._open_cover_gallery).grid(row=7,column=0,columnspan=2,sticky="ew",pady=(8,0))
        self.art_note=ttk.Label(body,wraplength=920); self.art_note.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(18,5)); self._changed()
        actions=ttk.Labelframe(body,text="3. REVIEW & CREATE",padding=14); actions.grid(row=2,column=0,columnspan=2,sticky="ew",pady=(8,0)); actions.columnconfigure((0,1,2,3),weight=1)
        ttk.Button(actions,text="Review my book plan",command=self._review).grid(row=0,column=0,sticky="ew",padx=(0,5))
        ttk.Button(actions,text="Create + run proof gate",command=self._create,style="Primary.TButton").grid(row=0,column=1,sticky="ew",padx=5)
        ttk.Button(actions,text="Open last package",command=self._open_last_package).grid(row=0,column=2,sticky="ew",padx=5)
        ttk.Button(actions,text="Open proof report",command=self._open_proof).grid(row=0,column=3,sticky="ew",padx=(5,0))
        ttk.Label(body,textvariable=self.status,wraplength=920).grid(row=3,column=0,columnspan=2,sticky="ew",pady=(14,0))
    def _choose_kind(self, kind):
        self.kind.set(kind); self._refresh_kind_buttons(); self._changed()
    def _refresh_kind_buttons(self):
        """Keep the visible selection aligned with the generator route."""
        for kind,button in getattr(self,"kind_buttons",{}).items():
            button.configure(style="Primary.TButton" if self.kind.get()==kind else "Action.TButton")
    def _sync_difficulty_control(self):
        if hasattr(self, "difficulty_box"):
            self.difficulty_box.configure(state="disabled" if self.kind.get() in UNRATED else "readonly")

    def _changed(self,*_):
        self._sync_difficulty_control()
        self._idea_index=0; self._reset(); self._format_changed(); self._next_name_idea(); self._theme_changed()

    def _theme_changed(self,*_):
        options, palette, _style = THEME_ART.get(self.theme.get(), ART[self.kind.get()])
        photo_choices=("Automatic matching", *options)
        if hasattr(self, "cover_photo_box"):
            self.cover_photo_box.configure(values=photo_choices)
        if self.cover_photo.get() not in photo_choices:
            self.cover_photo.set("Automatic matching")
        checked, detail, capacity=content_check(self.kind.get(), self.theme.get()) if self.kind.get() in ("Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games") else (True, "Sudoku grids are generated and solution-checked when created", 0)
        library_note = f" Library: {capacity} checked entries ({detail})." if self.kind.get() in ("Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games") else ""
        difficulty_note = " " + difficulty_sentence(self.kind.get(), self.difficulty.get())
        self.art_note.configure(text=f"Cover options: {len(options)} matching local pictures, {len(COVER_STYLE_OPTIONS) - 1} layouts, and the {palette} color direction. Automatic matching rotates a fitting layout and never uses a word-search grid for this puzzle type.{library_note}{difficulty_note}")
    def _format_changed(self,*_):
        preset=FORMAT_PRESETS[self.format.get()]; self.count.set(preset["count"]); self.difficulty.set(preset["difficulty"])
        self.status.set(preset["label"])
    def _apply_blueprint(self):
        """One-click production defaults; manual controls stay available when wanted."""
        plan_kind=self.kind.get(); self.cover_style.set("Automatic matching"); self.cover_photo.set("Automatic matching")
        self.interior_style.set(default_preset(plan_kind, self.format.get() == "Signature Edition")); self.bonus_enabled.set(True)
        self._format_changed(); self._next_name_idea(); self._theme_changed()
        self.status.set(f"Applied the automatic {plan_kind} blueprint: matching cover, {self.interior_style.get()} interior, reader bonuses, and checked format defaults.")
    def _next_name_idea(self):
        ideas=name_ideas_for(self.kind.get(), self.theme.get(), int(self.count.get()))
        title_text, subtitle=ideas[self._idea_index % len(ideas)]
        self._idea_index += 1; self.book_title.set(title_text); self.subtitle.set(subtitle)
        self._automatic_subtitle = subtitle; self._automatic_count = int(self.count.get())
    def _open_cover_gallery(self):
        PuzzleCoverGallery(self)
    def _check(self):
        if not self.book_title.get().strip() or not self.subtitle.get().strip(): raise ValueError("Please enter a title and subtitle.")
        if not 24 <= int(self.count.get()) <= 150: raise ValueError("Use 24 to 150 puzzles so the book has enough interior pages.")
        validate_scramble_promise(self.kind.get(), self.theme.get(), self.book_title.get(), self.subtitle.get())
        if self.kind.get() in ("Word Scramble + Trivia", "Cryptogram", "Mixed Brain Games"):
            capacity=pack_capacity(self.kind.get(), self.theme.get()); needed=buffered_capacity_needed(int(self.count.get()))
            if capacity < needed: raise ValueError(f"The {self.theme.get()} content pack has {capacity} reviewed entries for {self.kind.get()}. This studio requires {needed} entries for a {int(self.count.get())}-puzzle book (including its safety buffer) before it will create a release package.")
    def _review(self):
        try: self._check()
        except ValueError as e: messagebox.showerror("Check your book",str(e),parent=self); return
        special=("\nSudoku extras: number, letter, and shape games." if self.kind.get()=="Sudoku" else
                 "\nMixed-book extras: a themed divider page starts each Sudoku, Cryptogram, and word-scramble section; each section has its own answers." if self.kind.get()=="Mixed Brain Games" else "")
        cover_choice = self.cover_style.get().lower() + " layout / " + self.cover_photo.get()
        bonus = "Five reader bonus pages included." if self.bonus_enabled.get() else "No reader bonus pages."
        messagebox.showinfo("Your book plan",f"Type: {self.kind.get()}\nTitle: {self.book_title.get()}\nSubtitle: {self.subtitle.get()}\nPuzzles: {self.count.get()}\nDifficulty: {difficulty_description(self.kind.get(), self.difficulty.get())}\nInterior: {self.interior_style.get()}\n{bonus}\nAuthor: Jordan M. Slade\nCover: {cover_choice}{special}\n\nThe package will include an interior PDF, full KDP wrap, listing kit, preflight, and final Production Proof Gate.",parent=self)
    def _create(self):
        try: self._check()
        except ValueError as e: messagebox.showerror("Check your book",str(e),parent=self); return
        if self._creating:
            return
        snapshot={"kind":self.kind.get(),"title":self.book_title.get().strip(),"subtitle":self.subtitle.get().strip(),"count":int(self.count.get()),"difficulty":self.difficulty.get(),"theme":self.theme.get(),"cover_style":self.cover_style.get(),"cover_photo":self.cover_photo.get(),"interior_style":self.interior_style.get(),"title_page_style":self.title_page_style.get(),"bonuses":automatic_bonus_pages(self.kind.get(), self.theme.get(), self.format.get() == "Signature Edition") if self.bonus_enabled.get() else []}
        approved=messagebox.askyesno("Approve this book plan",f"Puzzle type: {snapshot['kind']}\nTitle: {snapshot['title']}\nTheme: {snapshot['theme']}\nPuzzles: {snapshot['count']}\nDifficulty: {difficulty_description(snapshot['kind'], snapshot['difficulty'])}\n\nCreate exactly this plan and begin the checked production route?",parent=self)
        if not approved:
            self.status.set("Book plan was not approved. Nothing was created."); return
        evidence={"source":"puzzle_studio.operator_confirmation","evidence_id":hashlib.sha256(f"{snapshot['kind']}|{snapshot['title']}|{snapshot['theme']}|{snapshot['count']}|{datetime.now().isoformat()}".encode("utf-8")).hexdigest()[:20]}
        self._creating = True
        self.status.set("Creating the interior, cover, listing files, and final proof check. This can take a few minutes for Sudoku.")
        def work():
            from publishing.job_queue import ProductionJobQueue
            job_id=hashlib.sha1(f"{snapshot['kind']}|{snapshot['title']}".encode("utf-8")).hexdigest()[:12]
            queue=ProductionJobQueue(APP); acquired, note=queue.acquire(job_id, snapshot['title'])
            if not acquired:
                self.after(0,lambda: (setattr(self, "_creating", False), self.status.set(note), messagebox.showinfo("One book at a time", note, parent=self)))
                return
            try:
                folder=create_package(snapshot['kind'],snapshot['title'],snapshot['subtitle'],"Jordan M. Slade",snapshot['count'],snapshot['difficulty'],random.SystemRandom().randint(1,2**31-1),snapshot['theme'],snapshot['cover_style'],snapshot['cover_photo'],snapshot['interior_style'],snapshot['bonuses'],evidence,snapshot['title_page_style'])
                self.after(0,lambda: self._created(folder))
            except Exception as e:
                queue.release(job_id, "needs_attention")
                self.after(0,lambda detail=str(e): (setattr(self, "_creating", False), self.status.set("Something needs attention. Open the message below for the next step."),messagebox.showerror("Package could not be created",detail,parent=self)))
            else:
                queue.release(job_id, "complete")
        threading.Thread(target=work,daemon=True).start()
    def _created(self, folder: Path):
        self._creating=False; self.last_package=folder; self.status.set(f"Done — Proof Gate passed. Saved in {folder}")
        messagebox.showinfo("Package complete",f"Your complete KDP package passed the automatic Proof Gate:\n{folder}\n\nOpen the Proof Report, then run KDP Print Previewer before publishing.",parent=self)
    def _open_last_package(self):
        if self.last_package and self.last_package.exists(): os.startfile(self.last_package)
        else: messagebox.showinfo("No package yet","Create a package first.",parent=self)
    def _open_proof(self):
        from publishing.package_layout import package_file
        target=package_file(self.last_package, "PRODUCTION_PROOF_GATE.txt") if self.last_package else None
        if target and target.exists(): os.startfile(target)
        else: messagebox.showinfo("No proof report yet","Create a package first.",parent=self)


class PuzzleCoverGallery(tk.Toplevel):
    """Visual cover chooser for every non-word-search puzzle format."""
    def __init__(self, studio: PuzzleBookStudio):
        super().__init__(studio); self.studio = studio; self.title("Puzzle cover gallery")
        usable_w = max(760, self.winfo_screenwidth() - 70); usable_h = max(500, self.winfo_screenheight() - 110)
        width, height = min(1020, usable_w), min(720, usable_h)
        self.geometry(f"{width}x{height}"); self.minsize(min(800, width), min(520, height)); self.transient(studio)
        self.status = tk.StringVar(value="Rendering matching cover choices…"); self.images: list[ImageTk.PhotoImage] = []; self.options: list[dict] = []; self.refresh_offset = 0
        # Tkinter variables belong to the UI thread. Capture their values now
        # so the rendering worker never touches a Tk object.
        self.settings = {"kind": studio.kind.get(), "theme": studio.theme.get(), "title": studio.book_title.get(), "subtitle": studio.subtitle.get(), "count": int(studio.count.get())}
        root=ttk.Frame(self,padding=20); root.pack(fill="both",expand=True)
        ttk.Label(root,text="COVER GALLERY",font=("Segoe UI",18,"bold")).pack(anchor="w")
        ttk.Label(root,text="Choose approved generated or local artwork. Every thumbnail below uses the exact image named on its card; cover layout is controlled separately.",wraplength=950).pack(anchor="w",pady=(3,10))
        self.grid=ttk.Frame(root); self.grid.pack(fill="both",expand=True)
        footer=ttk.Frame(root); footer.pack(fill="x",pady=(8,0)); ttk.Label(footer,textvariable=self.status,wraplength=760).pack(side="left",fill="x",expand=True)
        ttk.Button(footer,text="Refresh Cover Ideas",command=self._refresh).pack(side="right")
        threading.Thread(target=self._render,daemon=True).start()

    def _render(self):
        kind, theme = self.settings["kind"], self.settings["theme"]
        _pictures, palette, _ = THEME_ART.get(theme, ART[kind])
        request=CoverRequest(route="Puzzle Studio Gallery",title=self.settings["title"],subtitle=self.settings["subtitle"],puzzle_type=kind,topic=theme,selection_seed=100+self.refresh_offset)
        gallery=select_cover_gallery(request,slots=6,refresh_offset=self.refresh_offset)
        folder = Path(tempfile.mkdtemp(prefix="puzzle_cover_gallery_"))
        made=[]
        for index, concept in enumerate(gallery.concepts):
            direction="Photo spotlight"
            picture=str(concept.asset.get("path") or "")
            selected_palette, style = concept.palette or palette, "photo"
            output = folder / f"cover_{index}.png"
            art_path = cover_art_path(picture)
            command=[sys.executable,str(APP/"cover.py"),"--title",self.settings["title"].strip() or DEFAULTS[kind][0],"--subtitle",self.settings["subtitle"].strip(),"--author","Jordan M. Slade","--puzzle-count",str(self.settings.get("count") or 0),"--format-label",kind.upper(),"--puzzle-type",kind,"--palette",selected_palette or palette,"--style",style,"--art",str(art_path),"--out",str(output),"--preview"]
            result=subprocess.run(command,cwd=APP,capture_output=True,text=True)
            if result.returncode == 0: made.append({"direction": direction, "picture": picture, "palette": selected_palette, "path": output, "asset_id":concept.art_asset_id,"visual_family":concept.asset.get("visual_family_id",""),"source":"Generated artwork" if concept.asset.get("project_generated") is True else "Local approved photo"})
        self.after(0,lambda:self._show(made,gallery.metrics))

    def _show(self, options: list[dict], metrics: dict | None = None) -> None:
        for child in self.grid.winfo_children(): child.destroy()
        self.images.clear()
        self.options=options
        for index, option in enumerate(options):
            card=ttk.Frame(self.grid,padding=6); card.grid(row=index//3,column=index%3,sticky="nsew",padx=6,pady=6)
            try:
                with Image.open(option["path"]).convert("RGB") as image:
                    image.thumbnail((220,285),Image.Resampling.LANCZOS)
                    photo=ImageTk.PhotoImage(image.copy())
                self.images.append(photo); ttk.Label(card,image=photo).pack()
                option["path"].unlink(missing_ok=True)
            except OSError:
                ttk.Label(card,text="Preview unavailable").pack(pady=70)
            ttk.Label(card,text=option["source"],font=("Segoe UI",10,"bold")).pack(pady=(5,0))
            ttk.Label(card,text=f"{option['palette'].replace('-', ' ').title()}\n{Path(option['picture']).name}",wraplength=220,justify="center").pack(pady=(2,5))
            ttk.Button(card,text="Use this cover",command=lambda value=option:self._choose(value)).pack(fill="x")
        if options:
            try: options[0]["path"].parent.rmdir()
            except OSError: pass
        metrics=metrics or {}; unique=metrics.get("distinct_visual_families_shown",0)
        limit_note=f" Diversity limited: only {metrics.get('eligible_visual_family_count',0)} suitable approved artwork families are available." if metrics.get("diversity_limited") else ""
        self.status.set(f"{len(options)} concepts using {unique} unique artwork families are ready.{limit_note} No new art was generated.")

    def _refresh(self) -> None:
        self.refresh_offset += 1; self.status.set("Reranking your approved existing artwork…")
        threading.Thread(target=self._render,daemon=True).start()

    def _choose(self, option: dict) -> None:
        self.studio.cover_style.set(option["direction"]); self.studio.cover_photo.set(option["picture"])
        self.studio.status.set(f"Applied {option['direction'].lower()} with {option['picture']}. Review or create when ready.")
        self.destroy()
