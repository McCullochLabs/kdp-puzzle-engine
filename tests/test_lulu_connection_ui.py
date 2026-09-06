from pathlib import Path


def test_marketplace_connections_exposes_secure_lulu_setup_without_revealing_saved_secrets():
    source = Path("publishing/ui.py").read_text(encoding="utf-8")
    lulu_section = source.split("class LuluConnectDialog", 1)[1].split("class EtsyConnectDialog", 1)[0]
    assert "Configure Lulu" in lulu_section
    assert "show=\"•\"" in lulu_section
    assert "save_credentials(LuluCredentials" in lulu_section
    assert "Check Lulu setup" in source
