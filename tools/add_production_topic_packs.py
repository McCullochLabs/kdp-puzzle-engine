"""Add focused, reusable book-topic packs from existing approved topics only."""
from __future__ import annotations

import argparse, json, shutil
from datetime import datetime
from pathlib import Path

PACKS = {
    "Hiking, Trails & Trailheads": ["Outdoor Adventure", "National Parks", "Travel Road Trips and Getaways", "Nature"],
    "Camping, Campfires & the Great Outdoors": ["Outdoor Adventure", "National Parks", "Forest Wildlife and Outdoors", "Nature"],
    "Road Trips, Routes & Scenic Drives": ["Travel Road Trips and Getaways", "Vehicles & Automotive", "Travel and Geography", "National Parks"],
    "RV, Camper & Van Life": ["Vehicles & Automotive", "Travel Road Trips and Getaways", "Outdoor Adventure", "National Parks"],
    "Lakes, Rivers & Waterfalls": ["Coastal Lake and River Life", "Nature", "Outdoor Adventure", "Travel and Geography"],
    "Beach Days & Coastal Escapes": ["Ocean Life", "Coastal Lake and River Life", "Nature", "Travel and Geography"],
    "Birdwatching for Beginners": ["Birdwatching", "Birdwatching & Wildlife", "Nature", "Forest Wildlife and Outdoors"],
    "Forest Animals & Wildlife": ["Forest Wildlife and Outdoors", "Nature", "Birdwatching", "National Parks"],
    "Backyard Nature & Garden Birds": ["Birdwatching", "Nature", "Gardening", "Pets and Animal Care"],
    "Gardening Through the Seasons": ["Gardening", "Gardening and Garden Life", "Weather and Climate", "Nature"],
    "Herbs, Vegetables & Garden Harvests": ["Herbs Fruits and Vegetables", "Gardening", "Garden to Table", "Baking and Food"],
    "Farm Life & Country Living": ["Farm Country and Rural Life", "Homesteading", "Gardening", "Nature"],
    "Home Cooking & Baking": ["Baking and Food", "Herbs Fruits and Vegetables", "Garden to Table", "Home and Household"],
    "Cozy Home & Simple Living": ["Home and Household", "Wellness and Self Care", "Mindfulness", "Hobbies Crafts and Pastimes"],
    "Weather, Storms & Sky Watching": ["Weather and Climate", "Science and Discovery", "Nature", "Space & Astronomy"],
    "Stargazing & the Night Sky": ["Space & Astronomy", "Science and Discovery", "Nature"],
    "Planets, Rockets & Space Missions": ["Space & Astronomy", "Science and Discovery"],
    "Pet Care & Happy Homes": ["Pets and Animal Care", "Cat Lover", "Dog Breeds", "Home and Household"],
    "Cats, Dogs & Backyard Animals": ["Pets and Animal Care", "Cat Lover", "Dog Breeds", "Birdwatching", "Nature"],
    "Car Parts, Repairs & Garage Life": ["Vehicles & Automotive", "Careers Community and Everyday Life"],
    "Off-Road, ATVs & Outdoor Vehicles": ["Vehicles & Automotive", "Outdoor Adventure", "National Parks", "Travel Road Trips and Getaways"],
    "Family Fun & Everyday Life": ["Positive Parenting", "Careers Community and Everyday Life", "Home and Household", "Hobbies Crafts and Pastimes"],
    "Reading, Libraries & Book Lovers": ["Books Reading and Libraries", "General Interest", "Word Skills and Brain Games"],
    "Music, Instruments & Song Culture": ["Music and Instruments", "Pop Culture & Entertainment", "Hobbies Crafts and Pastimes"],
    "Arts, Crafts & Creative Hobbies": ["Arts Creativity and Making", "Hobbies Crafts and Pastimes", "Home and Household"],
    "Game Night & Brain Games": ["Word Skills and Brain Games", "Hobbies Crafts and Pastimes", "Sports and Hobbies", "General Interest"],
    "Throwback Pop Culture & Nostalgia": ["Pop Culture & Entertainment", "Nostalgia Through the Decades", "Video Games & Gaming", "Music and Instruments"],
    "U.S. Geography, Parks & Landmarks": ["US Geography and Landmarks", "National Parks", "Travel and Geography", "American History"],
}

def apply(path: Path, write: bool = False) -> dict:
    data=json.loads(path.read_text(encoding="utf-8-sig")); topics=data.get("topics", {})
    valid={name:[source for source in sources if source in topics] for name,sources in PACKS.items()}
    valid={name:sources for name,sources in valid.items() if sources}
    result={name:len(set(word for source in sources for word in topics[source])) for name,sources in valid.items()}
    report={"packs":len(valid),"two_book_ready":sum(1 for count in result.values() if count >= 1152),"capacity":dict(sorted(result.items()))}
    if write:
        backup=path.with_name(f"{path.stem}.before_production_packs_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}"); shutil.copy2(path,backup)
        packs=data.setdefault("topic_packs", {}); packs.update(valid)
        data["production_topic_packs"]={name:{"sources":sources,"word_search_capacity":result[name],"purpose":"Focused reusable production pack"} for name,sources in valid.items()}
        data["last_production_pack_update"]={"at":datetime.now().isoformat(timespec="seconds"), **report}
        temporary=path.with_suffix(path.suffix+".tmp"); temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); temporary.replace(path); report["backup"]=str(backup)
    return report

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--apply",action="store_true"); parser.add_argument("--path",type=Path,default=Path(__file__).resolve().parents[1]/"word_banks"/"Guided_Builder_Master_Word_Bank.json"); args=parser.parse_args(); print(json.dumps(apply(args.path,args.apply),indent=2))
