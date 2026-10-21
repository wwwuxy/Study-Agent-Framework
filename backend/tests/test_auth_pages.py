from fastapi.testclient import TestClient


def test_auth_routes_serve_spa_without_catching_api_errors(settings, tmp_path):
    from app.main import create_app

    dist = tmp_path / "web"
    dist.mkdir()
    (dist / "index.html").write_text("<main>login-shell</main>")
    app = create_app(settings.model_copy(update={"frontend_dist": str(dist)}))
    with TestClient(app) as client:
        assert client.get("/login").text == "<main>login-shell</main>"
        assert client.get("/register").text == "<main>login-shell</main>"
        assert client.get("/api/v1/no-such-api").status_code == 404
        assert client.get("/unknown-page").status_code == 404


def test_auth_routes_without_dist_do_not_fake_a_page(settings, tmp_path):
    from app.main import create_app

    with TestClient(
        create_app(settings.model_copy(update={"frontend_dist": str(tmp_path / "missing")}))
    ) as client:
        assert client.get("/login").status_code == 404
