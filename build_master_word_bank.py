"""Build a large reusable local word bank from the active themed collections."""
from __future__ import annotations

import json
import re
from pathlib import Path
from word_search_creator import WORD_BANKS_DIR, REVIEW_REQUIRED_TERMS
from vocabulary_series_data import GRADE_VOCABULARY, words_for
from master_library_expansions import EXTRA_TOPIC_WORDS


EDUCATION_BANDS_FILE = WORD_BANKS_DIR / "source_data" / "education_grade_word_bands.json"
DICTIONARY_CATALOG_FILE = WORD_BANKS_DIR / "source_data" / "dwyl_topic_candidate_catalog.json"


def _load_education_grade_bands() -> dict[str, list[str]]:
    """Load frequency-screened grade pools; missing files simply mean no expansion."""
    try:
        payload = json.loads(EDUCATION_BANDS_FILE.read_text(encoding="utf-8"))
        bands = payload.get("bands", {})
        return {str(topic): [str(word).upper() for word in words if str(word).isalpha()]
                for topic, words in bands.items() if isinstance(words, list)}
    except (OSError, json.JSONDecodeError):
        return {}


def _dictionary_candidate_summary() -> dict[str, object]:
    """Expose candidate counts while keeping them out of generation pools."""
    try:
        payload = json.loads(DICTIONARY_CATALOG_FILE.read_text(encoding="utf-8"))
        suggestions = payload.get("suggestions_by_topic", {})
        return {
            "source": payload.get("source", "dwyl/english-words local spelling dictionary"),
            "policy": payload.get("policy", "Candidates require review before generation."),
            "counts": payload.get("counts", {}),
            "suggested_counts_by_topic": {str(topic): len(words) for topic, words in suggestions.items() if isinstance(words, list)},
            "catalog_file": str(DICTIONARY_CATALOG_FILE),
        }
    except (OSError, json.JSONDecodeError):
        return {"status": "Candidate catalog has not been built yet."}


TOPIC_FAMILY_RULES: dict[str, tuple[str, ...]] = {
    "Animals & Nature": ("Animal", "Bird", "Nature", "Ocean", "Park", "Outdoor", "Coastal", "Farm", "Garden", "Pet", "Cat", "Dog", "Reptile"),
    "Home & Wellbeing": ("Home", "Wellness", "Mindfulness", "Parent", "Homestead", "Food", "Baking", "Herbs"),
    "Learning & Word Skills": ("Vocabulary", "Science", "Space", "Books", "Word Skills"),
    "Entertainment & Hobbies": ("Pop Culture", "Video", "Sports", "Hobbies", "Arts", "Music"),
    "History, Faith & Culture": ("History", "War", "Bible", "Faith", "American", "Nostalgia", "Decade"),
    "Travel & Places": ("Travel", "Geography", "Road", "Vehicle", "State", "Landmark"),
    "Holidays & Seasons": ("Holiday", "Season", "Christmas", "Halloween", "Thanksgiving"),
}


def topic_family(topic: str) -> str:
    for family, hints in TOPIC_FAMILY_RULES.items():
        if any(hint.casefold() in topic.casefold() for hint in hints):
            return family
    return "General & Flexible"


# These are relationship links, not permission to pour one topic's full word
# list into another.  A word can be discoverable through every genuinely
# related group while a generated book still pulls only from its clean, direct
# source topic.  This protects buyer-facing relevance and improves Guided
# Builder suggestions at the same time.
RELATED_TOPIC_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("RIVER", "LAKE", "WATERFALL", "SHORE", "TRAIL", "CAMP", "HIKE", "WILDERNESS", "FOREST", "MOUNTAIN", "CANYON", "WILDLIFE"), ("Nature", "Outdoor Adventure", "National Parks", "Travel Road Trips and Getaways", "US Geography and Landmarks")),
    (("GARDEN", "FLOWER", "HERB", "SEED", "SOIL", "ORCHARD", "VEGETABLE", "HARVEST", "BEEHIVE", "CHICKEN", "FARM"), ("Gardening and Garden Life", "Homesteading", "Farm Country and Rural Life", "Home and Household")),
    (("BOOK", "READ", "WRITE", "AUTHOR", "LIBRARY", "POET", "NOVEL", "WORD", "SPELL", "VOCABULAR"), ("Books Reading and Libraries", "Word Skills and Brain Games", "Grade School Vocabulary", "Middle School Vocabulary", "High School Vocabulary")),
    (("OCEAN", "SEA", "COAST", "BEACH", "WAVE", "TIDE", "SAIL", "MARINA", "KAYAK", "CANOE"), ("Coastal Lake and River Life", "Ocean Life", "Nature", "Travel Road Trips and Getaways")),
    (("DOG", "CAT", "PET", "BIRD", "AQUARIUM", "VETERIN", "ANIMAL"), ("Pets and Animal Care", "Birdwatching", "Nature")),
    (("MUSIC", "SONG", "GUITAR", "PIANO", "CONCERT", "RHYTHM", "MELODY", "ALBUM"), ("Music and Instruments", "Pop Culture & Entertainment", "Hobbies Crafts and Pastimes")),
    (("CAR", "TRUCK", "VEHICLE", "ROAD", "RV", "CAMPER", "DRIV", "HIGHWAY", "TRAILER"), ("Vehicles & Automotive", "Travel Road Trips and Getaways", "Outdoor Adventure")),
    (("SPACE", "PLANET", "STAR", "MOON", "ROCKET", "ASTRO", "GALAX", "TELESCOPE", "ORBIT"), ("Space & Astronomy", "Science and Discovery", "Nature")),
    (("WEATHER", "CLIMATE", "STORM", "RAIN", "SNOW", "WIND", "CLOUD", "HURRICANE", "TORNADO", "THUNDER", "LIGHTNING", "FROST"), ("Weather and Climate", "Science and Discovery", "Nature", "Outdoor Adventure")),
    (("FOREST", "WILDLIFE", "RANGER", "TRAIL", "MEADOW", "PRAIRIE", "WETLAND", "MARSH", "WOODLAND", "WILDERNESS"), ("Forest Wildlife and Outdoors", "Nature", "Outdoor Adventure", "National Parks")),
    (("CHRISTMAS", "WINTER", "SNOW", "HALLOWEEN", "THANKSGIVING", "EASTER", "VALENTINE", "HOLIDAY", "HARVEST", "PUMPKIN", "AUTUMN", "FALL"), ("Holiday and Seasonal Life", "Christmas and Winter", "Halloween Autumn and Harvest", "Seasonal Celebrations", "Weather and Climate", "Nature", "Baking and Food")),
    (("BIBLE", "SCRIPTURE", "PSALM", "PRAYER", "CHURCH", "GOSPEL", "DISCIP", "APOST", "FAITH", "GRACE", "WORSHIP"), ("Bible and Faith", "Faith & Encouragement", "Faith Inspiration and Kindness")),
    (("CASSETTE", "MIXTAPE", "PAGER", "VHS", "ARCADE", "RETRO", "THROWBACK", "VINYL", "JUKEBOX"), ("Nostalgia Through the Decades", "Pop Culture & Entertainment", "Music and Instruments")),
)


def related_topics_for_word(word: str, direct_topics: set[str], available_topics: set[str]) -> set[str]:
    """Return discovery links without changing the word's direct source list."""
    related = set(direct_topics)
    for roots, targets in RELATED_TOPIC_KEYWORDS:
        if any(root in word for root in roots):
            related.update(topic for topic in targets if topic in available_topics)
    return related



