from publishing.activity_packs import ActivityPackPlan, PRESETS
from publishing.studio_preview import render_pack_preview, render_document


def test_actual_preview_renders_introduction_puzzle_and_matching_answers():
    plan = ActivityPackPlan(title='Space explorers', theme='Space', words=tuple(PRESETS['Space'].split()), seed=42)
    images = render_pack_preview(plan)
    assert len(images) == 3
    assert all(image.width > 600 and image.height > 800 for _, image in images)
    assert images[1][1].tobytes() != images[2][1].tobytes()
    assert images[1][1].tobytes() == render_pack_preview(plan)[1][1].tobytes()


def test_saved_cover_preview_reads_real_image_without_modifying_it(tmp_path):
    from PIL import Image
    path = tmp_path/'cover.png'
    Image.new('RGB', (300, 400), '#7652ad').save(path)
    original = path.read_bytes()
    assert render_document(path).getpixel((0,0)) == (118,82,173)
    assert path.read_bytes() == original
