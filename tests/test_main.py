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


def test_spot_collection_page_renders_schema_driven_form(client):
    response = client.get("/moto/spots/collect")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "录入摩旅点位" in html
    assert "基础识别" in html
    assert "坐标" in html
    assert "可信度" in html
    assert "来源地址" in html
    assert "作者" in html


def test_spot_collection_page_builds_structured_preview(client):
    response = client.post(
        "/moto/spots/collect",
        data={
            "slug": "shenyang-station",
            "name": "沈阳骑士驿站",
            "spot_type": "moto-station",
            "city": "沈阳",
            "region": "辽中",
            "route_type": "supply-stop",
            "coordinates_lat": "41.8057",
            "coordinates_lng": "123.4315",
            "parking_friendly": "yes",
            "best_seasons": "spring, autumn",
            "ride_level": "beginner",
            "recommended_stay": "半天 / 过夜",
            "summary": "适合出发前集合、补给和过夜。",
            "photo_focus": "机车合影\n出发集结",
            "support_role": "fuel, lodging, repair",
            "moto_station_features": "可停车, 骑友集合",
            "sources_type": ["manual", ""],
            "sources_name": ["骑友口述", ""],
            "sources_url": ["https://example.com/shenyang-station", ""],
            "sources_author": ["辽东骑士老张", ""],
            "sources_verified": ["yes", ""],
            "sources_note": ["2026 春季复核", ""],
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "沈阳骑士驿站" in html
    assert "moto-station" in html
    assert "123.4315" in html
    assert "骑友集合" in html
    assert "2026 春季复核" in html
    assert "https://example.com/shenyang-station" in html
    assert "辽东骑士老张" in html
    assert "图片预览" in html
    assert "data:image/svg+xml" in html


def test_spots_index_page_renders_and_filters(client):
    response = client.get("/moto/spots?region=辽南&support=fuel")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "辽宁摩旅点位库" in html
    assert "大连滨海路" in html
    assert "适合补油" in html
    assert "本桓公路" not in html


def test_spot_image_gallery_renders_from_structured_data(client):
    detail_response = client.get("/moto/spots/liaoning/dalian-binhai-road")

    assert detail_response.status_code == 200
    detail_html = detail_response.get_data(as_text=True)
    assert "图片浏览" in detail_html
    assert "/moto/spots/liaoning/dalian-binhai-road/images/cover.svg" in detail_html
    assert "spot-gallery-main-image" in detail_html
    assert "planner-gallery__thumb" in detail_html

    image_response = client.get("/moto/spots/liaoning/dalian-binhai-road/images/cover.svg")
    assert image_response.status_code == 200
    assert image_response.mimetype == "image/svg+xml"
    svg = image_response.get_data(as_text=True)
    assert "大连滨海路" in svg
    assert "liaoning-binhai-cover" in svg


def test_approved_candidate_becomes_visible_in_formal_spot_library(client):
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    candidate_path = root / "data" / "normalized" / "candidate_spots.json"
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    rejected_path = root / "data" / "reviewed" / "rejected_spots.json"

    original_candidate = candidate_path.read_text(encoding="utf-8")
    original_approved = approved_path.read_text(encoding="utf-8")
    original_rejected = rejected_path.read_text(encoding="utf-8")

    try:
        response = client.post("/moto/spots/review/shenyang-rider-station/approve", follow_redirects=True)
        assert response.status_code == 200

        spots_response = client.get("/moto/spots")
        spots_html = spots_response.get_data(as_text=True)
        assert spots_response.status_code == 200
        assert "沈阳骑士驿站" in spots_html

        detail_response = client.get("/moto/spots/liaoning/shenyang-rider-station")
        detail_html = detail_response.get_data(as_text=True)
        assert detail_response.status_code == 200
        assert "沈阳骑士驿站" in detail_html
        assert "osm" in detail_html
    finally:
        candidate_path.write_text(original_candidate, encoding="utf-8")
        approved_path.write_text(original_approved, encoding="utf-8")
        rejected_path.write_text(original_rejected, encoding="utf-8")


def test_approved_candidate_is_highlighted_and_biases_planner_results(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    candidate_path = root / "data" / "normalized" / "candidate_spots.json"
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    rejected_path = root / "data" / "reviewed" / "rejected_spots.json"

    original_candidate = candidate_path.read_text(encoding="utf-8")
    original_approved = approved_path.read_text(encoding="utf-8")
    original_rejected = rejected_path.read_text(encoding="utf-8")

    try:
        review_response = client.post("/moto/spots/review/shenyang-rider-station/approve", follow_redirects=True)
        assert review_response.status_code == 200

        form_response = client.get("/moto/planner")
        form_html = form_response.get_data(as_text=True)
        assert form_response.status_code == 200
        assert "新批准点位" in form_html
        assert "沈阳骑士驿站 · 沈阳" in form_html

        result_response = client.post(
            "/moto/planner/result",
            data={
                "route_template": "",
                "route_region": "",
                "origin": "沈阳",
                "trip_days": "2",
                "daily_distance": "200",
                "experience_level": "beginner",
                "bike_type": "300-500cc",
                "route_preference": ["scenic", "relaxed"],
                "must_visit_spots": ["shenyang-rider-station"],
                "budget_range": "1000-2000",
                "poi_types": ["fuel", "repair", "lodging", "viewpoint"],
            },
        )

        assert result_response.status_code == 200
        result_html = result_response.get_data(as_text=True)
        assert "辽宁 2 天大连滨海轻骑线" in result_html
    finally:
        candidate_path.write_text(original_candidate, encoding="utf-8")
        approved_path.write_text(original_approved, encoding="utf-8")
        rejected_path.write_text(original_rejected, encoding="utf-8")


def test_approved_candidate_detail_recommends_existing_route_templates(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    candidate_path = root / "data" / "normalized" / "candidate_spots.json"
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    rejected_path = root / "data" / "reviewed" / "rejected_spots.json"

    original_candidate = candidate_path.read_text(encoding="utf-8")
    original_approved = approved_path.read_text(encoding="utf-8")
    original_rejected = rejected_path.read_text(encoding="utf-8")

    try:
        review_response = client.post("/moto/spots/review/shenyang-rider-station/approve", follow_redirects=True)
        assert review_response.status_code == 200

        detail_response = client.get("/moto/spots/liaoning/shenyang-rider-station")
        detail_html = detail_response.get_data(as_text=True)
        assert detail_response.status_code == 200
        assert "更适合挂入这些现有路线模板" in detail_html
        assert "辽宁 2 天大连滨海轻骑线" in detail_html
        assert "/moto/planner?route=liaoning-dalian-coast-2-day&amp;origin=沈阳" in detail_html
    finally:
        candidate_path.write_text(original_candidate, encoding="utf-8")
        approved_path.write_text(original_approved, encoding="utf-8")
        rejected_path.write_text(original_rejected, encoding="utf-8")


def test_approved_candidate_detail_shows_source_url_and_author(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    candidate_path = root / "data" / "normalized" / "candidate_spots.json"
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    rejected_path = root / "data" / "reviewed" / "rejected_spots.json"

    original_candidate = candidate_path.read_text(encoding="utf-8")
    original_approved = approved_path.read_text(encoding="utf-8")
    original_rejected = rejected_path.read_text(encoding="utf-8")

    try:
        review_response = client.post("/moto/spots/review/shenyang-rider-station/approve", follow_redirects=True)
        assert review_response.status_code == 200

        detail_response = client.get("/moto/spots/liaoning/shenyang-rider-station")
        detail_html = detail_response.get_data(as_text=True)
        assert detail_response.status_code == 200
        assert "采集来源与作者" in detail_html
        assert "osm" in detail_html
        assert "captured_at=2026-05-27" in detail_html
    finally:
        candidate_path.write_text(original_candidate, encoding="utf-8")
        approved_path.write_text(original_approved, encoding="utf-8")
        rejected_path.write_text(original_rejected, encoding="utf-8")