# Carefully curated evergreen terms.  They supplement (rather than replace)
# words already found in saved themes, so every future rebuild preserves both.
CURATED_TOPIC_WORDS: dict[str, list[str]] = {
    "Space & Astronomy": [
        "astronomy", "astronaut", "astronautics", "asteroid", "asteroidbelt", "atmosphere", "aurora", "blackhole", "celestial", "comet", "constellation", "cosmos", "crater", "dwarfplanet", "eclipse", "equinox", "exoplanet", "galaxy", "gravity", "heliosphere", "horizon", "interstellar", "lightyear", "meteor", "meteorite", "meteoroid", "milkyway", "moon", "nebula", "observatory", "orbit", "planet", "planetarium", "satellite", "shootingstar", "solar", "solstice", "spacecraft", "spacesuit", "star", "stargazing", "supernova", "telescope", "universe", "zenith",
        "sun", "sunspot", "solarflare", "solarwind", "corona", "chromosphere", "photosphere", "helium", "hydrogen", "fusion", "sunrise", "sunset", "daylight", "nightfall",
        "mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto", "ceres", "eris", "haumea", "makemake", "rockyplanet", "terrestrial", "gasgiant", "icegiant", "innerplanet", "outerplanet", "solarsystem", "kuiperbelt", "oortcloud", "asteroidbelt", "orbitpath", "rotation", "revolution", "axis", "equinox", "perihelion", "aphelion",
        "mercurycrater", "calorisbasin", "venusclouds", "earthquake", "blueplanet", "oceans", "continents", "marsrover", "olympusmons", "vallesmarineris", "phobos", "deimos", "jupiterstorm", "greatredspot", "europa", "io", "ganymede", "callisto", "saturnrings", "titan", "enceladus", "uranusrings", "neptunewinds", "triton", "plutoheart", "charon",
        "apollo", "artemis", "voyager", "pioneer", "cassini", "juno", "hubble", "webb", "curiosity", "perseverance", "ingenuity", "newhorizons", "osirisrex", "spitzer", "kepler", "galileo", "rover", "lander", "probe", "capsule", "rocket", "launchpad", "countdown", "missioncontrol", "spacewalk", "spaceshuttle", "internationalspacestation", "crew", "payload", "booster", "thruster", "parachute", "reentry", "liftoff", "moonwalk",
        "bigdipper", "littledipper", "orion", "cassiopeia", "scorpius", "pegasus", "andromeda", "pleiades", "polaris", "sirius", "betelgeuse", "rigel", "redgiant", "whitedwarf", "neutronstar", "pulsar", "quasar", "wormhole", "darkmatter", "darkenergy", "spectroscope", "radiation", "infrared", "ultraviolet", "xray", "gamma", "magnetosphere", "moonphase", "newmoon", "fullmoon", "crescent", "gibbous", "lunar", "tidal", "eclipsepath",
    ],
    "Vehicles & Automotive": [
        "vehicle", "automobile", "car", "truck", "suv", "crossover", "minivan", "van", "wagon", "coupe", "sedan", "convertible", "hatchback", "roadster", "limousine", "pickup", "cab", "bed", "tailgate", "bumper", "grille", "hood", "trunk", "roof", "windshield", "wiper", "mirror", "headlight", "taillight", "turnsignal", "doorhandle", "seatbelt", "dashboard", "steeringwheel", "glovebox", "sunroof", "moonroof", "licenseplate",
        "ford", "chevrolet", "gmc", "cadillac", "buick", "chrysler", "dodge", "jeep", "ram", "toyota", "honda", "nissan", "subaru", "mazda", "mitsubishi", "hyundai", "kia", "volkswagen", "audi", "bmw", "mercedes", "volvo", "tesla", "lexus", "acura", "infiniti", "porsche", "ferrari", "lamborghini", "maserati", "jaguar", "landrover", "rivian", "lucid", "mustang", "corvette", "camaro", "malibu", "impala", "charger", "challenger", "durango", "wrangler", "gladiator", "bronco", "explorer", "expedition", "escape", "ranger", "maverick", "f150", "f250", "f350", "silverado", "sierra", "tahoe", "suburban", "yukon", "tacoma", "tundra", "ravfour", "highlander", "corolla", "camry", "prius", "civic", "accord", "crv", "pilot", "odyssey", "sentra", "altima", "frontier", "pathfinder", "outback", "forester", "crosstrek", "impreza", "legacy", "cxfive", "miata", "soul", "telluride", "palisade", "modelthree", "modely",
        "engine", "motor", "cylinder", "piston", "crankshaft", "camshaft", "valve", "sparkplug", "fuelinjector", "carburetor", "airfilter", "oilfilter", "oilpan", "dipstick", "radiator", "coolant", "thermostat", "waterpump", "alternator", "starter", "battery", "fuse", "wiring", "transmission", "clutch", "driveshaft", "differential", "axle", "bearing", "suspension", "shock", "strut", "spring", "controlarm", "swaybar", "brake", "brakepad", "brakerotor", "caliper", "brakefluid", "parkingbrake", "tire", "tread", "wheel", "rim", "hubcap", "alignment", "traction", "torque", "horsepower", "odometer", "speedometer", "tachometer", "accelerator",
        "turbo", "turbocharger", "supercharger", "intercooler", "coldairintake", "exhaust", "muffler", "headers", "downpipe", "catalyticconverter", "liftkit", "levelingkit", "loweringkit", "coilover", "winch", "lightbar", "roofrack", "bedliner", "tonneaucover", "runningboard", "mudflap", "offroad", "fourwheel", "allwheel", "frontwheel", "rearwheel", "manual", "automatic", "hybrid", "electric", "diesel", "gasoline", "ethanol", "charging", "range", "regenerative", "navigation", "backupcamera", "cruisecontrol", "keyless", "remote", "bluetooth", "carplay", "androidauto",
        "headunit", "amplifier", "subwoofer", "tweeter", "speaker", "equalizer", "crossover", "woofer", "soundbar", "bass", "treble", "volume", "stereo", "radio", "antenna", "dashcam", "usb", "auxiliary", "handsfree", "microphone",
        "rv", "camper", "motorhome", "traveltrailer", "fifthwheel", "popuptent", "teardrop", "toyhauler", "awning", "campsite", "hitch", "towbar", "towvehicle", "generator", "freshwater", "graywater", "blackwater", "propane", "slideout", "bunkhouse", "atv", "utv", "quad", "fourwheeler", "dirtbike", "sidebyside", "helmet", "rollcage", "trailride", "sanddune", "rockcrawling", "overland", "jeeptrail", "campinggear",
    ],
}

# Extra-friendly expansion packs.  These favor words a child, teen, or casual
# puzzle fan will recognize, while the set-based rebuild below removes repeats.
CURATED_TOPIC_WORDS["Space & Astronomy"].extend([
    "adventure", "alien", "alienworld", "amazing", "astronomer", "astronomyclub", "backyard", "beyond", "blue", "bright", "cloud", "cloudy", "cosmic", "cosmicdust", "distant", "dream", "earthshine", "explore", "explorer", "faraway", "flash", "flying", "glow", "glowing", "heavens", "journey", "magic", "midnight", "mystery", "night", "nightlight", "orbiting", "peaceful", "planetwatch", "quiet", "rainbow", "sky", "skywatcher", "sparkle", "sparkling", "starlight", "starship", "twilight", "wonder", "world", "worlds",
    "air", "airplane", "balloon", "birds", "bluebird", "breeze", "day", "dawn", "daytime", "evening", "feather", "firefly", "flashlight", "kite", "lantern", "mountain", "rain", "raincloud", "raindrop", "rainyday", "rainbow", "snow", "snowflake", "sunbeam", "sunny", "sunshine", "thunder", "weather", "wind", "windy",
    "apolloeleven", "armstrong", "buzzaldrin", "commandmodule", "discovery", "launch", "launching", "liftoff", "moonbase", "moonbuggy", "moonlanding", "moonrock", "moonraker", "moonrise", "moonshadow", "moonstone", "orbiter", "rocketship", "saturnfive", "spaceage", "spacecamp", "spacecrew", "spaceflight", "spacefood", "spacegame", "spacehome", "spacelab", "spaceman", "spacemovie", "spaceparty", "spaceplane", "spacerace", "spacestation", "spacetravel", "spacevideo", "starbase", "starbook", "starcamp", "starchart", "starfield", "stargazer", "starglow", "starjump", "starmap", "starparty", "starpath", "starrynight", "startrail", "starwatch", "universebook",
    "babyplanet", "blueplanet", "coldplanet", "giantplanet", "littleplanet", "planetbook", "planetday", "planetearth", "planetfamily", "planetguide", "planetlover", "planetquiz", "planetring", "planetscape", "planetshow", "planettrip", "redplanet", "ringedplanet", "roundplanet", "tinyplanet", "venusian", "martian", "jovian", "saturnian", "neptunian", "lunarland", "lunarrock", "moonbeam", "mooncake", "moonchild", "moondance", "moonlight", "moonmap", "moonparty", "moonphase", "moonshine", "moonwalkers", "newmoon", "nightmoon", "supermoon", "harvestmoon", "bluemoon", "eclipseglasses",
    "asteroidfield", "comettail", "cometwatch", "dustcloud", "galaxytrip", "galaxyview", "milkyway", "nebulae", "nightscape", "planetariumshow", "satelliteview", "skyguide", "skyline", "solareclipse", "starcluster", "starcolor", "stardust", "starfinder", "starfish", "starfruit", "starshine", "starspot", "telescopeview", "telescopeclub", "telescopetrip", "universequiz", "universeview", "zerogravity", "gravitygame", "spacepuzzle", "spacequest", "spacesafari", "spacescience", "spacewalkers", "cosmictrip", "cosmicview", "rocketfuel", "rocketrace", "rocketride", "rocketteam", "rockettoy", "rockettrail", "rocketwatch", "orbitgame", "orbitride", "orbitwatch", "missionpatch", "missionteam", "missionbadge", "exploremore", "sciencefair", "scienceclub", "sciencebook", "curiosity", "discoveryday", "futureworld", "imagining", "imagination",
])

CURATED_TOPIC_WORDS["Vehicles & Automotive"].extend([
    "autoshop", "carshow", "carwash", "carcare", "carseat", "carpool", "cartrip", "carride", "carpark", "carcover", "carclub", "carlover", "carbook", "cargame", "carkey", "caralarm", "carwashsoap", "driveway", "highway", "freeway", "roadtrip", "roadside", "roadmap", "roundabout", "intersection", "crosswalk", "stoplight", "trafficlight", "trafficjam", "speedlimit", "parking", "parkinglot", "gasstation", "servicebay", "dealership", "showroom", "testdrive", "driving", "driver", "passenger", "passengerseat", "frontseat", "backseat", "seatcover", "floor mat", "floormat", "cupholder", "armrest", "console", "airconditioner", "heater", "defroster", "window", "powerwindow", "doorlock", "keyfob", "ignition", "horn", "hazardlights", "dome light", "domelight",
    "beetle", "golf", "jetta", "passat", "tiguan", "atlas", "taos", "idfour", "fiesta", "focus", "fusion", "taurus", "equinox", "blazer", "trailblazer", "bolt", "colorado", "canyon", "envoy", "terrain", "acadia", "enclave", "encore", "escalade", "sorento", "sportage", "carnival", "kfive", "elantra", "sonata", "tucson", "santafe", "ioniq", "versa", "rogue", "armada", "murano", "kicks", "leaf", "maxima", "ridgeline", "passport", "hrv", "fit", "insight", "ascent", "solterra", "tribeca", "cxthirty", "cxninety", "mxfive", "eclipse", "outlander", "mirage", "chargerdaytona", "hornet", "journey", "avenger", "dart", "renegade", "wagoneer", "grandwagoneer", "patriot", "commander", "compass", "grandcherokee",
    "classiccar", "musclecar", "racecar", "sports car", "sportscar", "familycar", "citycar", "compactcar", "electriccar", "hybridcar", "luxurycar", "usedcar", "newcar", "dreamcar", "showcar", "rallycar", "policecar", "taxicab", "schoolbus", "citybus", "tourbus", "shuttlebus", "ambulance", "firetruck", "towtruck", "garbagetruck", "boxtruck", "deliveryvan", "workvan", "cargo van", "cargovan", "campervan", "minibus", "motorcycle", "scooter", "moped", "bicycle", "tricycle", "gokart", "gokarting", "monstertruck", "snowmobile", "golfcart", "farmtractor", "tractor", "forklift", "bulldozer", "excavator", "crane", "dumptruck", "cementmixer", "semitruck", "eighteenwheeler", "flatbed", "tanktruck", "pickuptruck",
    "campfire", "campground", "camping", "campsite", "campchair", "campkitchen", "campmeal", "campout", "campstore", "camptrail", "cooler", "sleepingbag", "tent", "tentdoor", "lantern", "picnictable", "marshmallow", "trailmap", "trailhead", "hiking", "hiker", "backpack", "binoculars", "fishingpole", "kayak", "canoe", "boat", "pontoon", "jet ski", "jetski", "beachtrip", "lake trip", "laketrip", "mountaintrip", "familytrip", "weekendtrip", "vacationride", "towhitch", "towrope", "trailerhitch", "trailerpark", "rvpark", "rvtrip", "rvlife", "rvliving", "campingvan", "camperlife", "motorcoach", "roadsidecamp", "offroadtrip", "dirtroad", "gravelroad", "forestroad", "mountainroad", "desertroad",
    "clean", "cleaning", "carsoap", "washbucket", "sponge", "towel", "wax", "polish", "shiny", "shine", "vacuum", "airfreshener", "freshener", "repair", "mechanic", "toolbox", "wrench", "socket", "screwdriver", "pliers", "jack", "jumpercables", "sparetire", "tiregauge", "airpump", "fuelpump", "gascap", "gasgauge", "oilchange", "tuneup", "checkup", "service", "safety", "safedriver", "drivingsafe", "seatbelt", "childseat", "boosterseat", "firstaid", "emergency", "roadhelp", "towservice", "insurance", "registration", "inspection", "ownersmanual", "carbatterycharger", "windshieldwash", "windshieldwiper", "license", "permit", "tripmeter", "mileage", "milemarker", "reststop", "snackstop", "music", "playlist", "podcast", "audiobook", "phonecharger", "mapapp", "gps",
])

