from background_generation.index import BackgroundAssetIndex

def test_car_subject_outranks_generic_road_landscape():
    brief=BackgroundAssetIndex.cover_brief({"detected_topic":"Classic Cars and Road Trips","title":"Classic Cars and Road Trips Word Search","puzzle_type":"Word Search"})
    car={"topics":["car","vehicle","road","travel","automotive"]}
    scenery={"topics":["road","trip","travel","nature"]}
    assert BackgroundAssetIndex._topic_score(car,brief)>BackgroundAssetIndex._topic_score(scenery,brief)

def test_landscape_preference_is_unchanged_for_a_landscape_book():
    brief=BackgroundAssetIndex.cover_brief({"detected_topic":"Mountains","title":"Mountain Views","puzzle_type":"Word Search"})
    scenery={"topics":["mountain","mountains","nature"]}
    car={"topics":["car","vehicle","road"]}
    assert BackgroundAssetIndex._topic_score(scenery,brief)>BackgroundAssetIndex._topic_score(car,brief)
