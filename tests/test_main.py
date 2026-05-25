def test_index_page_renders(client):
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Flask app is running" in html
    assert "port 6001" in html


def test_status_page_renders_runtime_details(client):
    response = client.get("/status")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Developer Panel" in html
    assert "Operational overview for the current Flask runtime." in html
    assert "Environment" in html
    assert "development" in html
    assert "http://127.0.0.1:6001" in html
    assert "/api/status" in html


def test_status_api_returns_runtime_details(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.get_json()
    assert data == {
        "app_name": "Flask App",
        "environment": "development",
        "host": "0.0.0.0",
        "port": 6001,
        "debug": True,
        "status": "ok",
        "local_url": "http://127.0.0.1:6001",
        "network_url": "http://0.0.0.0:6001",
        "endpoints": [
            {"label": "Landing Page", "path": "/", "kind": "page"},
            {"label": "Status Panel", "path": "/status", "kind": "page"},
            {"label": "Status API", "path": "/api/status", "kind": "json"},
        ],
    }


def test_planner_form_exposes_more_routes_and_spots(client):
    response = client.get("/moto/planner")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "优先参考路线模板" in html
    assert "想经过的打卡点" in html
    assert "辽宁 2 天大连滨海轻骑线" in html
    assert "绿江村 · 丹东宽甸" in html


def test_planner_result_honors_selected_route_template(client):
    response = client.post(
        "/moto/planner/result",
        data={
            "route_template": "liaoning-dalian-coast-2-day",
            "route_region": "north",
            "origin": "沈阳",
            "trip_days": "2",
            "daily_distance": "200",
            "experience_level": "beginner",
            "bike_type": "300-500cc",
            "route_preference": ["coast", "relaxed"],
            "must_visit_spots": ["dalian-binhai-road", "jinshitan"],
            "budget_range": "1000-2000",
            "poi_types": ["fuel", "viewpoint"],
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "辽宁 2 天大连滨海轻骑线" in html
    assert "沈阳 -&gt; 滨海路 -&gt; 棒棰岛 -&gt; 金石滩" in html
    assert "大连滨海路、金石滩" in html