CURATED_TOPIC_WORDS["Video Games & Gaming"] = [
    "arcade", "arcadegame", "arcademachine", "atari", "gameboy", "gamecube", "gamegear", "nintendo", "playstation", "xbox", "switch", "wii", "dreamcast", "genesis", "saturn", "gamepad", "controller", "joystick", "keyboard", "headset", "console", "handheld", "cartridge", "memorycard", "gamecard", "gameshelf", "gamer", "gaming", "gameplay", "gameroom", "gametime", "gamestore", "gametoken", "highscore", "leaderboard", "bonusround", "checkpoint", "cutscene", "finalboss", "gameover", "levelup", "newgame", "powerup", "savegame", "sidequest", "speedrun", "tutorial", "walkthrough", "multiplayer", "singleplayer", "onlineplay", "teammate", "scoreboard", "achievement", "trophy", "badge", "avatar", "character", "hero", "villain", "sidekick", "quest", "mission", "battle", "adventure", "puzzle", "platformer", "racing", "sports", "strategy", "roleplay", "sandbox", "simulation", "survival", "rhythm", "fighting", "shooter", "retro", "pixel", "pixelart", "eightbit", "sixteenbit", "gameplan", "gameday", "gameface", "gamezone",
    "mario", "luigi", "peach", "bowser", "yoshi", "toad", "wario", "waluigi", "dais y", "daisy", "rosalina", "donkeykong", "diddykong", "kirby", "metaknight", "dedede", "link", "zelda", "ganondorf", "hyrule", "triforce", "samus", "metroid", "pikachu", "pokemon", "eevee", "charizard", "bulbasaur", "squirtle", "jigglypuff", "snorlax", "mewtwo", "mario kart", "mariokart", "animalcrossing", "isabelle", "tomnook", "splatoon", "inkling", "pikmin", "olimar", "fireemblem", "starfox", "foxmccloud", "fzero", "kidicarus", "wiisports", "nintendogs", "brainage", "tetris", "pacman", "frogger", "galaga", "centipede", "qbert", "digdug", "asteroids", "spaceinvaders", "missilecommand", "breakout", "pong", "defender", "joust", "paperboy", "rampage", "mortal kombat", "mortalkombat", "streetfighter", "megaman", "sonic", "tails", "knuckles", "crashbandicoot", "spyro", "rayman", "lara croft", "laracroft", "tombraider", "princeofpersia", "finalfantasy", "dragonquest", "kingdomhearts", "resident evil", "residentevil", "castlevania", "contra", "metalslug", "simcity", "the sims", "thesims", "civilization", "ageofempires", "starcraft", "warcraft", "diablo", "doom", "quake", "halflife", "portal", "bioshock", "mass effect", "masseffect", "fallout", "skyrim", "elder scrolls", "elderscrolls",
    "minecraft", "creeper", "enderman", "redstone", "fortnite", "battlepass", "roblox", "amongus", "fallguys", "rocketleague", "overwatch", "valorant", "apexlegends", "callofduty", "halo", "masterchief", "forza", "gears", "fable", "seaofthieves", "grounded", "palworld", "terraria", "stardewvalley", "animalwell", "hollowknight", "cuphead", "undertale", "deltarune", "hades", "celeste", "deadcells", "slaythespire", "balatro", "subnautica", "no mans sky", "nomanssky", "eldenring", "dark souls", "darksouls", "bloodborne", "sekiro", "monsterhunter", "persona", "yakuza", "likeadragon", "assassinscreed", "farcry", "watchdogs", "grandtheftauto", "reddead", "spiderman", "godofwar", "horizon", "ratchet", "clank", "uncharted", "lastofus", "ghost of tsushima", "ghostoftsushima", "returnal", "helldivers", "astrobot", "gran turismo", "granturismo", "needforspeed", "maddennfl", "nbatwok", "fifa", "easports", "dancecentral", "guitarhero", "rockband", "justdance", "cozygame", "indiegame", "openworld", "virtualworld", "cloudgaming", "streaming", "livestream", "esports", "gamelibrary", "gamesnight", "gameparty", "gamedisc", "digitalgame", "download", "updates", "downloadable", "gamer tag", "gamertag", "friendlist", "voicechat", "partychat", "crossplay", "replay", "fanart", "fandom", "collectible", "figurine", "gameguide", "gamemusic", "soundtrack", "bossbattle", "treasurechest", "magicspell", "dragon", "castle", "spaceship", "racecar", "soccerball", "basketball", "sword", "shield", "treasure", "map", "key", "coin", "gem", "potion", "portaldoor", "victory", "champion", "winner",
]

CURATED_TOPIC_WORDS["Pop Culture & Entertainment"] = [
    "popculture", "entertainment", "celebrity", "famous", "fan", "fandom", "fanclub", "fanmail", "fanart", "trending", "trend", "viral", "iconic", "classic", "throwback", "nostalgia", "redcarpet", "premiere", "awardshow", "spotlight", "autograph", "selfie", "photograph", "magazine", "poster", "billboard", "podcast", "talkshow", "gameshow", "realityshow", "talentshow", "quizshow", "late night", "latenight", "binge", "binge watch", "bingewatch", "episode", "season", "finale", "pilot", "rerun", "streaming", "playlist", "soundtrack", "theme song", "themesong", "catchphrase", "spoiler", "cliffhanger", "blockbuster", "boxoffice", "cinema", "movie", "movie night", "movienight", "movie star", "moviestar", "film", "filmbuff", "director", "producer", "actor", "actress", "comedian", "singer", "dancer", "rapper", "band", "concert", "festival", "tour", "album", "single", "vinyl", "cassette", "cdplayer", "mixtape", "jukebox", "karaoke", "musicvideo", "radiostar", "headliner", "backstage", "encore", "microphone", "guitar", "drums", "keyboard", "bass", "melody", "chorus", "verse", "harmony", "beat", "rhythm", "popstar", "rockstar",
    "superhero", "supervillain", "comicbook", "comicstrip", "graphicnovel", "cartoon", "animation", "animated", "anime", "manga", "cosplay", "costume", "mascot", "actionfigure", "tradingcard", "collector", "collecting", "toybox", "toystore", "boardgame", "cardgame", "dollhouse", "plushie", "sticker", "keychain", "lunchbox", "tshirt", "hoodie", "sneakers", "fashion", "runway", "makeup", "hairstyle", "tattoo", "emoji", "meme", "hashtag", "influencer", "vlogger", "creator", "channel", "video", "shortvideo", "reaction", "unboxing", "challenge", "dancechallenge", "filter", "smartphone", "headphones", "earbuds", "selfiestick", "socialmedia", "internet", "website", "app", "chatroom", "screenshot", "ringtone", "textmessage", "groupchat", "trailer", "teaser", "sequel", "prequel", "remake", "reboot", "spinoff", "franchise", "crossover", "cameo", "villain", "heroine", "sidekick", "detective", "wizard", "robot", "alien", "pirate", "princess", "knight", "monster", "zombie", "vampire", "werewolf", "dragon", "unicorn", "mermaid", "spaceship", "timemachine", "secretagent", "superpower", "magic", "adventure", "mystery", "comedy", "romance", "drama", "action", "fantasy", "scifi", "western", "musical", "documentary", "thriller",
    "starwars", "jedi", "sith", "darthvader", "yoda", "skywalker", "chewbacca", "r2d2", "c3po", "lightsaber", "millenniumfalcon", "harrypotter", "hogwarts", "gryffindor", "slytherin", "hufflepuff", "ravenclaw", "muggle", "quidditch", "wand", "marvel", "avengers", "spiderman", "ironman", "captainamerica", "hulk", "thor", "blackwidow", "wolverine", "deadpool", "batman", "superman", "wonderwoman", "flash", "aquaman", "joker", "gotham", "disney", "pixar", "mickey", "minnie", "goofy", "donald", "simba", "elsa", "moana", "shrek", "spongebob", "bart simpson", "bartsimpson", "homer simpson", "homersimpson", "southpark", "friends", "seinfeld", "strangerthings", "wednesday", "bridgerton", "yellowstone", "survivor", "theoffice", "office", "greysanatomy", "doctorwho", "startrek", "doctorwho", "sherlock", "jamesbond", "indianajones", "jurassicpark", "backtothefuture", "ghostbusters", "karatekid", "rocky", "topgun", "titanic", "barbie", "legomovie", "minions", "transformers", "power rangers", "powerrangers", "turtles", "pokemon", "mario", "zelda", "sonic", "minecraft", "fortnite", "lego", "hotwheels", "barbiecore", "swiftie", "boyband", "girlgroup", "dancefloor", "disco", "hiphop", "countrymusic", "jazz", "blues", "soulmusic", "popmusic", "rockmusic", "concertticket", "fanfiction", "fan theory", "fantheory", "watchparty", "moviemarathon", "popquiz", "trivia", "trivianight", "karaokebar", "talentscout", "awardnight", "afterparty", "celebration", "birthdayparty", "sleepover", "slumberparty", "weekendfun", "saturdaynight", "sundayfunday", "familymovie", "familygame", "game night", "gamenight",
]

