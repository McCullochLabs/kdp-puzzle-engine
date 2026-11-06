import io
from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfReader
import wordsearch

def test_long_word_list_preserves_all_targets_and_font_size():
    wordsearch.register_fonts();buffer=io.BytesIO();c=Canvas(buffer,pagesize=(612,792),initialFontName="Sans")
    words=["ACCELERATORCABLE","STEERINGCOLUMN","WINDSHIELDWIPER","DISTRIBUTORCAP","TRANSMISSION","DIFFERENTIAL","CARBURETOR","HEADLAMPS","FLYWHEEL","GEARBOX","CHASSIS","BUMPER"]
    wordsearch.draw_word_list(c,words,81,194,450,word_font=13)
    c.save();text=PdfReader(buffer).pages[0].extract_text()
    assert all(word in text for word in words)
    assert c._puzzle_text_regions[0]["font_pt"]==13

def test_full_puzzle_layout_leaves_room_for_twenty_long_targets():
    wordsearch.register_fonts();buffer=io.BytesIO();c=Canvas(buffer,pagesize=(612,792),initialFontName="Sans")
    words=["ACCELERATORCABLE","STEERINGCOLUMN","WINDSHIELDWIPER","DISTRIBUTORCAP","TRANSMISSION","DIFFERENTIAL","CARBURETOR","HEADLAMPS","FLYWHEEL","GEARBOX","CHASSIS","BUMPER","IGNITIONCOIL","SPARKPLUG","RUNNINGBOARD","CRANKSHAFT","RADIATOR","TAILPIPE","CLUTCHPEDAL","BRAKEFLUID"]
    import random
    grid,_,_=wordsearch.generate_puzzle(words,N=21,rng=random.Random(21))
    wordsearch.puzzle_page(c,1,"Workshop",grid,words,3,"Garage Days")
    c.save();text=PdfReader(buffer).pages[0].extract_text()
    assert all(word in text for word in words)
    regions=[r for r in c._puzzle_text_regions if r["role"]=="word_list"]
    assert regions[0]["font_pt"]>=12
