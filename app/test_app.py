from app import add, app


def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_add():
    assert add(2, 3) == 5


def test_index():
    r = client().get("/")
    assert r.status_code == 500
    assert "Hello" in r.get_json()["message"]


def test_health():
    r = client().get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_add_route():
    r = client().get("/add?a=2&b=3")
    assert r.get_json()["result"] == 5


def test_add_route_bad_input():
    assert client().get("/add?a=x&b=3").status_code == 400
