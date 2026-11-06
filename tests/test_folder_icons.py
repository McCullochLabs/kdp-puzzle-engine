from pathlib import Path

from publishing.folder_icons import MARKER_COMMENT, create_red_folder_icon, desktop_ini_text, mark_folder_red, mark_sale_ready_folder


def test_red_folder_icon_and_windows_marker_are_created(tmp_path: Path):
    icon = create_red_folder_icon(tmp_path / "assets" / "ready.ico")
    folder = tmp_path / "out" / "book"
    folder.mkdir(parents=True)
    marker = mark_folder_red(folder, icon, apply_attributes=False)

    assert icon.is_file()
    assert icon.read_bytes()[:4] == b"\x00\x00\x01\x00"
    text = marker.read_text(encoding="utf-16")
    assert "[.ShellClassInfo]" in text
    assert f"IconResource={icon.resolve()},0" in text
    assert MARKER_COMMENT in text


def test_desktop_ini_uses_an_absolute_shared_icon_path(tmp_path: Path):
    icon = tmp_path / "folder.ico"
    value = desktop_ini_text(icon)
    assert str(icon.resolve()) in value
    assert "IconIndex=0" in value


def test_sale_ready_marker_uses_the_project_shared_icon(tmp_path: Path):
    folder = tmp_path / "out" / "book"
    folder.mkdir(parents=True)
    marker = mark_sale_ready_folder(tmp_path, folder, apply_attributes=False)
    shared = tmp_path / "assets" / "system" / "red_sale_ready_folder.ico"
    assert shared.is_file()
    assert str(shared.resolve()) in marker.read_text(encoding="utf-16")