# Broad, familiar franchise, character, media, and play vocabulary for books
# aimed at casual fans.  The rebuild normalizes spellings and removes repeats.
CURATED_TOPIC_WORDS["Video Games & Gaming"].extend([
    "adventureisland", "afterburner", "agario", "angrybirds", "arkanoid", "armywomen", "banjokazooie", "banjotooie", "battlefield", "battletoads", "beatmania", "bomberman", "borderlands", "brawlhalla", "bubblebobble", "candycrush", "castlerush", "chronotrigger", "clashroyale", "clashofclans", "commandconquer", "cookingmama", "crazytaxi", "crusaderkings", "cyberpunk", "dancegame", "darksiders", "daysgone", "deadbydaylight", "deadspace", "deathstranding", "detroitbecomehuman", "devilmaycry", "discoelysium", "donkeykongcountry", "donkeykongjr", "dota", "duckhunt", "dungeonkeeper", "earthbound", "easportsfc", "earthwormjim", "everquest", "excitebike", "factorio", "farmingsimulator", "fatalfury", "fez", "firewatch", "flappybird", "footballmanager", "freefire", "freeride", "freestyle", "gauntlet", "gears of war", "gearsofwar", "godofwar", "goldeneye", "gradius", "grandia", "grimdawn", "guiltygear", "gunstarheroes", "halfminutelife", "harvestmoon", "hearthstone", "herostorm", "hitman", "hotline miami", "hotlinemiami", "iceclimber", "injustice", "jetgrindradio", "jetsetradio", "justcause", "katamari", "killerinstinct", "kingdomcome", "kirbysadventure", "kirbydreamland", "klonoa", "leftfourdead", "legostarwars", "lemmings", "littlebigplanet", "luigismansion", "marioparty", "mariorpg", "mariostrikers", "marvelvs capcom", "marvelvscapcom", "megadrive", "metalgear", "metalgearsolid", "metalslug", "miitopia", "minesweeper", "mirrorsedge", "monopoly", "moonlighter", "myst", "nba jam", "nbajam", "nier", "nintendoland", "nintendoswitch", "okami", "ori", "out run", "outrun", "overcooked", "paper mario", "papermario", "parappatherapper", "parappa", "payday", "peggle", "perfectdark", "phoenixwright", "pikminbloom", "plantsvszombies", "pokemon go", "pokemongo", "pokemonsnap", "pokemonstadium", "poptropica", "projectzomboid", "punchout", "quakearena", "rabbids", "rainbowsix", "ratch et", "ratchetandclank", "raymanlegends", "redfaction", "remnant", "returntomonkeyisland", "ridethell", "rimworld", "robloxstudio", "roguelegacy", "rune factory", "runefactory", "runescape", "sackboy", "saintsrow", "samandmax", "sega", "shadowofthecolossus", "shenmue", "shovelknight", "silent hill", "silenthill", "simpsonsgame", "skate", "skullgirls", "skylanders", "smashbros", "snak e", "snake", "snowrunner", "sonicmania", "soulcalibur", "southparkgame", "splintercell", "spore", "spyhunter", "star wars game", "starwarsgame", "starfield", "starwarsbattlefront", "stateofdecay", "streetsofrage", "supermeatboy", "supermariobros", "supermetroid", "supersmashbros", "systemshock", "tekken", "thedarkness", "theforest", "thewitcher", "thewalkingdead", "timesplitters", "tinytina", "titanfall", "tombraider", "tonyhawk", "torchlight", "trackmania", "tropico", "twistedmetal", "uncharted", "valheim", "vampiresurvivors", "virtua fighter", "virtuafighter", "warframe", "wario ware", "warioware", "watchdogslegion", "wehappyfew", "wii fit", "wiifit", "wiiu", "worms", "wrestlemania", "xcom", "xenoblade", "yakuza", "yoshisisland", "zeldaoracle", "zombiegames",
    "achievements", "aiming", "arcadecabinet", "backwardcompatible", "battlearena", "bossfight", "buttonmash", "campaign", "characterselect", "cheatcode", "clan", "clutch", "combo", "competitive", "crafting", "customization", "digitalstore", "difficulty", "discord", "dpad", "emote", "endgame", "equipment", "gamecapture", "gamecase", "gamecredits", "gameengine", "gamegift", "gamelobby", "gamemaster", "gamenight", "gamepass", "gameplayvideo", "gamerchair", "gamerdesk", "gamerlife", "gamerscore", "gamestream", "gametester", "gametrailer", "gifting", "grinding", "guild", "handheldgame", "healthbar", "hitpoints", "inventory", "lanparty", "loadingscreen", "loot", "lootbox", "matchmaking", "minigame", "modding", "motioncontrol", "nerf", "npc", "onlinefriend", "patchnotes", "playthrough", "ranked", "respawn", "retrogaming", "roundone", "skilltree", "squad", "streamer", "tactical", "teamwork", "topscore", "tournament", "videogame", "videogamer", "virtualreality", "vrheadset", "webcam", "wireless", "xpboost",
])

CURATED_TOPIC_WORDS["Video Games & Gaming"].extend([
    "arcadehall", "buttonpress", "gameboard", "gamebooth", "gamecorner", "gamecraft", "gamefriend", "gamehero", "gamequest", "gamerzone", "playbutton", "playtime",
])

CURATED_TOPIC_WORDS["Pop Culture & Entertainment"].extend([
    "a lister", "alister", "aftershow", "americasgot talent", "americasgottalent", "americanidol", "awardwinner", "backlot", "backstagepass", "bestseller", "bigscreen", "broadway", "cabletv", "castingcall", "celebnews", "celebritynews", "charttopper", "cinematic", "comedynight", "comiccon", "cultureclub", "cultclassic", "dancecrew", "dancehall", "daytime", "digitalart", "disneyland", "dragrace", "emmys", "fanbase", "fanexpo", "fanpage", "fanweekend", "featurefilm", "filmmaker", "filmfestival", "filmset", "firstlook", "flashmob", "follower", "followercount", "gossip", "grammys", "hitshow", "hollywood", "hollywoodsign", "instagram", "internetstar", "late show", "lateshow", "livemusic", "livestreamer", "meetandgreet", "movieclub", "moviehouse", "moviemagic", "movietheater", "musicaward", "musicchart", "musicfan", "musicfest", "musiclover", "musicstream", "networktv", "nightlife", "nominee", "numberone", "oscars", "paparazzi", "performance", "performer", "photobooth", "popart", "popcorn", "popculturequiz", "popicon", "popstar", "press tour", "presstour", "primetime", "producerchair", "recordlabel", "redcarpetlook", "reel", "remix", "reviewer", "screenplay", "showbiz", "showtime", "singalong", "socialstar", "songwriter", "stagecrew", "stageplay", "streamingservice", "superfan", "television", "theater", "ticketstub", "tiktok", "trendsetter", "tvguide", "tvshow", "varietyshow", "viewingparty", "viralvideo", "voiceactor", "webseries", "weekendwatch", "youtube", "youtuber",
    "addamsfamily", "aladdin", "aliceinwonderland", "anchorman", "avatarfilm", "beetlejuice", "bigbangtheory", "blackpanther", "blade runner", "bladerunner", "bluey", "breakingbad", "bridgeton", "brooklynninenine", "candyman", "casablanca", "charliesangels", "chicago", "cinderella", "clueless", "coco", "daredevil", "despicableme", "doctorstrange", "downtonabbey", "dumbanddumber", "dune", "encanto", "etmovie", "familyguy", "fastandfurious", "findingnemo", "frozen", "futurama", "gameofthrones", "gilmoregirls", "gladiator", "grease", "guardians", "hamilton", "hannahmontana", "hercules", "highschoolmusical", "homealone", "howimetyourmother", "insideout", "ironman", "jaws", "johnwick", "kungfupanda", "legallyblonde", "lionking", "littlemermaid", "lordoftherings", "lucasfilm", "madmax", "mandalorian", "mean girls", "meangirls", "moana", "modernfamily", "mulan", "nightmarebeforechristmas", "notebook", "oceans eleven", "oceanseleven", "oppenheimer", "paddington", "parksandrecreation", "peakyblinders", "piratesofthecaribbean", "pitchperfect", "princessbride", "pulpfiction", "queereye", "raiders", "ratatouille", "rickandmorty", "riverdale", "rockybalboa", "rudy", "sandlot", "savedbythebell", "schittscreek", "schoolofrock", "scream", "sesamestreet", "sexandthecity", "sharknado", "sixth sense", "sixthsense", "sleepyhollow", "snowwhite", "sonicmovie", "soundofmusic", "squidgame", "star trek", "startrek", "stepbrothers", "superbad", "terminator", "thebatman", "thebear", "thecrown", "thegodfather", "themask", "thematrix", "theprincessdiaries", "thewitcher", "tigerking", "trolls", "twilight", "upmovie", "wandavision", "westworld", "wicked", "willywonka", "wizards", "wolverine", "wonka", "zootopia",
    "abba", "adele", "aerosmith", "beyonce", "billieeilish", "blondie", "bonjovi", "brunomars", "carrieunderwood", "cher", "coldplay", "dollyparton", "drake", "eltonjohn", "eminem", "fleetwoodmac", "foo fighters", "foofighters", "greenday", "harry styles", "harrystyles", "janetjackson", "justinbieber", "katyperry", "kendricklamar", "ladygaga", "lilnasx", "lizz o", "lizzo", "madonna", "maroonfive", "metallica", "mileycyrus", "nirvana", "oliviarodrigo", "postmalone", "prince", "rihanna", "sabrina carpenter", "sabrinacarpenter", "shania twain", "shaniatwain", "sia", "spicegirls", "taylorswift", "thebeatles", "theweeknd", "tinaturner", "tob y keith", "tobykeith", "twentyonepilots", "usher", "whitneyhouston", "zachbryan", "boyz ii men", "boyziimen", "backstreetboys", "nsync", "newkids", "one direction", "onedirection", "jonasbrothers", "littlemix", "destinyschild", "fifthharmony", "kpop", "kpopstar", "musicidol", "rocklegend", "singer songwriter", "singersongwriter", "summerhit", "topforty", "worldtour", "dancepop", "indierock", "poprock", "punkrock", "classicrock", "alternativerock", "acoustic", "ballad", "breakdance", "choreography", "danceparty", "djset", "guitarhero", "guitarsolo", "musicawardshow", "musicfestival", "musicvenue", "openmic", "recordstore", "songlyrics", "stagefright", "synthesizer", "vinylrecord",
])

