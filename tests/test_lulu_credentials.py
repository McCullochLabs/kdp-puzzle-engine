from integrations.lulu.session import (
    PRODUCTION,
    SANDBOX,
    LuluCredentials,
    deserialize_credentials,
    forget_credentials,
    load_credentials,
    save_credentials,
    serialize_credentials,
    setup_report,
)


class FakeStore:
    def __init__(self):
        self.value = None

    def load(self):
        return self.value

    def save(self, credentials):
        self.value = credentials

    def forget(self):
        had_value = self.value is not None
        self.value = None
        return had_value


def test_lulu_credentials_round_trip_is_secure_and_defaults_to_sandbox():
    store = FakeStore()
    credentials = LuluCredentials("client-key", "very-secret", "sandbox")
    save_credentials(credentials, store)
    loaded = load_credentials(store)
    assert loaded.client_key == "client-key"
    assert loaded.client_secret == "very-secret"
    assert loaded.environment == SANDBOX
    assert "very-secret" not in repr(loaded)
    assert serialize_credentials(loaded)["environment"] == SANDBOX


def test_lulu_credentials_normalize_production_and_forget():
    store = FakeStore()
    save_credentials(LuluCredentials("key", "secret", "prod"), store)
    assert load_credentials(store).environment == PRODUCTION
    assert forget_credentials(store) is True
    assert forget_credentials(store) is False
    assert "not set up" in setup_report(load_credentials(store)).lower()


def test_lulu_stored_payload_accepts_unknown_environment_as_sandbox():
    loaded = deserialize_credentials({"client_key": "key", "client_secret": "secret", "environment": "future"})
    assert loaded.environment == SANDBOX
