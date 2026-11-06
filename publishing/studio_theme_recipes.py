"""Theme compositions and explicit alternatives; never rewrite bank membership."""

THEME_RECIPES = {
    'homesteading': ('Homesteading', 'Gardening', 'Home and Household', 'Farm Country and Rural Life', 'Baking and Food'),
    'homestead': ('Homesteading', 'Gardening', 'Home and Household', 'Farm Country and Rural Life', 'Baking and Food'),
}

GROUP_ALTERNATIVES = {
    'Cannabis Culture, Chill & Legal Lifestyle': ('Nature', 'Cozy Home & Simple Living'),
    'Cats & Pets': ('Cat Lover', 'Cats, Dogs & Happy Pets'),
    'Cocktail Hour, Nightlife & Social Club': ('Food, Baking & Kitchen', 'Family Fun & Everyday Life'),
    'Date Night, Romance & Relationship Fun': ('Cozy Home & Simple Living', 'Family Fun & Everyday Life'),
    'Dogs & Pets': ('Dog Breeds', 'Cats, Dogs & Happy Pets'),
    'Easter and Spring': ('Easter, Spring & New Beginnings', 'Gardening Through the Seasons'),
    'General Interest': ('Family Fun & Everyday Life', 'Travel & World Discovery'),
    'Herbs Fruits and Vegetables': ('Herbs, Vegetables & Garden Harvests', 'Garden to Table'),
    'Holidays': ('Holidays & Seasonal Fun', 'Christmas and Winter'),
    'Ocean Life': ('Coastal & Ocean Adventure', 'Coastal Lake and River Life'),
    'Responsible Firearms, Range & Outdoor Heritage': ('Outdoor Adventure, Parks & Trails', 'National Parks & Outdoors'),
    'Signature Gardening': ('Gardening', 'Gardening Through the Seasons'),
    'Thanksgiving': ('Holidays & Seasonal Fun', 'Home Cooking & Baking'),
    'Travel and Geography': ('Travel Road Trips and Getaways', 'Travel & World Discovery'),
}


def group_unavailable(topic, *, short=False):
    alternatives = GROUP_ALTERNATIVES.get(topic, ())
    message = ('This group cannot yet supply a checked activity pack.' if short else
               'This group cannot yet supply a checked full book. A shorter activity pack may be available.')
    if alternatives:
        message += ' Different themes you can choose: ' + '; '.join(alternatives) + '. These are alternatives, not replacements for your requested theme.'
    return message + ' Choose in Browse all topics. No word-bank work is needed.'