for _grade_topic in GRADE_VOCABULARY:
    CURATED_TOPIC_WORDS[_grade_topic] = words_for(_grade_topic)
for _grade_topic, _grade_words in _load_education_grade_bands().items():
    CURATED_TOPIC_WORDS[_grade_topic] = _grade_words

# Planet and vehicle names make the two large packs deeper without forcing
# technical vocabulary into a casual puzzle book.
CURATED_TOPIC_WORDS["Space & Astronomy"].extend([
    "adrastea", "amalthea", "ananke", "ariel", "atlas", "belinda", "bianca", "callirrhoe", "calypso", "carme", "carpo", "carpo", "cressida", "cordelia", "desdemona", "elara", "epimetheus", "euporie", "farbauti", "francisco", "helene", "hermippe", "himalia", "hyperion", "iapetus", "janus", "juliet", "kalyke", "kore", "leda", "lysithea", "mab", "metis", "mimas", "miranda", "narvi", "nereid", "oberon", "ophelia", "pandora", "pasiphae", "phoebe", "portia", "prometheus", "proteus", "puck", "rhea", "rosalind", "sinope", "skathi", "tethys", "thebe", "thalassa", "themis", "thrymr", "titania", "umbriel", "valetudo", "varda", "vesta", "ysabel",
    "aquarius", "aquila", "aries", "auriga", "bootes", "caelum", "camelopardalis", "canismajor", "canisminor", "capricorn", "centaurus", "cepheus", "cetus", "columba", "coma", "corvus", "crater", "cygnus", "delphinus", "dorado", "draco", "eridanus", "fornax", "gemini", "grus", "hercules", "horologium", "hydra", "lacerta", "leo", "lepus", "libra", "lupus", "lynx", "lyra", "mensa", "microscopium", "monoceros", "musca", "norma", "octans", "ophiuchus", "pavo", "perseus", "phoenix", "pictor", "pisces", "puppis", "reticulum", "sagitta", "sagittarius", "sculptor", "scutum", "serpens", "sextans", "taurus", "triangulum", "tucana", "vela", "virgo", "volans", "vulpecula",
    "aeolus", "akatsuki", "bepicolombo", "chandrayaan", "chandrayaanone", "chandrayaanthree", "chang'e", "clementine", "copernicus", "dawn", "deepimpact", "dscovr", "europaclipper", "gaia", "hayabusa", "insight", "jameswebb", "jupitericy", "lro", "luna", "lunarorbiter", "mariner", "marsodyssey", "marsreconnaissance", "maven", "messenger", "osirisrex", "parker", "psyche", "rosalindfranklin", "soho", "solarorbiter", "stardust", "tess", "viking", "vikingone", "vikingtwo", "venera", "veritas", "voyagerone", "voyagertwo", "zond",
    "astronauthelmet", "astronautpatch", "astronautteam", "countdownclock", "earthorbit", "flightplan", "goldenrecord", "launchday", "launchsite", "missionflag", "missionlogo", "missionroom", "moonmuseum", "moonphoto", "moonprobe", "moonrider", "planetphoto", "planettour", "rocketengine", "rocketlaunch", "rocketscience", "spacealbum", "spacebadge", "spaceball", "spacebook", "spacebuddy", "spacecraftwindow", "spaceexplorer", "spacegarden", "spacejournal", "spacelearning", "spaceposter", "spaceschool", "spacescout", "spaceshipwindow", "spacestory", "spacewatch", "staradventure", "staralbum", "starbadge", "starbooklet", "starcollection", "starcompass", "starjournal", "starlesson", "starmuseum", "starquest", "starreader", "starsearch", "starseason", "starshipcrew", "starstory", "startravel", "starviewer", "sunnyspace", "telescopecase", "telescopelens", "universeclub", "universeguide", "universejourney", "universemap",
])

CURATED_TOPIC_WORDS["Vehicles & Automotive"].extend([
    "accordhybrid", "aerostar", "alero", "allroad", "amigo", "ampera", "arcadia", "arietta", "astrovan", "avalon", "avalanche", "aviator", "baja", "belair", "bentayga", "berlingo", "bighorn", "bison", "bora", "breezeway", "cabriolet", "caliber", "california", "camperbus", "caprice", "captiva", "cavalier", "celica", "century", "cherokee", "chevelle", "cirrus", "clubman", "cobra", "comet", "concorde", "continental", "countryman", "cruze", "cutlass", "dakota", "delica", "deville", "discovery", "duster", "eclipse", "ecosport", "element", "elcamino", "endurance", "envoy", "escalade", "fairlane", "fairmont", "falcon", "firebird", "fleetwood", "freestar", "freestyle", "frontier", "galant", "gallardo", "gls", "golfcart", "grancoupe", "grandvitara", "horizon", "huracan", "impulse", "javelin", "jimmy", "karmannghia", "lagonda", "lancer", "landcruiser", "lebaron", "malibu", "mariner", "markviii", "matador", "matrix", "maxima", "mercurycar", "montero", "monza", "mustangmach", "nautilus", "neon", "nitro", "nova", "outback", "pacifica", "parkavenue", "passport", "pinto", "priusprime", "probe", "protege", "pulsar", "quattro", "quest", "ramcharger", "rebel", "regal", "rio", "roadmaster", "rodeo", "sable", "safari", "scout", "sequoia", "sentra", "sienna", "solstice", "sonoma", "spectra", "spirit", "sportage", "sprinter", "starion", "stratus", "suburban", "sunfire", "supra", "tercel", "territory", "thunderbird", "torino", "trailblazer", "transam", "transit", "tribeca", "tsx", "valiant", "veloster", "venture", "vibe", "viper", "voyager", "windstar", "wrangler", "xterra", "yaris", "zfour",
    "autocross", "backroad", "bikeride", "brakecheck", "caravan", "caravanpark", "carfestival", "carmeet", "carparade", "carpet", "carpetcleaner", "carsafety", "carseatcover", "carsticker", "cartooncar", "chargingcable", "chargingstation", "citydrive", "countrydrive", "cruising", "cruiser", "dashboardcam", "daytrip", "drivinggame", "drivinglesson", "drivethrough", "familyroadtrip", "fuelstop", "garage", "garageband", "garagefloor", "garagekey", "garagesale", "gearshift", "highwaydrive", "hitchball", "journeyhome", "kidseat", "longdrive", "luggage", "mapbook", "motortrip", "nightdrive", "offroadfun", "parkpass", "roadatlas", "roadgames", "roadmusic", "roadready", "roadscene", "roadsign", "roadwork", "scenicdrive", "seatpocket", "servicebook", "shorttrip", "snowdrive", "speedbump", "sunglasses", "sunnyside", "sunvisor", "tailgateparty", "tirestore", "tollbooth", "trafficcone", "travelmug", "tripbuddy", "tripplanner", "trunkspace", "tuneupday", "vehiclecare", "vehiclekey", "weekenddrive", "winterdrive", "worktruck",
])


