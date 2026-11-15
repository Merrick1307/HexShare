import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.auth_oidc import build_router


@pytest.fixture
def auth_app(monkeypatch):
    monkeypatch.delenv("HEXSHARE_OIDC_DISPLAY_NAME", raising=False)
    monkeypatch.delenv("HEXSHARE_OIDC_LOGO_URL", raising=False)
    app = FastAPI()
    app.include_router(build_router(), prefix="/api/v1")
    return app


@pytest.mark.parametrize("provider_id, name, logo_url", [
    ("google", "Google", "https://www.gstatic.com/images/branding/googleg/1x/googleg_standard_color_128dp.png"),
    ("hexiam", "HexIAM", None),
])
def test_public_config_brands_the_default_provider(auth_app, provider_id, name, logo_url):
    auth_app.state.default_oidc_idp = provider_id
    # Other configured providers must not determine the button's branding.
    auth_app.state.oidc_clients = {"hexiam": object(), "google": object()}

    with TestClient(auth_app) as client:
        response = client.get("/api/v1/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "demo_mode": False,
        "default_idp": provider_id,
        "provider": {"id": provider_id, "display_name": name, "logo_url": logo_url},
    }


@pytest.mark.parametrize("provider_id", ["google", "hexiam"])
def test_config_returns_custom_branding_and_preserves_demo_mode(auth_app, monkeypatch, provider_id):
    auth_app.state.default_oidc_idp = provider_id
    auth_app.state.demo_mode = True
    monkeypatch.setenv("HEXSHARE_OIDC_DISPLAY_NAME", "  Company SSO  ")
    monkeypatch.setenv("HEXSHARE_OIDC_LOGO_URL", "  https://cdn.example.com/sso.svg  ")
    monkeypatch.setenv("HEXSHARE_CLIENT_SECRET", "not-public")

    with TestClient(auth_app) as client:
        response = client.get("/api/v1/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "demo_mode": True,
        "default_idp": provider_id,
        "provider": {
            "id": provider_id,
            "display_name": "Company SSO",
            "logo_url": "https://cdn.example.com/sso.svg",
        },
    }
    assert "not-public" not in response.text


@pytest.mark.parametrize("provider_id, name, logo_url", [
    ("google", "Google", "https://www.gstatic.com/images/branding/googleg/1x/googleg_standard_color_128dp.png"),
    ("hexiam", "HexIAM", None),
])
def test_blank_branding_uses_defaults(auth_app, monkeypatch, provider_id, name, logo_url):
    auth_app.state.default_oidc_idp = provider_id
    monkeypatch.setenv("HEXSHARE_OIDC_DISPLAY_NAME", "  ")
    monkeypatch.setenv("HEXSHARE_OIDC_LOGO_URL", "  ")

    with TestClient(auth_app) as client:
        response = client.get("/api/v1/auth/config")

    assert response.status_code == 200
    assert response.json()["provider"] == {
        "id": provider_id, "display_name": name, "logo_url": logo_url,
    }