# The old master builder harvested every active theme. A word that had slipped
# into a bad theme could then be presented as valid for a completely unrelated
# book. The clean rebuild starts only with deliberately selected source groups.
CLEAN_TOPIC_SOURCES: dict[str, tuple[str, ...]] = {
    "American Heritage": ("American History", "World War II History", "US Geography and Landmarks"),
    "American History": ("World War II History",),
    "Arts Creativity and Making": ("Arts Creativity and Making",),
    "Baking & Food": ("Hobbies Crafts and Pastimes", "Home and Household", "Seasonal Celebrations"),
    "Baking and Food": ("Hobbies Crafts and Pastimes", "Home and Household", "Seasonal Celebrations"),
    "Bible and Faith": ("Bible and Faith", "Faith Inspiration and Kindness"),
    "Birdwatching": ("Birdwatching", "Nature"),
    "Birdwatching & Wildlife": ("Birdwatching", "Nature"),
    "Cat Lover": ("Cat Lover",),
    "Careers Community and Everyday Life": ("Careers Community and Everyday Life",),
    "Cats & Pets": ("Cat Lover", "Pets and Animal Care"),
    "Dog Breeds": ("Dog Breeds",),
    "Dogs & Pets": ("Dog Breeds", "Pets and Animal Care"),
    "Faith & Encouragement": ("Faith Inspiration and Kindness", "Mindfulness"),
    "Garden to Table": ("Gardening and Garden Life", "Farm Country and Rural Life", "Home and Household"),
    "Gardening": ("Gardening and Garden Life", "Farm Country and Rural Life", "Homesteading", "Nature"),
    "Gardening & Garden Life": ("Gardening and Garden Life", "Farm Country and Rural Life", "Homesteading", "Nature"),
    "General Interest": ("Word Skills and Brain Games", "Books Reading and Libraries", "Home and Household"),
    "Grade 5 Vocabulary": ("Grade 5 Vocabulary",),
    "Grade 6 Vocabulary": ("Grade 6 Vocabulary",),
    "Grade 7 Vocabulary": ("Grade 7 Vocabulary",),
    "Grade 8 Vocabulary": ("Grade 8 Vocabulary",),
    "Grade 9 Vocabulary": ("Grade 9 Vocabulary",),
    "Grade 10 Vocabulary": ("Grade 10 Vocabulary",),
    "Grade 11 Vocabulary": ("Grade 11 Vocabulary",),
    "Grade 12 Vocabulary": ("Grade 12 Vocabulary",),
    "Grade School Vocabulary": ("Grade School Vocabulary", "Word Skills and Brain Games"),
    "Herbs Fruits and Vegetables": ("Gardening and Garden Life", "Farm Country and Rural Life", "Home and Household"),
    "High School Vocabulary": ("High School Vocabulary", "Word Skills and Brain Games"),
    "Holidays": ("Holiday and Seasonal Life", "Christmas and Winter", "Halloween Autumn and Harvest", "Seasonal Celebrations", "Weather and Climate", "Baking and Food"),
    "Christmas": ("Christmas and Winter", "Holiday and Seasonal Life", "Seasonal Celebrations", "Weather and Climate", "Baking and Food"),
    "Christmas and Winter": ("Christmas and Winter", "Holiday and Seasonal Life", "Seasonal Celebrations", "Weather and Climate", "Baking and Food"),
    "Halloween": ("Halloween Autumn and Harvest", "Holiday and Seasonal Life", "Seasonal Celebrations", "Weather and Climate", "Baking and Food"),
    "Halloween Autumn and Harvest": ("Halloween Autumn and Harvest", "Holiday and Seasonal Life", "Seasonal Celebrations", "Weather and Climate", "Baking and Food"),
    "Thanksgiving": ("Halloween Autumn and Harvest", "Holiday and Seasonal Life", "Seasonal Celebrations", "Baking and Food", "Gardening and Garden Life"),
    "Easter and Spring": ("Holiday and Seasonal Life", "Seasonal Celebrations", "Gardening and Garden Life", "Weather and Climate", "Baking and Food"),
    "Homestead Living": ("Homesteading", "Farm Country and Rural Life", "Gardening and Garden Life"),
    "Homesteading": ("Homesteading", "Farm Country and Rural Life", "Gardening and Garden Life"),
    "Middle School Vocabulary": ("Middle School Vocabulary", "Word Skills and Brain Games"),
    "Mindfulness": ("Mindfulness", "Wellness and Self Care"),
    "Mindfulness & Wellness": ("Mindfulness", "Wellness and Self Care"),
    "National Parks": ("National Parks", "Outdoor Adventure", "Forest Wildlife and Outdoors", "Nature", "US Geography and Landmarks"),
    "National Parks & Outdoors": ("National Parks", "Outdoor Adventure", "Forest Wildlife and Outdoors", "Nature", "US Geography and Landmarks"),
    "Nature": ("Nature", "Outdoor Adventure"),
    "Nostalgia Through the Decades": ("Pop Culture & Entertainment", "Music and Instruments"),
    "Ocean Life": ("Coastal Lake and River Life", "Nature"),
    "Positive Parenting": ("Positive Parenting", "Home and Household"),
    "Seasonal Celebrations": ("Seasonal Celebrations", "Nature"),
    "Signature Gardening": ("Gardening and Garden Life", "Nature"),
    "Space & Astronomy": ("Space & Astronomy", "Science and Discovery"),
    "Sports & Hobbies": ("Hobbies Crafts and Pastimes",),
    "Sports and Hobbies": ("Hobbies Crafts and Pastimes",),
    "Travel & World Discovery": ("Travel Road Trips and Getaways", "US Geography and Landmarks"),
    "Travel and Geography": ("Travel Road Trips and Getaways", "US Geography and Landmarks"),
    "Vehicles & Automotive": ("Vehicles & Automotive",),
    "Video Games & Gaming": ("Video Games & Gaming",),
    "World War II History": ("World War II History",),
    "Weather and Climate": ("Weather and Climate", "Science and Discovery", "Nature"),
    "Weather & Climate": ("Weather and Climate", "Science and Discovery", "Nature"),
    "Forest Wildlife and Outdoors": ("Forest Wildlife and Outdoors", "Nature", "Outdoor Adventure"),
    "Forest, Wildlife & Outdoors": ("Forest Wildlife and Outdoors", "Nature", "Outdoor Adventure"),
}

# Existing broad lists include some publisher-risky franchises and brand names.
# They are not useful for a fully automatic commercial word-search workflow.
EXTRA_REJECTED_TERMS = {
    "FORD", "CHEVROLET", "GMC", "CADILLAC", "BUICK", "CHRYSLER", "DODGE", "JEEP", "TOYOTA", "HONDA", "NISSAN", "SUBARU", "MAZDA", "BMW", "TESLA",
    "TETRIS", "PACMAN", "FROGGER", "GALAGA", "PONG", "MORTALKOMBAT", "STREETFIGHTER", "MEGAMAN", "CRASHBANDICOOT", "SPYRO", "MINECRAFT", "FORTNITE", "ROBLOX",
}


def _clean_source_word(value: object) -> str:
    return re.sub(r"[^A-Z]", "", str(value).upper())


def _source_words(source_name: str) -> list[str]:
    return list(CURATED_TOPIC_WORDS.get(source_name, [])) + list(EXTRA_TOPIC_WORDS.get(source_name, []))


def _word_is_safe(word: str) -> bool:
    cleaned = _clean_source_word(word)
    blocked = REVIEW_REQUIRED_TERMS | EXTRA_REJECTED_TERMS
    return 3 <= len(cleaned) <= 18 and cleaned not in {
        _clean_source_word(term) for term in blocked}


def _safe_words(source_names: tuple[str, ...]) -> set[str]:
    words: set[str] = set()
    for source_name in source_names:
        for raw_word in _source_words(source_name):
            word = _clean_source_word(raw_word)
            if word and _word_is_safe(raw_word):
                words.add(word)
    return words


APPROVED_LINKS_FILE = WORD_BANKS_DIR / "word_intelligence" / "approved_topic_links.json"


def _load_approved_links(path: Path | None = None) -> tuple[dict, dict]:
    """Load the human-curated link source written by the apply engine.

    Missing or unreadable files simply mean "no curated links yet" - bank
    builds never depend on the intelligence layer being populated.
    """
    source = Path(path) if path else APPROVED_LINKS_FILE
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
        return payload.get("links") or {}, payload.get("topic_raw_names") or {}
    except (OSError, json.JSONDecodeError):
        return {}, {}


def merge_approved_links(words_by_topic: dict[str, set[str]],
                         links: dict, topic_raw_names: dict) -> dict:
    """Fold APPROVED human decisions into generation packs (additive).

    Only pairs marked APPROVED contribute words; every candidate still passes
    the same trademark/exclusion gate as curated sources. Canonical topic ids
    without a known raw master-bank name are skipped and reported so nothing
    silently vanishes.
    """
    summary = {"approved_pairs": 0, "merged_words": 0,
               "skipped_unknown_topic": 0}
    slug_to_raw: dict[str, list[str]] = {}
    for slug, raw_names in (topic_raw_names or {}).items():
        known = [name for name in raw_names if name in words_by_topic]
        if known:
            slug_to_raw[slug] = known
    for word, topics in (links or {}).items():
        clean = _clean_source_word(word)
        for topic_id, info in (topics or {}).items():
            if not isinstance(info, dict) or info.get("status") != "approved":
                continue
            summary["approved_pairs"] += 1
            raw_names = slug_to_raw.get(topic_id)
            if not raw_names:
                summary["skipped_unknown_topic"] += 1
                continue
            if not clean or not _word_is_safe(clean):
                continue
            before = sum(len(words_by_topic[name]) for name in raw_names)
            for name in raw_names:
                words_by_topic[name].add(clean)
            added = sum(len(words_by_topic[name]) for name in raw_names) - before
            summary["merged_words"] += added
    return summary


def _dwyl_dictionary_count() -> int:
    """Confirm the optional public spelling source is available locally.

    It is intentionally not dumped into topic packs: a dictionary can tell us
    that a word exists, but it cannot tell us that it belongs in Gardening,
    National Parks, or any other buyer-facing niche.
    """
    source = WORD_BANKS_DIR / "source_data" / "dwyl_words_alpha.txt"
    try:
        return sum(1 for _ in source.open(encoding="utf-8"))
    except OSError:
        return 0


def _local_public_domain_terms(filename: str) -> set[str]:
    """Return vetted normalized terms from a local public-domain cache.

    A missing or damaged cache simply leaves the matching library unchanged.
    """
    source = WORD_BANKS_DIR / "source_data" / filename
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
        values = payload.get("terms", []) if isinstance(payload, dict) else []
    except (OSError, json.JSONDecodeError):
        return set()
    return {word for raw in values if (word := _clean_source_word(raw)) and _word_is_safe(word)}


def main() -> None:
    # Keep the actual source groups available too.  That gives the Guided Book
    # Builder more honest choices while every saved theme can still point to a
    # friendly, series-specific alias below.  Crucially, this deliberately
    # does not read active theme files: an imported off-topic book must never
    # become evidence that a word belongs in another subject.
    WORD_BANKS_DIR.mkdir(parents=True, exist_ok=True)
    target = WORD_BANKS_DIR / "Guided_Builder_Master_Word_Bank.json"
    try:
        existing = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    existing_topics = existing.get("topics", {}) if isinstance(existing.get("topics"), dict) else {}
    # Keep the most complete local snapshot available as a recovery source.
    # This is deliberately additive: a failed/older refresh must never make
    # previously curated topic vocabulary disappear from a later refresh.
    for snapshot in sorted(WORD_BANKS_DIR.glob("Guided_Builder_Master_Word_Bank.before_*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            saved = json.loads(snapshot.read_text(encoding="utf-8-sig"))
            saved_topics = saved.get("topics", {}) if isinstance(saved.get("topics"), dict) else {}
            for topic, values in saved_topics.items():
                if isinstance(values, list):
                    existing_topics.setdefault(str(topic), []).extend(values)
            break
        except (OSError, json.JSONDecodeError):
            continue
    existing_production = existing.get("production_topic_packs", {}) if isinstance(existing.get("production_topic_packs"), dict) else {}
    existing_packs = existing.get("topic_packs", {}) if isinstance(existing.get("topic_packs"), dict) else {}

    source_names = sorted({source for sources in CLEAN_TOPIC_SOURCES.values() for source in sources})
    words_by_topic = {source: _safe_words((source,)) for source in source_names}
    words_by_topic.update({topic: _safe_words(source_names) for topic, source_names in CLEAN_TOPIC_SOURCES.items()})
    approved_links, topic_raw_names = _load_approved_links()
    merge_summary = merge_approved_links(words_by_topic, approved_links, topic_raw_names)
    if merge_summary["approved_pairs"]:
        print("Approved links: merged {merged_words} curated word(s) from "
              "{approved_pairs} pair(s); skipped {skipped_unknown_topic} "
              "unknown-topic pair(s).".format(**merge_summary))
    school_groups = {
        "Grade School Vocabulary": ("Grade 5 Vocabulary", "Grade 6 Vocabulary"),
        "Middle School Vocabulary": ("Grade 7 Vocabulary", "Grade 8 Vocabulary"),
        "High School Vocabulary": ("Grade 9 Vocabulary", "Grade 10 Vocabulary", "Grade 11 Vocabulary", "Grade 12 Vocabulary"),
    }
    for group, grades in school_groups.items():
        words_by_topic[group] = set().union(*(words_by_topic.get(grade, set()) for grade in grades))
    # The current Master Library can contain prior curated expansions that are
    # not generated by the narrow source map above.  Preserve only topics that
    # are *not* already rebuilt from an explicit clean source.  Treating an old
    # theme-derived alias as a recovery source would reintroduce the exact
    # off-topic contamination this rebuild is designed to prevent.
    cleanly_rebuilt_topics = set(source_names) | set(CLEAN_TOPIC_SOURCES)
    for topic, values in existing_topics.items():
        if isinstance(values, list) and str(topic) not in cleanly_rebuilt_topics:
            words_by_topic.setdefault(str(topic), set()).update(
                str(word).upper() for word in values if str(word).strip()
            )
    # Production-only collections (for example, the adult collections) are
    # curated locally but are not represented in the general source mapping.
    # Preserve those explicit topic pools during a normal library refresh so a
    # refresh can never silently erase a production option.
    for record in existing_production.values():
        sources = record.get("sources", []) if isinstance(record, dict) else []
        for source in sources:
            if source not in words_by_topic and isinstance(existing_topics.get(source), list):
                words_by_topic[source] = set(str(word).upper() for word in existing_topics[source] if str(word).strip())
    # A cached public-domain KJV vocabulary source makes the Bible/Faith
    # portfolio deep enough for distinct books without borrowing unrelated
    # general dictionary words.  The source is local after import and is not
    # consulted by ordinary app launches.
    bible_terms = _local_public_domain_terms("public_domain_kjv_terms.json")
    if bible_terms:
        words_by_topic.setdefault("Bible and Faith", set()).update(bible_terms)
    history_terms = _local_public_domain_terms("public_domain_us_history_terms.json")
    if history_terms:
        words_by_topic.setdefault("American History", set()).update(history_terms)
    # Rebuild friendly aliases from their now-complete source pools.  This is
    # important after adding a local source cache: otherwise an alias such as
    # American Heritage could retain only its small pre-cache base and become
    # content-identical to an unrelated narrow topic in the intelligence map.
    external_source_topics = {"Bible and Faith", "American History"}
    for alias, declared_sources in CLEAN_TOPIC_SOURCES.items():
        if alias in external_source_topics:
            continue
        combined = set().union(*(words_by_topic.get(source, set()) for source in declared_sources))
        if combined:
            words_by_topic[alias] = combined
    all_words = set().union(*words_by_topic.values()) if words_by_topic else set()
    packs = {
        "Animals & Pets": ["Cat Lover", "Dog Breeds", "Birdwatching", "Nature"],
        "Backyard Birds & Nature": ["Birdwatching", "Nature", "National Parks"],
        "Coastal & Ocean Adventure": ["Ocean Life", "Travel and Geography", "Nature"],
        "Garden to Table": ["Gardening", "Signature Gardening", "Herbs Fruits and Vegetables", "Baking and Food"],
        "Homestead Living": ["Homesteading", "Gardening", "Positive Parenting", "Baking and Food"],
        "Holidays & Seasonal Fun": ["Holidays", "Holiday and Seasonal Life", "Seasonal Celebrations", "Baking and Food", "Nature", "Weather and Climate"],
        "Christmas, Winter & Cozy Traditions": ["Christmas and Winter", "Holiday and Seasonal Life", "Seasonal Celebrations", "Weather and Climate", "Baking and Food"],
        "Halloween, Autumn & Harvest": ["Halloween Autumn and Harvest", "Holiday and Seasonal Life", "Seasonal Celebrations", "Weather and Climate", "Baking and Food"],
        "Thanksgiving, Harvest & Family": ["Halloween Autumn and Harvest", "Holiday and Seasonal Life", "Baking and Food", "Gardening and Garden Life"],
        "Easter, Spring & New Beginnings": ["Holiday and Seasonal Life", "Seasonal Celebrations", "Gardening and Garden Life", "Weather and Climate", "Baking and Food"],
        "Faith & Encouragement": ["Bible and Faith", "Mindfulness"],
        "Bible, Faith & Encouragement": ["Bible and Faith", "Faith Inspiration and Kindness", "Mindfulness"],
        "Bible, Faith & Encouragement — Complete": ["Bible and Faith", "Faith Inspiration and Kindness", "Mindfulness", "Books Reading and Libraries"],
        "American Heritage": ["American History", "World War II History"],
        "Presidents, History & Americana": ["American History", "World War II History"],
        "National Parks & Outdoors": ["National Parks", "Nature", "Travel and Geography"],
        "National Parks, Trails & Wild Places": ["National Parks", "Forest Wildlife and Outdoors", "Outdoor Adventure", "Nature", "US Geography and Landmarks"],
        "Travel & World Discovery": ["Travel and Geography", "National Parks", "Ocean Life"],
        "Food, Baking & Kitchen": ["Baking and Food", "Herbs Fruits and Vegetables", "Gardening"],
        "Relaxation & Mindfulness": ["Mindfulness", "Nature", "General Interest"],
        "Mindfulness, Gratitude & Kindness": ["Mindfulness", "Faith Inspiration and Kindness", "Positive Parenting"],
        "Sports, Hobbies & Leisure": ["Sports and Hobbies", "General Interest"],
        "Hobbies, Crafts & Pastimes": ["Hobbies Crafts and Pastimes", "Sports and Hobbies", "General Interest"],
        "Family & Home": ["Positive Parenting", "Homesteading", "Baking and Food", "Gardening"],
        "Garden, Flowers & Growing Things": ["Gardening", "Gardening and Garden Life", "Nature"],
        "Gardening, Herbs & Homestead Living": ["Gardening and Garden Life", "Homesteading", "Herbs Fruits and Vegetables", "Farm Country and Rural Life", "Nature"],
        "Seasonal Holidays & Celebrations": ["Holidays", "Seasonal Celebrations", "Baking and Food", "Nature"],
        "Book Lovers, Reading & Libraries": ["Books Reading and Libraries", "General Interest"],
        "Nostalgia Through the Decades": ["General Interest", "Pop Culture & Entertainment", "Video Games & Gaming"],
        "Large-Print Friendly Themes": ["General Interest", "Mindfulness", "Nature", "Hobbies Crafts and Pastimes", "Books Reading and Libraries"],
        "Space for Kids & Teens": ["Space & Astronomy"],
        "Planets & Solar System": ["Space & Astronomy"],
        "Stargazing, Telescopes & Night Sky": ["Space & Astronomy", "Nature"],
        "Space Missions, Rockets & Astronauts": ["Space & Astronomy"],
        "Vehicles, Cars & Trucks": ["Vehicles & Automotive"],
        "Car Care, Parts & Repair": ["Vehicles & Automotive"],
        "Classic Cars, Muscle Cars & Car Shows": ["Vehicles & Automotive", "Pop Culture & Entertainment"],
        "RV, Camping & Off-Road": ["Vehicles & Automotive"],
        "Automotive Audio & Upgrades": ["Vehicles & Automotive"],
        "Family Road Trips & Travel": ["Vehicles & Automotive", "Travel and Geography", "National Parks"],
        "Retro Video Game Time": ["Video Games & Gaming", "General Interest"],
        "Modern Video Games": ["Video Games & Gaming", "Sports and Hobbies"],
        "Arcade, Consoles & Gaming Culture": ["Video Games & Gaming", "Pop Culture & Entertainment"],
        "Game Night & Pop Culture": ["Video Games & Gaming", "Pop Culture & Entertainment", "Sports and Hobbies"],
        "Movies, TV & Entertainment": ["Pop Culture & Entertainment", "General Interest"],
        "Pop Music, Media & Trends": ["Pop Culture & Entertainment", "Sports and Hobbies"],
        "Throwback Pop Culture": ["Pop Culture & Entertainment", "Video Games & Gaming", "General Interest"],
        "Birdwatching, Backyards & Wildlife": ["Birdwatching", "Nature", "Cat Lover", "Dog Breeds"],
        "Mindful Living & Family Wellness": ["Mindfulness", "Positive Parenting", "Homesteading"],
        "Grade School Vocabulary": ["Grade School Vocabulary"],
        "Middle School Vocabulary": ["Middle School Vocabulary"],
        "High School Vocabulary": ["High School Vocabulary"],
        "Vocabulary Ladder Collection": ["Grade School Vocabulary", "Middle School Vocabulary", "High School Vocabulary"],
        "Grade 5 Vocabulary": ["Grade 5 Vocabulary"],
        "Grade 6 Vocabulary": ["Grade 6 Vocabulary"],
        "Grade 7 Vocabulary": ["Grade 7 Vocabulary"],
        "Grade 8 Vocabulary": ["Grade 8 Vocabulary"],
        "Grade 9 Vocabulary": ["Grade 9 Vocabulary"],
        "Grade 10 Vocabulary": ["Grade 10 Vocabulary"],
        "Grade 11 Vocabulary": ["Grade 11 Vocabulary"],
        "Grade 12 Vocabulary": ["Grade 12 Vocabulary"],
        "Vocabulary Ladder: Grades 5–12": ["Grade 5 Vocabulary", "Grade 6 Vocabulary", "Grade 7 Vocabulary", "Grade 8 Vocabulary", "Grade 9 Vocabulary", "Grade 10 Vocabulary", "Grade 11 Vocabulary", "Grade 12 Vocabulary"],
        "Outdoor Adventure, Parks & Trails": ["Outdoor Adventure", "Nature", "National Parks", "Travel Road Trips and Getaways"],
        "Home, Cozy Living & Self Care": ["Home and Household", "Wellness and Self Care", "Mindfulness", "Hobbies Crafts and Pastimes"],
        "Pets, Backyard Animals & Care": ["Pets and Animal Care", "Cat Lover", "Dog Breeds", "Birdwatching", "Nature"],
        "Cats, Dogs & Happy Pets": ["Pets and Animal Care", "Cat Lover", "Dog Breeds", "Birdwatching", "Nature"],
        "Science, Space & Discovery": ["Science and Discovery", "Space & Astronomy", "Nature"],
        "Weather, Climate & Storms": ["Weather and Climate", "Science and Discovery", "Nature"],
        "Forests, Wildlife & Outdoor Escape": ["Forest Wildlife and Outdoors", "Nature", "Outdoor Adventure", "National Parks"],
        "Travel, Road Trips & Weekend Getaways": ["Travel Road Trips and Getaways", "Vehicles & Automotive", "Travel and Geography", "National Parks"],
        "Arts, Crafts & Creative Time": ["Arts Creativity and Making", "Hobbies Crafts and Pastimes", "Home and Household"],
        "Music, Songs & Instruments": ["Music and Instruments", "Pop Culture & Entertainment", "Hobbies Crafts and Pastimes"],
        "Farm, Country & Rural Life": ["Farm Country and Rural Life", "Homesteading", "Nature", "Gardening"],
        "Coastal, Lake & River Life": ["Coastal Lake and River Life", "Ocean Life", "Nature", "Travel and Geography"],
        "US Geography, Parks & Landmarks": ["US Geography and Landmarks", "National Parks", "Travel and Geography", "American History"],
        "Careers, Community & Everyday Life": ["Careers Community and Everyday Life", "Home and Household", "Positive Parenting"],
        "Word Skills, Puzzles & Vocabulary": ["Word Skills and Brain Games", "Grade School Vocabulary", "Middle School Vocabulary", "High School Vocabulary"],
        "Everything Library": sorted(words_by_topic),
    }
    # Keep named production packs added by the user or previous app upgrades.
    # Only retain packs whose sources remain in the refreshed library.
    for name, sources in existing_packs.items():
        if isinstance(sources, list) and name not in packs:
            valid = [source for source in sources if source in words_by_topic]
            if valid:
                packs[str(name)] = valid
    topics = {topic: sorted(words) for topic, words in sorted(words_by_topic.items())}
    topic_capacities = {
        topic: {
            "unique_words": len(words),
            "no_repeat_12_word_puzzles": len(words) // 12,
            "no_repeat_20_word_puzzles": len(words) // 20,
            "books_48_puzzles_12_words": len(words) // (48 * 12),
            "books_48_puzzles_20_words": len(words) // (48 * 20),
            "books_100_puzzles_12_words": len(words) // (100 * 12),
            "books_100_puzzles_20_words": len(words) // (100 * 20),
            "ready_for_48_puzzle_book": len(words) >= 48 * 12,
            "ready_for_100_puzzle_signature": len(words) >= 100 * 12,
            "ready_for_100_puzzle_signature_20_words": len(words) >= 100 * 20,
            "portfolio_words_2_standard_plus_signature": 2 * 48 * 12 + 100 * 12,
            "ready_for_2_standard_plus_signature": len(words) >= 2 * 48 * 12 + 100 * 12,
        }
        for topic, words in topics.items()
    }
    # Packs are what the Guided Book Builder actually offers.  Report their
    # combined repeat-free capacity too, so the app never has to guess whether
    # a friendly, multi-topic choice can support the selected book size.
    topic_pack_capacities = {}
    for pack, sources in packs.items():
        pack_words = {word for source in sources for word in topics.get(source, [])}
        topic_pack_capacities[pack] = {
            "unique_words": len(pack_words),
            "no_repeat_12_word_puzzles": len(pack_words) // 12,
            "no_repeat_20_word_puzzles": len(pack_words) // 20,
            "books_48_puzzles_12_words": len(pack_words) // (48 * 12),
            "books_48_puzzles_20_words": len(pack_words) // (48 * 20),
            "books_100_puzzles_12_words": len(pack_words) // (100 * 12),
            "books_100_puzzles_20_words": len(pack_words) // (100 * 20),
            "ready_for_48_puzzle_book": len(pack_words) >= 48 * 12,
            "ready_for_100_puzzle_signature": len(pack_words) >= 100 * 12,
            "ready_for_100_puzzle_signature_20_words": len(pack_words) >= 100 * 20,
            "portfolio_words_2_standard_plus_signature": 2 * 48 * 12 + 100 * 12,
            "ready_for_2_standard_plus_signature": len(pack_words) >= 2 * 48 * 12 + 100 * 12,
        }
    # Every word records every topic and ready-made pack it belongs to. This
    # keeps reusable words connected without dumping unrelated words into a book.
    word_groups: dict[str, set[str]] = {}
    for topic, words in topics.items():
        for word in words:
            word_groups.setdefault(word, set()).add(topic)
    for pack, sources in packs.items():
        for source in sources:
            for word in topics.get(source, []):
                word_groups.setdefault(word, set()).add(pack)
    topic_to_family = {topic: topic_family(topic) for topic in topics}
    topic_families: dict[str, list[str]] = {}
    for topic, family in topic_to_family.items():
        topic_families.setdefault(family, []).append(topic)
    for family in topic_families:
        topic_families[family].sort(key=str.casefold)
    pack_families: dict[str, list[str]] = {}
    for pack, sources in packs.items():
        family = "Everything" if pack == "Everything Library" else topic_family(str(sources[0]) if sources else pack)
        pack_families.setdefault(family, []).append(pack)
    for family in pack_families:
        pack_families[family].sort(key=str.casefold)
    word_profiles: dict[str, dict[str, list[str]]] = {}
    available_topics = set(topics)
    strict_source_topics = set(source_names)
    for word in sorted(all_words):
        direct_topics = {topic for topic in strict_source_topics if word in topics.get(topic, [])}
        # Friendly saved-theme labels are discovery links.  They must not be
        # mistaken for proof that a word originally came from that subject.
        alias_topics = {topic for topic, values in topics.items() if topic not in strict_source_topics and word in values}
        related_topics = related_topics_for_word(word, direct_topics | alias_topics, available_topics)
        word_profiles[word] = {
            # Keep this original field as the strict, direct-topic evidence
            # used by quality checks and book generation.
            "topics": sorted(direct_topics),
            "families": sorted({topic_to_family[topic] for topic in direct_topics}),
            # These additional links power search and recommendations only.
            "related_topics": sorted(related_topics),
            "related_families": sorted({topic_to_family[topic] for topic in related_topics}),
        }
    related_topic_links = {
        word: profile["related_topics"]
        for word, profile in word_profiles.items()
        if profile["related_topics"] != profile["topics"]
    }
    payload = {
        "schema_version": 5,
        "name": "Guided Builder Master Word Bank",
        "description": "Built from curated, topic-specific sources only. Words are organized into topic families, ready-made packs, strict direct-topic evidence, and reusable related-topic links.",
        "source_policy": {
            "topic_only": True,
            "active_theme_harvesting": False,
            "dwyl_english_words": "Used as a local spelling-reference source only; dictionary entries are never blindly added to a niche pack.",
            "dwyl_dictionary_entries_available": _dwyl_dictionary_count(),
        },
        "three_level_library": {
            "proven": "Direct, reviewed topic membership. These are the only words eligible for automatic book generation.",
            "suggested": "High-confidence dictionary candidates awaiting topic review. They never enter a generated book automatically.",
            "unassigned": "Searchable dictionary candidates with no trustworthy topic assignment. They remain out of topic generation.",
            "candidate_catalog": _dictionary_candidate_summary(),
        },
        # A compact, local provenance record.  It makes future refreshes
        # auditable without treating a general dictionary as topic content.
        "source_records": {
            "curated_topic_lists": {
                "purpose": "Human-reviewed, topic-specific vocabulary used for book generation.",
                "topics": sorted(CURATED_TOPIC_WORDS),
            },
            "master_library_expansions": {
                "purpose": "Additional reviewed topic vocabulary maintained with the project.",
                "topics": sorted(EXTRA_TOPIC_WORDS),
            },
            "vocabulary_series": {
                "purpose": "Grade-level vocabulary used only for the matching learning packs.",
                "grades": sorted(GRADE_VOCABULARY),
            },
            "dwyl_english_words": {
                "purpose": "Spelling reference and discovery aid only; never automatically added to a niche book.",
                "entries_available": _dwyl_dictionary_count(),
            },
            "public_domain_kjv_vocabulary": {
                "purpose": "Bible/Faith-only vocabulary extracted locally from a public-domain KJV source; never used for other niches.",
                "entries_available": len(bible_terms),
            },
            "public_domain_us_history_vocabulary": {
                "purpose": "American-History-only vocabulary extracted locally from public-domain U.S. history texts; never used for unrelated niches.",
                "entries_available": len(history_terms),
            },
        },
        "total_unique_words": len(all_words),
        "topics": topics,
        "topic_families": topic_families,
        "topic_to_family": topic_to_family,
        "topic_packs": packs,
        "pack_families": pack_families,
        "topic_capacities": topic_capacities,
        "topic_pack_capacities": topic_pack_capacities,
        "production_topic_packs": {
            str(name): {**record, "sources": [source for source in record.get("sources", []) if source in topics],
                        "word_search_capacity": len({word for source in record.get("sources", []) if source in topics for word in topics[source]}),
                        "portfolio_required_words": 2 * 48 * 12 + 100 * 12,
                        "portfolio_ready": len({word for source in record.get("sources", []) if source in topics for word in topics[source]}) >= 2 * 48 * 12 + 100 * 12}
            for name, record in existing_production.items() if isinstance(record, dict) and any(source in topics for source in record.get("sources", []))
        },
        "word_groups": {word: sorted(groups) for word, groups in sorted(word_groups.items())},
        "word_profiles": word_profiles,
        "related_topic_links": related_topic_links,
        "words": sorted(all_words),
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Built {target} with {len(all_words)} unique words across {len(words_by_topic)} topics and {len(topic_families)} topic families.")


if __name__ == "__main__":
    main()
