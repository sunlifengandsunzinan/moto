import json

import pytest


def test_index_page_renders(client):
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Flask app is running" in html
    assert "port 5000" in html


def test_status_page_renders_runtime_details(client):
    response = client.get("/status")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Developer Panel" in html
    assert "Operational overview for the current Flask runtime." in html
    assert "Environment" in html
    assert "development" in html
    assert "http://127.0.0.1:5000" in html
    assert "/api/status" in html


def test_status_api_returns_runtime_details(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.get_json()
    assert data == {
        "app_name": "Flask App",
        "environment": "development",
        "host": "0.0.0.0",
        "port": 5000,
        "debug": True,
        "status": "ok",
        "local_url": "http://127.0.0.1:5000",
        "network_url": "http://0.0.0.0:5000",
        "endpoints": [
            {"label": "Landing Page", "path": "/", "kind": "page"},
            {"label": "Status Panel", "path": "/status", "kind": "page"},
            {"label": "Status API", "path": "/api/status", "kind": "json"},
        ],
    }


def test_moto_root_redirects_to_routes_tab(client):
    response = client.get("/moto")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/moto/routes")


def test_moto_routes_page_renders_miniapp_tabbar(client):
    response = client.get("/moto/routes")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "热门摩旅路线库" in html
    assert "底部导航" in html
    assert ">路线<" in html
    assert ">打卡点<" in html
    assert ">我的<" in html
    assert "is-active\" href=\"/moto/routes\"" in html


def test_moto_routes_page_supports_day_selection_and_amap_export(client):
    response = client.get("/moto/routes?days=2")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "按骑行天数选" in html
    assert "2 天路线拆分" in html
    assert "直接导航" in html
    assert "🔥" in html
    assert "收藏 / 导航" in html
    assert "采集导航点" in html
    assert "/moto/routes/" in html


def test_moto_gpx_page_renders_batch_workflow_and_link_rules(client):
    response = client.get("/moto/gpx")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "批量贴入抖音链接" in html
    assert "支持批量视频输入" in html
    assert "只挂合格路线" in html
    assert "公里数以高德路线计算为准" in html


def test_gpx_process_api_supports_batch_urls(client, monkeypatch):
    def fake_run_gpx_process_urls(urls=None, raw_text=""):
        assert urls == ["https://www.douyin.com/video/1001", "https://www.douyin.com/video/1002"]
        assert raw_text == ""
        return {
            "ok": False,
            "mode": "batch",
            "processed": 2,
            "success_count": 1,
            "failure_count": 1,
            "results": [
                {"url": "https://www.douyin.com/video/1001", "ok": True, "stdout": "ok", "stderr": ""},
                {"url": "https://www.douyin.com/video/1002", "ok": False, "stdout": "", "stderr": "bad"},
            ],
        }

    monkeypatch.setattr("app.blueprints.api.moto.gpx_service.run_gpx_process_urls", fake_run_gpx_process_urls)

    response = client.post(
        "/api/moto/gpx/process",
        json={"urls": ["https://www.douyin.com/video/1001", "https://www.douyin.com/video/1002"]},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["mode"] == "batch"
    assert data["processed"] == 2
    assert data["success_count"] == 1
    assert data["failure_count"] == 1


def test_route_templates_only_append_qualified_route_records(monkeypatch):
    from app.services import planner_service

    qualified_waypoints = [
        {"name": "沈阳", "lat": 41.8057, "lng": 123.4315},
        {"name": "本溪", "lat": 41.3256, "lng": 123.7686},
        {"name": "桓仁", "lat": 41.2640, "lng": 125.3614},
    ]

    monkeypatch.setattr(planner_service, "load_route_templates", lambda: [])
    monkeypatch.setattr(
        planner_service.gpx_service,
        "get_processed_route_records",
        lambda limit=500: [
            {
                "title": "辽宁东线测试",
                "route_slug": "liaoning-qualified-test",
                "route_days": 2,
                "distance_km": 260,
                "gpx_path": "/tmp/liaoning-qualified-test.gpx",
                "qualification_status": "qualified",
                "waypoints_json": json.dumps(qualified_waypoints, ensure_ascii=False),
            },
            {
                "title": "不合格路线",
                "route_slug": "liaoning-rejected-test",
                "route_days": 0,
                "distance_km": 0,
                "gpx_path": "/tmp/liaoning-rejected-test.gpx",
                "qualification_status": "rejected",
                "waypoints_json": json.dumps(qualified_waypoints, ensure_ascii=False),
            },
        ],
    )
    monkeypatch.setattr(planner_service.gpx_service, "get_gpx_waypoints", lambda filename: [])
    monkeypatch.setattr(planner_service.gpx_service, "get_gpx_files", lambda: [])
    monkeypatch.setattr(planner_service.gpx_service, "get_processed_videos", lambda limit=500: [])

    routes = planner_service.get_route_templates()

    assert len(routes) == 1
    route = routes[0]
    assert route["slug"] == "liaoning-qualified-test"
    assert route["days"] == 2
    assert route["distance_km"] == 260
    assert route["navigation"]["waypoints"][0]["name"] == "沈阳"
    assert route["days_plan"][0]["distance"] == 130


def test_moto_me_page_renders_workspace_summary(client):
    response = client.get("/moto/me")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "我的摩旅" in html
    assert "路线模板" in html
    assert "查看路线库" in html
    assert "提交定制需求" in html
    assert "is-active\" href=\"/moto/me\"" in html


def test_moto_routes_and_spots_api_return_miniapp_payloads(client):
    routes_response = client.get("/api/moto/routes")
    spots_response = client.get("/api/moto/spots")

    assert routes_response.status_code == 200
    assert spots_response.status_code == 200

    routes_payload = routes_response.get_json()
    spots_payload = spots_response.get_json()

    assert "page" in routes_payload
    assert "routes" in routes_payload
    assert "featured_summary" in routes_payload
    assert "filters" in routes_payload
    assert "amap_export" in routes_payload["routes"][0]
    assert "day_quick_filters" in routes_payload["filters"]
    assert "navigation_waypoints" in routes_payload["routes"][0]
    assert "waypoints" in routes_payload["routes"][0]["amap_export"]
    assert "embed_href" in routes_payload["routes"][0]["amap_export"]
    assert "navigation_mode" in routes_payload["routes"][0]["amap_export"]
    assert "supports_coordinate_navigation" in routes_payload["routes"][0]["amap_export"]

    first_waypoint = routes_payload["routes"][0]["amap_export"]["waypoints"][0]
    assert set(first_waypoint) == {"name", "lat", "lng", "has_coordinates"}

    assert "page" in spots_payload
    assert "spots" in spots_payload
    assert "stats" in spots_payload
    assert "filters" in spots_payload


def test_primary_routes_support_coordinate_navigation_for_real_routes(client):
    payload = client.get("/api/moto/routes").get_json()
    routes_by_slug = {route["slug"]: route for route in payload["routes"]}

    primary_route_slugs = [
        "liaoning-benhuan-3-day",
        "liaoning-dalian-coast-2-day",
        "liaoning-liaodong-2-day",
        "liaoning-red-beach-2-day",
    ]

    for slug in primary_route_slugs:
        route = routes_by_slug[slug]
        assert route["amap_export"]["navigation_mode"] == "coordinates"
        assert route["amap_export"]["coordinate_waypoint_count"] == route["waypoint_count"]
        assert route["amap_export"]["supports_coordinate_navigation"] is True

    assert "callnative=1" in routes_by_slug["liaoning-benhuan-3-day"]["amap_export"]["href"]
    assert "callnative=0" in routes_by_slug["liaoning-benhuan-3-day"]["amap_export"]["browser_href"]
    assert routes_by_slug["liaoning-benhuan-3-day"]["amap_export"]["launch_href"] == "/moto/routes/liaoning-benhuan-3-day/amap-launch"
    assert "121.997%2C39.0875%2C%E9%87%91%E7%9F%B3%E6%BB%A9" in routes_by_slug["liaoning-dalian-coast-2-day"]["amap_export"]["href"]
    assert not any("demo" in slug for slug in routes_by_slug)


def test_moto_route_amap_embed_page_renders_sdk_bootstrap(client):
    response = client.get("/moto/routes/liaoning-benhuan-3-day/amap-embed")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "行途地图" in html
    assert "高德路线图" in html
    assert "高德路线图" in html
    assert "本溪" in html


def test_route_templates_prefer_navigation_config_layer():
    from app.services.planner_service import get_route_templates

    routes = get_route_templates()

    assert all("navigation" in route for route in routes)
    assert all(route["navigation"]["provider"] == "amap" for route in routes)
    assert all(route["navigation"]["waypoints"] for route in routes)
    assert all(not route.get("is_navigation_state_demo") for route in routes)


def test_moto_me_api_returns_workspace_sections(client):
    response = client.get("/api/moto/me")

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["page"]["title"] == "我的摩旅"
    assert len(payload["metrics"]) >= 4
    assert any(item["label"] == "查看路线库" for item in payload["sections"][0]["items"])
    assert any(item["label"] == "提交定制需求" for item in payload["sections"][0]["items"])
    assert any(item["label"] == "采集导航点" for item in payload["sections"][0]["items"])


def test_route_index_card_uses_coordinate_waypoints_for_amap_export():
    from app.services.planner_service import _route_index_card

    card = _route_index_card(
        {
            "slug": "coord-test",
            "title": "坐标路线测试",
            "summary": "验证高德导出会优先带经纬度。",
            "best_season": "春季",
            "difficulty": "medium",
            "days": 2,
            "distance_km": 220,
            "navigation_waypoints": [
                {"name": "杭州", "lng": 120.1551, "lat": 30.2741},
                {"name": "莫干山", "coordinates": {"lng": 119.8722, "lat": 30.5632}},
                {"name": "安吉", "longitude": 119.6803, "latitude": 30.6380},
            ],
            "days_plan": [
                {"day": 1, "title": "杭州 -> 莫干山", "distance": 120},
                {"day": 2, "title": "莫干山 -> 安吉", "distance": 100},
            ],
        }
    )

    assert card["waypoints"] == ["杭州", "莫干山", "安吉"]
    assert card["amap_export"]["navigation_mode"] == "coordinates"
    assert card["amap_export"]["supports_coordinate_navigation"] is True
    assert card["amap_export"]["coordinate_waypoint_count"] == 3
    assert card["amap_export"]["status_variant"] == "complete"
    assert card["amap_export"]["status_badge"] == "坐标完整"
    assert card["amap_export"]["status_text"] == "3/3 个点已带坐标，可直接高德逐点导航"
    assert "120.1551%2C30.2741%2C%E6%9D%AD%E5%B7%9E" in card["amap_export"]["href"]
    assert "callnative=1" in card["amap_export"]["href"]
    assert "callnative=0" in card["amap_export"]["browser_href"]
    assert card["amap_export"]["launch_href"] == "/moto/routes/coord-test/amap-launch"
    assert "119.8722%2C30.5632%2C%E8%8E%AB%E5%B9%B2%E5%B1%B1" in card["amap_export"]["href"]
    assert "119.6803%2C30.638%2C%E5%AE%89%E5%90%89" in card["amap_export"]["href"]


def test_route_index_card_marks_partial_coordinate_navigation():
    from app.services.planner_service import _route_index_card

    card = _route_index_card(
        {
            "slug": "mixed-test",
            "title": "混合导航测试",
            "summary": "验证坐标和名称混合导航状态。",
            "best_season": "秋季",
            "difficulty": "medium",
            "days": 2,
            "distance_km": 180,
            "navigation_waypoints": [
                {"name": "沈阳", "lng": 123.4315, "lat": 41.8057},
                {"name": "本溪"},
                {"name": "桓仁", "lng": 125.3614, "lat": 41.2640},
            ],
            "days_plan": [
                {"day": 1, "title": "沈阳 -> 本溪", "distance": 90},
                {"day": 2, "title": "本溪 -> 桓仁", "distance": 90},
            ],
        }
    )

    assert card["amap_export"]["navigation_mode"] == "mixed"
    assert card["amap_export"]["status_variant"] == "partial"
    assert card["amap_export"]["status_badge"] == "部分坐标"
    assert card["amap_export"]["status_text"] == "2/3 个点已带坐标，将混合坐标和地点名称导航"


def test_route_favorite_api_persists_count(client, monkeypatch, tmp_path):
    from app.services import route_engagement

    stats_path = tmp_path / "route_engagement_stats.json"
    monkeypatch.setattr(route_engagement, "ROUTE_ENGAGEMENT_PATH", stats_path)

    response = client.post("/api/moto/routes/liaoning-benhuan-3-day/favorite")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["slug"] == "liaoning-benhuan-3-day"
    assert payload["engagement"]["favorite_count"] == 1
    assert payload["engagement"]["navigation_count"] == 0
    assert payload["engagement"]["total_count"] == 1

    saved = json.loads(stats_path.read_text(encoding="utf-8"))
    assert saved["routes"]["liaoning-benhuan-3-day"]["favorite_count"] == 1


def test_route_amap_launch_persists_navigation_count(client, monkeypatch, tmp_path):
    from app.services import route_engagement

    stats_path = tmp_path / "route_engagement_stats.json"
    monkeypatch.setattr(route_engagement, "ROUTE_ENGAGEMENT_PATH", stats_path)

    response = client.get("/moto/routes/liaoning-benhuan-3-day/amap-launch")

    assert response.status_code == 200
    saved = json.loads(stats_path.read_text(encoding="utf-8"))
    assert saved["routes"]["liaoning-benhuan-3-day"]["navigation_count"] == 1


def test_routes_api_sorts_by_engagement_total(client, monkeypatch, tmp_path):
    from app.services import route_engagement

    stats_path = tmp_path / "route_engagement_stats.json"
    stats_path.write_text(
        json.dumps(
            {
                "routes": {
                    "liaoning-red-beach-2-day": {"favorite_count": 2, "navigation_count": 5},
                    "liaoning-benhuan-3-day": {"favorite_count": 1, "navigation_count": 0},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(route_engagement, "ROUTE_ENGAGEMENT_PATH", stats_path)

    payload = client.get("/api/moto/routes").get_json()

    assert payload["routes"][0]["slug"] == "liaoning-red-beach-2-day"
    assert payload["routes"][0]["engagement"]["total_count"] == 7
    assert payload["routes"][1]["slug"] == "liaoning-benhuan-3-day"


def test_route_template_loader_validates_json_schema(tmp_path, monkeypatch):
    from app.services import route_templates_config

    invalid_path = tmp_path / "route_templates.json"
    invalid_path.write_text(
        '[{"slug": "bad-route", "navigation": {"provider": "amap", "waypoints": [{"name": "杭州"}, {"name": "安吉"}]}, "days_plan": [{"day": 1, "title": "杭州 -> 安吉", "distance": 100, "ride_time": "4h", "highlights": ["测试"], "note": "测试"}], "pois": {"fuel": []}, "region": "east", "days": 2, "difficulty": "easy", "scenery_type": ["scenic"], "bike_types": ["150-250cc"], "experience_levels": ["beginner"], "best_season": "春季", "distance_km": 100, "budget_range": "1000-2000", "summary": "bad", "spot_slugs": []}]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"route\[bad-route\]\.title must be a non-empty string"):
        route_templates_config.validate_route_templates_file(invalid_path)


def test_route_collection_page_and_api_expose_collection_entry(client):
    response = client.get("/moto/routes/collect?route=liaoning-benhuan-3-day")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "路线坐标采集" in html
    assert "建议先采成这份 JSON" in html
    assert "python scripts/validate_route_templates.py" in html
    assert "坐标完整" in html

    payload = client.get("/api/moto/routes/collect/schema?route=liaoning-benhuan-3-day").get_json()
    assert payload["selected_route"]["slug"] == "liaoning-benhuan-3-day"
    assert payload["selected_route"]["amap_export"]["status_variant"] == "complete"
    assert payload["selected_route_seed"]["route_slug"] == "liaoning-benhuan-3-day"
    assert any(field["name"] == "navigation.waypoints[]" for field in payload["schema"])
def test_planner_form_exposes_more_routes_and_spots(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    original_approved = approved_path.read_text(encoding="utf-8")

    try:
        approved_path.write_text(
            '[{"slug": "planner-form-spot", "name": "绿江村", "city": "丹东宽甸", "region": "辽东", "route_type": "riverside-village", "summary": "测试点位", "photo_focus": ["江景"], "support_role": ["viewpoint"]}]\n',
            encoding="utf-8",
        )

        response = client.get("/moto/planner")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "优先参考路线模板" in html
        assert "想经过的打卡点" in html
        assert "辽宁 2 天大连滨海轻骑线" in html
        assert "绿江村 · 丹东宽甸" in html
    finally:
        approved_path.write_text(original_approved, encoding="utf-8")


def test_planner_result_honors_selected_route_template(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    original_approved = approved_path.read_text(encoding="utf-8")

    try:
        approved_path.write_text(
            """[
  {"slug": "dalian-binhai-road", "name": "大连滨海路", "city": "大连", "region": "辽南", "route_type": "coast", "summary": "测试滨海路", "photo_focus": ["海边弯道"], "support_role": ["fuel", "viewpoint"], "image_key": "liaoning-binhai-cover"},
  {"slug": "jinshitan", "name": "金石滩", "city": "大连", "region": "辽南", "route_type": "coast-scenic", "summary": "测试金石滩", "photo_focus": ["海岸景观"], "support_role": ["fuel", "viewpoint"], "image_key": "liaoning-jinshi-cover"}
]\n""",
            encoding="utf-8",
        )

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
    finally:
        approved_path.write_text(original_approved, encoding="utf-8")


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
    assert "清空所有数据" in html
    assert "删除选中的已审批数据" in html
    assert "确认清空所有审核数据吗？该操作会同时删除待审核、已批准和已拒绝数据。" in html


def test_spot_collection_page_shows_video_review_insights_and_keyframes(client):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        candidate_path = root / "data" / "normalized" / "candidate_spots.json"
        keyframe_dir = root / "data" / "raw" / "openclaw_keyframes" / "dy-test"
        keyframe_path = keyframe_dir / "frame-01.jpg"
    video_dir = root / "data" / "raw" / "douyin_videos"
    video_path = video_dir / "video-review-candidate.mp4"
        original_candidate = candidate_path.read_text(encoding="utf-8")

        keyframe_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)
        keyframe_path.write_bytes(b"fake-jpeg-data")
    video_path.write_bytes(b"fake-mp4-data")

        try:
                candidate_path.write_text(
                        """[
    {
        "slug": "video-review-candidate",
        "name": "视频审核候选",
        "city": "",
        "region": "",
        "route_type": "",
        "summary": "",
        "confidence_score": "B",
        "sources": [],
        "video_url": "https://example.com/test-video.mp4",
        "local_video_path": "data/raw/douyin_videos/video-review-candidate.mp4",
        "keyframe_paths": ["data/raw/openclaw_keyframes/dy-test/frame-01.jpg"],
        "video_analysis": {
            "summary": "海边夜骑观景点",
            "transcript": "这里是大连滨海路，适合夜骑打卡",
            "ocrText": "滨海路 观景 停车",
            "placeHints": ["大连"],
            "routeHints": ["coast"]
        },
        "fixed_spot_info": {
            "city": "大连",
            "region": "辽南",
            "poiType": "scenic-spot",
            "routeType": "coast",
            "supportTags": ["viewpoint"],
            "spotMarkers": ["checkin-point"],
            "photoTags": ["夜景"],
            "summary": "固定点位信息"
        }
    }
]\n""",
                        encoding="utf-8",
                )

                response = client.get("/moto/spots/collect?candidate=video-review-candidate")
                assert response.status_code == 200
                html = response.get_data(as_text=True)
                assert "固定点位识别提示" in html
                assert "采用视频识别结果填充表单" in html
                assert "采用视频识别后会覆盖这些内容" in html
                assert "仅新增" in html
                assert "当前值：未填写" in html
                assert "识别后：大连" in html
                assert "视频推断位置：大连 · 辽南" in html
                assert "关键帧与视频诊断" in html
                assert "本地视频：data/raw/douyin_videos/video-review-candidate.mp4" in html
                assert "/moto/spots/collect/videos/video-review-candidate.mp4" in html
                assert "<video controls preload=\"metadata\" class=\"planner-review-video\"" in html
                assert "/moto/spots/collect/keyframes/dy-test/frame-01.jpg" in html
                assert "海边夜骑观景点" in html
                assert "这里是大连滨海路，适合夜骑打卡" in html

                apply_response = client.get("/moto/spots/collect?candidate=video-review-candidate&apply_video_analysis=1")
                apply_html = apply_response.get_data(as_text=True)
                assert apply_response.status_code == 200
                assert "当前表单已采用视频识别结果进行预填。" in apply_html
                assert "覆盖已有值" in apply_html
                assert 'value="dalian"' not in apply_html
                assert 'value="scenic-spot"' in apply_html
                assert 'value="辽南"' in apply_html
                assert 'value="coast"' in apply_html

                keyframe_response = client.get("/moto/spots/collect/keyframes/dy-test/frame-01.jpg")
                assert keyframe_response.status_code == 200
                assert keyframe_response.get_data() == b"fake-jpeg-data"

                video_response = client.get("/moto/spots/collect/videos/video-review-candidate.mp4")
                assert video_response.status_code == 200
                assert video_response.get_data() == b"fake-mp4-data"
        finally:
                candidate_path.write_text(original_candidate, encoding="utf-8")
                if keyframe_path.exists():
                        keyframe_path.unlink()
                if keyframe_dir.exists():
                        keyframe_dir.rmdir()
                if video_path.exists():
                    video_path.unlink()


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


def test_spot_collection_page_can_delete_selected_reviewed_items(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    candidate_path = root / "data" / "normalized" / "candidate_spots.json"
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    rejected_path = root / "data" / "reviewed" / "rejected_spots.json"

    original_candidate = candidate_path.read_text(encoding="utf-8")
    original_approved = approved_path.read_text(encoding="utf-8")
    original_rejected = rejected_path.read_text(encoding="utf-8")

    try:
        candidate_path.write_text("[]\n", encoding="utf-8")
        approved_path.write_text(
            """[
  {"slug": "approved-a", "name": "已批准 A", "city": "大连", "region": "辽南", "route_type": "coast", "summary": "测试点位 A", "photo_focus": ["海景"], "support_role": ["viewpoint"], "sources": [], "reviewed_at": "2026-05-27"},
  {"slug": "approved-b", "name": "已批准 B", "city": "丹东", "region": "辽东", "route_type": "city-riverside", "summary": "测试点位 B", "photo_focus": ["夜景"], "support_role": ["viewpoint"], "sources": [], "reviewed_at": "2026-05-27"}
]\n""",
            encoding="utf-8",
        )
        rejected_path.write_text(
            """[
  {"slug": "rejected-a", "name": "已拒绝 A", "city": "沈阳", "sources": [], "reviewed_at": "2026-05-27"}
]\n""",
            encoding="utf-8",
        )

        spots_before = client.get("/moto/spots")
        assert spots_before.status_code == 200
        assert "已批准 A" in spots_before.get_data(as_text=True)

        detail_before = client.get("/moto/spots/liaoning/approved-a")
        assert detail_before.status_code == 200

        response = client.post(
            "/moto/spots/reviewed/delete",
            data={"reviewed_item_keys": ["approved:0:approved-a", "rejected:0:rejected-a"]},
            follow_redirects=True,
        )

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "已删除 2 条已审批数据。" in html
        assert "已批准 A" not in approved_path.read_text(encoding="utf-8")
        assert "已拒绝 A" not in rejected_path.read_text(encoding="utf-8")
        assert "已批准 B" in approved_path.read_text(encoding="utf-8")

        spots_after = client.get("/moto/spots")
        spots_after_html = spots_after.get_data(as_text=True)
        assert spots_after.status_code == 200
        assert "已批准 A" not in spots_after_html
        assert "已批准 B" in spots_after_html

        detail_after = client.get("/moto/spots/liaoning/approved-a")
        assert detail_after.status_code == 404
    finally:
        candidate_path.write_text(original_candidate, encoding="utf-8")
        approved_path.write_text(original_approved, encoding="utf-8")
        rejected_path.write_text(original_rejected, encoding="utf-8")


def test_spot_collection_page_can_clear_all_review_data(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    candidate_path = root / "data" / "normalized" / "candidate_spots.json"
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    rejected_path = root / "data" / "reviewed" / "rejected_spots.json"

    original_candidate = candidate_path.read_text(encoding="utf-8")
    original_approved = approved_path.read_text(encoding="utf-8")
    original_rejected = rejected_path.read_text(encoding="utf-8")

    try:
        candidate_path.write_text('[{"slug": "candidate-a", "name": "待审核 A"}]\n', encoding="utf-8")
        approved_path.write_text('[{"slug": "approved-a", "name": "已批准 A", "city": "大连", "region": "辽南", "route_type": "coast", "summary": "测试点位 A", "photo_focus": ["海景"], "support_role": ["viewpoint"]}]\n', encoding="utf-8")
        rejected_path.write_text('[{"slug": "rejected-a", "name": "已拒绝 A"}]\n', encoding="utf-8")

        spots_before = client.get("/moto/spots")
        assert spots_before.status_code == 200
        assert "已批准 A" in spots_before.get_data(as_text=True)

        response = client.post("/moto/spots/reviewed/clear", follow_redirects=True)

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "已清空 3 条数据" in html
        assert candidate_path.read_text(encoding="utf-8") == "[]\n"
        assert approved_path.read_text(encoding="utf-8") == "[]\n"
        assert rejected_path.read_text(encoding="utf-8") == "[]\n"

        spots_after = client.get("/moto/spots")
        assert spots_after.status_code == 200
        assert "已批准 A" not in spots_after.get_data(as_text=True)

        detail_after = client.get("/moto/spots/liaoning/approved-a")
        assert detail_after.status_code == 404
    finally:
        candidate_path.write_text(original_candidate, encoding="utf-8")
        approved_path.write_text(original_approved, encoding="utf-8")
        rejected_path.write_text(original_rejected, encoding="utf-8")


def test_spots_index_page_renders_and_filters(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    original_approved = approved_path.read_text(encoding="utf-8")

    try:
        approved_path.write_text(
            """[
  {"slug": "coast-fuel-stop", "name": "大连滨海路", "city": "大连", "region": "辽南", "route_type": "coast", "summary": "滨海测试点位", "photo_focus": ["海边弯道"], "support_role": ["fuel", "viewpoint"]},
  {"slug": "east-view-stop", "name": "丹东沿江停靠点", "city": "丹东", "region": "辽东", "route_type": "city-riverside", "summary": "沿江测试点位", "photo_focus": ["江景"], "support_role": ["viewpoint"]},
  {"slug": "coast-view-stop", "name": "旅顺观景停靠点", "city": "大连旅顺", "region": "辽南", "route_type": "coast-scenic", "summary": "旅顺测试点位", "photo_focus": ["海景"], "support_role": ["viewpoint"]}
]\n""",
            encoding="utf-8",
        )

        response = client.get("/moto/spots?region=辽南&support=fuel")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "辽宁摩旅点位库" in html
        assert "大连滨海路" in html
        assert "适合补油" in html
        assert "丹东沿江停靠点" not in html
        assert "旅顺观景停靠点" not in html
        assert "<strong>3</strong>\n          <span>总点位</span>" in html
        assert "<strong>1</strong>\n          <span>当前展示</span>" in html
        assert "<strong>2</strong>\n          <span>覆盖区域</span>" in html
        assert "当前展示 1 / 3 个点位" in html
        assert "按区域看" in html
        assert "按需求看" in html
        assert "先点常用条件，再决定要不要展开全部筛选" in html
    finally:
        approved_path.write_text(original_approved, encoding="utf-8")


def test_spots_index_page_prefers_collected_images_for_approved_spots(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    original_approved = approved_path.read_text(encoding="utf-8")

    try:
        approved_path.write_text(
            """[
  {
    \"slug\": \"test-collected-image-spot\",
    \"name\": \"测试采集图片点位\",
    \"spot_type\": \"scenic-spot\",
    \"city\": \"大连\",
    \"region\": \"辽南\",
    \"route_type\": \"coast\",
    \"coordinates\": {\"lat\": 38.914, \"lng\": 121.614},
    \"access_level\": \"easy\",
    \"parking_friendly\": true,
    \"best_seasons\": [\"summer\"],
    \"best_time_of_day\": [],
    \"ride_level\": \"beginner\",
    \"recommended_stay\": \"1-2 小时\",
    \"road_features\": [],
    \"risk_notes\": [],
    \"summary\": \"优先展示采集图片。\",
    \"photo_focus\": [\"海边弯道\"],
    \"image_urls\": [\"https://example.com/collected-cover.jpg\", \"https://example.com/collected-route.jpg\"],
    \"image_key\": \"candidate-test-collected-image-spot\",
    \"route_tags\": [\"辽南\"],
    \"nearby_spot_slugs\": [],
    \"fuel_support\": \"nearby\",
    \"repair_support\": \"unknown\",
    \"lodging_support\": \"unknown\",
    \"food_support\": \"unknown\",
    \"support_role\": [\"viewpoint\"],
    \"moto_station_features\": [],
    \"confidence_score\": \"B\",
    \"sources\": [],
    \"last_verified_at\": \"\"
  }
]\n""",
            encoding="utf-8",
        )

        response = client.get("/moto/spots?region=辽南")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "测试采集图片点位" in html
        assert "打卡点" in html
        assert "咖啡站" in html
        assert "https://example.com/collected-cover.jpg" in html
        assert "/moto/spots/liaoning/test-collected-image-spot/images/cover.svg" not in html
    finally:
        approved_path.write_text(original_approved, encoding="utf-8")


def test_spots_index_page_shows_video_brief_for_approved_spots(client):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        approved_path = root / "data" / "reviewed" / "approved_spots.json"
        original_approved = approved_path.read_text(encoding="utf-8")

        try:
                approved_path.write_text(
                        """[
    {
        "slug": "video-brief-spot",
        "name": "视频简报点位",
        "city": "大连",
        "region": "辽南",
        "route_type": "coast",
        "summary": "点位摘要",
        "photo_focus": ["海景"],
        "support_role": ["viewpoint"],
        "video_url": "https://example.com/video.mp4",
        "keyframe_paths": ["data/raw/openclaw_keyframes/video-brief/frame-01.jpg", "data/raw/openclaw_keyframes/video-brief/frame-02.jpg"],
        "video_analysis": {
            "summary": "海边落日观景位"
        },
        "fixed_spot_info": {
            "poiType": "scenic-spot",
            "routeType": "coast"
        }
    }
]\n""",
                        encoding="utf-8",
                )

                response = client.get("/moto/spots")

                assert response.status_code == 200
                html = response.get_data(as_text=True)
                assert "视频简报点位" in html
                assert "视频采集" in html
                assert "关键帧 2 张" in html
                assert "风景打卡点" in html
                assert "海岸公路" in html
                assert "海边落日观景位" in html
                assert "点开可看图片、来源和适合接入的路线模板。" in html
        finally:
                approved_path.write_text(original_approved, encoding="utf-8")


def test_spot_image_gallery_renders_from_structured_data(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    approved_path = root / "data" / "reviewed" / "approved_spots.json"
    original_approved = approved_path.read_text(encoding="utf-8")

    try:
        approved_path.write_text(
            '[{"slug": "dalian-binhai-road", "name": "大连滨海路", "city": "大连", "region": "辽南", "route_type": "coast", "summary": "测试滨海路", "photo_focus": ["海边弯道"], "support_role": ["fuel", "viewpoint"], "image_key": "liaoning-binhai-cover"}]\n',
            encoding="utf-8",
        )

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
    finally:
        approved_path.write_text(original_approved, encoding="utf-8")


def test_approved_spot_detail_shows_video_analysis_and_keyframes(client):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        approved_path = root / "data" / "reviewed" / "approved_spots.json"
        original_approved = approved_path.read_text(encoding="utf-8")
        keyframe_dir = root / "data" / "raw" / "openclaw_keyframes" / "detail-test"
        keyframe_path = keyframe_dir / "frame-01.jpg"
        keyframe_dir.mkdir(parents=True, exist_ok=True)
        keyframe_path.write_bytes(b"detail-fake-jpeg")

        try:
                approved_path.write_text(
                        """[
    {
        "slug": "detail-video-spot",
        "name": "详情视频点位",
        "city": "大连",
        "region": "辽南",
        "route_type": "coast",
        "summary": "详情测试点位",
        "photo_focus": ["海景"],
        "support_role": ["viewpoint"],
        "video_url": "https://example.com/detail-video.mp4",
        "keyframe_paths": ["data/raw/openclaw_keyframes/detail-test/frame-01.jpg"],
        "video_analysis": {
            "summary": "海边视频摘要",
            "transcript": "视频转写内容",
            "ocrText": "大连 滨海",
            "placeHints": ["大连"],
            "routeHints": ["coast"],
            "sceneLabels": ["海景"]
        },
        "fixed_spot_info": {
            "city": "大连",
            "region": "辽南",
            "poiType": "scenic-spot",
            "routeType": "coast",
            "supportTags": ["viewpoint"],
            "spotMarkers": ["checkin-point"],
            "summary": "固定点位摘要"
        },
        "sources": []
    }
]\n""",
                        encoding="utf-8",
                )

                detail_response = client.get("/moto/spots/liaoning/detail-video-spot")
                detail_html = detail_response.get_data(as_text=True)
                assert detail_response.status_code == 200
                assert "视频采集诊断" in detail_html
                assert "视频分析与关键帧" in detail_html
                assert "https://example.com/detail-video.mp4" in detail_html
                assert "/moto/spots/collect/keyframes/detail-test/frame-01.jpg" in detail_html
                assert "固定点位摘要" in detail_html
                assert "视频转写内容" in detail_html
                assert "场景标签：海景" in detail_html
        finally:
                approved_path.write_text(original_approved, encoding="utf-8")
                if keyframe_path.exists():
                        keyframe_path.unlink()
                if keyframe_dir.exists():
                        keyframe_dir.rmdir()


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


def test_local_collector_monitor_page_renders_status_summary(client, tmp_path, monkeypatch):
        from app.services import collector_monitor

        status_path = tmp_path / "local_collection_status.json"
        output_path = tmp_path / "openclaw_export.json"
        status_path.write_text(
                """{
    "state": "success",
    "run_mode": "manual",
    "current_stage": "idle",
    "pipeline_status": "success",
    "health": "ok",
    "last_heartbeat": "2026-05-28T09:00:00+00:00",
    "last_success_at": "2026-05-28T09:00:00+00:00",
    "last_pipeline_at": "2026-05-28T09:00:05+00:00",
    "items_collected": 12,
    "cycle_count": 2,
    "current_task_index": 108,
    "tasks_completed": 108,
    "tasks_total": 108,
    "pending_candidates_processed": 12,
    "pending_candidates_added": 5,
    "pending_candidates_updated": 2,
    "pending_candidates_total": 31,
    "last_duration_seconds": 14.2,
    "pipeline_summary": "adapted openclaw export -> normalized raw candidates",
    "recent_cycles": [
        {"cycle": 2, "finished_at": "2026-05-28T09:00:00+00:00", "state": "success", "items_collected": 12, "tasks_completed": 108, "tasks_total": 108, "duration_seconds": 14.2, "pipeline_status": "success", "pending_candidates_added": 5, "pending_candidates_updated": 2, "pending_candidates_total": 31},
        {"cycle": 1, "finished_at": "2026-05-28T08:54:00+00:00", "state": "success", "items_collected": 8, "tasks_completed": 108, "tasks_total": 108, "duration_seconds": 12.1, "pipeline_status": "success", "pending_candidates_added": 3, "pending_candidates_updated": 1, "pending_candidates_total": 26}
    ],
    "events": [
        {"at": "2026-05-28T09:00:00+00:00", "level": "info", "message": "本地采集完成，共输出 12 条候选数据。"}
    ]
}
""",
                encoding="utf-8",
        )
        output_path.write_text(
                """{
    "source": "local-collector",
    "exported_at": "2026-05-28T09:00:00+00:00",
    "items": [{"name": "测试点位 1"}, {"name": "测试点位 2"}]
}
""",
                encoding="utf-8",
        )

        monkeypatch.setattr(collector_monitor, "COLLECTOR_STATUS_PATH", status_path)
        monkeypatch.setattr(collector_monitor, "COLLECTOR_OUTPUT_PATH", output_path)

        response = client.get("/moto/collector/monitor")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "本地采集监控" in html
        assert "最近一次成功" in html
        assert "手动常驻" in html
        assert "已完成" in html
        assert "adapted openclaw export -&gt; normalized raw candidates" in html
        assert "待审批增量：新增 5 · 更新 2 · 队列总量 31" in html
        assert "点击启动后会持续采集，直到你手动点“停止采集”。" in html
        assert "新增待审批" in html
        assert "上一轮 3 · 最近 3 轮累计 8" in html
        assert "队列总量" in html
        assert "本轮重复跳过" in html
        assert "历史已下载跳过" in html
        assert "下载失败" in html
        assert "最近几轮采集结果" in html
        assert "第 2 轮" in html
        assert "本地采集完成，共输出 12 条候选数据。" in html
        assert "108 / 108" in html


def test_local_collector_monitor_api_returns_status_payload(client, tmp_path, monkeypatch):
        from app.services import collector_monitor

        status_path = tmp_path / "local_collection_status.json"
        output_path = tmp_path / "openclaw_export.json"
        status_path.write_text(
                """{
    "state": "running",
    "run_mode": "manual",
    "current_stage": "collecting",
    "pipeline_status": "success",
    "last_heartbeat": "2026-05-28T09:05:00+00:00",
    "last_pipeline_at": "2026-05-28T09:04:58+00:00",
    "items_collected": 4,
    "cycle_count": 3,
    "current_task_index": 108,
    "tasks_completed": 21,
    "tasks_total": 108,
    "current_task": "准备继续采集下一轮",
    "pending_candidates_processed": 4,
    "pending_candidates_added": 1,
    "pending_candidates_updated": 3,
    "pending_candidates_total": 28,
    "pipeline_summary": "adapted openclaw export -> normalized raw candidates",
    "recent_cycles": [
        {"cycle": 3, "finished_at": "2026-05-28T09:04:58+00:00", "state": "success", "items_collected": 4, "tasks_completed": 108, "tasks_total": 108, "duration_seconds": 18.6, "pipeline_status": "success", "pending_candidates_added": 1, "pending_candidates_updated": 3, "pending_candidates_total": 28},
        {"cycle": 2, "finished_at": "2026-05-28T08:59:58+00:00", "state": "success", "items_collected": 6, "tasks_completed": 108, "tasks_total": 108, "duration_seconds": 16.3, "pipeline_status": "success", "pending_candidates_added": 2, "pending_candidates_updated": 1, "pending_candidates_total": 27}
    ],
    "events": [
        {"at": "2026-05-28T09:05:00+00:00", "level": "info", "message": "上一轮采集完成，继续执行下一轮。"}
    ]
}
""",
                encoding="utf-8",
        )
        output_path.write_text(
                """{
    "source": "local-collector",
    "exported_at": "2026-05-28T09:00:00+00:00",
    "items": [{"name": "测试点位"}]
}
""",
                encoding="utf-8",
        )

        monkeypatch.setattr(collector_monitor, "COLLECTOR_STATUS_PATH", status_path)
        monkeypatch.setattr(collector_monitor, "COLLECTOR_OUTPUT_PATH", output_path)

        response = client.get("/api/collector-monitor")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["page"]["title"] == "本地采集监控"
        assert payload["monitor"]["health"]["label"] in {"采集中", "正常"}
        assert payload["monitor"]["run_mode_label"] == "手动常驻"
        assert payload["monitor"]["current_stage_label"] == "正在采集"
        assert payload["monitor"]["pipeline_status_label"] == "已完成"
        assert payload["monitor"]["current_task"] == "准备继续采集下一轮"
        assert payload["monitor"]["metrics"][2]["value"] == "1"
        assert payload["monitor"]["recent_cycles"][0]["cycle"] == "3"
        assert payload["monitor"]["pending_queue_delta"]["added"] == "1"
        assert payload["monitor"]["recent_cycles"][0]["pending_delta"] == "新增 1 · 更新 3 · 队列总量 28"
        assert payload["monitor"]["pending_trend_cards"][0]["value"] == "1"
        assert payload["monitor"]["pending_trend_cards"][0]["hint"] == "上一轮 2 · 最近 3 轮累计 3"
        assert payload["monitor"]["pending_trend_cards"][3]["label"] == "本轮重复跳过"
        assert payload["monitor"]["pending_trend_cards"][4]["label"] == "历史已下载跳过"
        assert payload["monitor"]["pending_trend_cards"][5]["label"] == "下载失败"


    def test_local_collector_monitor_start_and_stop_routes_return_feedback(client, monkeypatch):
        from app.blueprints.pages import moto as moto_pages

        monkeypatch.setattr(moto_pages, "start_local_collector", lambda: {"pid": 12345})
        monkeypatch.setattr(moto_pages, "stop_local_collector", lambda: {"pid": 12345})

        start_response = client.post(
            "/moto/collector/monitor/start",
            follow_redirects=False,
        )
        assert start_response.status_code == 302
        assert "monitor_message=" in start_response.headers["Location"]
        assert "12345" in start_response.headers["Location"]
        assert "%E6%89%8B%E5%8A%A8%E5%81%9C%E6%AD%A2" in start_response.headers["Location"]

        stop_response = client.post("/moto/collector/monitor/stop", follow_redirects=False)
        assert stop_response.status_code == 302
        assert "monitor_message=" in stop_response.headers["Location"]
        assert "12345" in stop_response.headers["Location"]


    def test_local_collector_run_once_syncs_items_into_pending_queue_when_pipeline_skipped(tmp_path):
        import json
        from scripts import run_local_social_collection as collector

        source_path = tmp_path / "source.json"
        output_path = tmp_path / "openclaw_export.json"
        raw_candidates_path = tmp_path / "local_collector_candidates.json"
        status_path = tmp_path / "local_collection_status.json"
        pending_queue_path = tmp_path / "candidate_spots.json"

        source_path.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "platform": "xiaohongshu",
                            "title": "大连滨海观景停靠点",
                            "summary": "海边实拍，适合机车打卡和补油。",
                            "url": "https://www.xiaohongshu.com/explore/spot-a",
                            "author": "辽南骑士",
                            "city": "大连",
                            "region": "辽南",
                            "routeType": "coast",
                            "supportTags": ["fuel", "viewpoint"],
                            "spotMarkers": ["checkin-point"],
                            "imageUrls": ["https://example.com/spot-a.jpg"],
                            "comments": [{"text": "就在大连滨海路边上"}],
                        }
                    ]
                },
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )

        original_queue_path = collector.CANDIDATE_QUEUE_PATH
        collector.CANDIDATE_QUEUE_PATH = pending_queue_path
        try:
            payload = collector.run_once(
                [source_path],
                output_path,
                raw_candidates_path,
                status_path,
                max_items=5,
                cycle_index=1,
                run_pipeline=False,
            )

            queue = json.loads(pending_queue_path.read_text(encoding="utf-8"))
            raw_candidates = json.loads(raw_candidates_path.read_text(encoding="utf-8"))

            assert len(payload["items"]) == 1
            assert len(raw_candidates) == 1
            assert len(queue) == 1
            assert queue[0]["name"] == "大连滨海观景停靠点"
            assert queue[0]["city"] == "大连"
            assert queue[0]["region"] == "辽南"
            assert queue[0]["route_type"] == "coast"
        finally:
            collector.CANDIDATE_QUEUE_PATH = original_queue_path


def test_local_collector_parses_public_search_rss_and_page_meta():
                from scripts import run_local_social_collection as collector

                rss = """<?xml version='1.0' encoding='utf-8'?>
<rss version='2.0'>
    <channel>
        <item>
            <title>大连滨海路摩旅实拍</title>
            <link>https://www.xiaohongshu.com/explore/test-note</link>
            <description>辽宁摩旅观景与补给记录</description>
        </item>
    </channel>
</rss>
"""
                results = collector.parse_search_rss_items(rss)
                assert results[0]["link"] == "https://www.xiaohongshu.com/explore/test-note"

                html = """
<html>
    <head>
        <title>大连滨海路摩旅实拍</title>
        <meta property="og:title" content="大连滨海路摩旅实拍" />
        <meta property="og:description" content="大连滨海路适合机车观景和补油。" />
        <meta property="og:image" content="https://ci.xiaohongshu.com/test-cover.jpg" />
        <meta name="keywords" content="辽宁摩旅,大连,滨海路" />
    </head>
</html>
"""
                item = collector.build_live_item_from_page(
                        {"platform": "xiaohongshu", "keyword": "辽宁 摩旅", "limit": 5},
                        results[0],
                        html,
                )
                assert item is not None
                assert item["city"] == "大连"
                assert item["region"] == "辽南"
                assert "https://ci.xiaohongshu.com/test-cover.jpg" in item["imageUrls"]


        def test_local_collector_rejects_profile_urls_and_keeps_detail_pages():
                from scripts import run_local_social_collection as collector

                assert collector.is_supported_search_result_url(
                    "xiaohongshu",
                    "https://www.xiaohongshu.com/explore/test-note",
                ) is True
                assert collector.is_supported_search_result_url(
                    "xiaohongshu",
                    "https://www.xiaohongshu.com/user/profile/123456",
                ) is False
                assert collector.is_supported_search_result_url(
                    "douyin",
                    "https://www.douyin.com/video/7480000000000000000",
                ) is True
                assert collector.is_supported_search_result_url(
                    "douyin",
                    "https://www.douyin.com/user/MS4wLjABAAAA",
                ) is False


        def test_deepseek_enrichment_merges_structured_fields_without_overwriting_richer_text():
                from scripts.deepseek_candidate_enrichment import merge_item_enrichment

                item = {
                    "platform": "douyin",
                    "name": "大连滨海夜骑停靠点",
                    "videoAnalysis": {
                        "summary": "原始摘要更详细一些",
                        "ocrText": "滨海路 停车",
                        "placeHints": ["大连"],
                    },
                    "fixedSpotInfo": {
                        "city": "",
                        "region": "",
                        "poiType": "",
                        "routeType": "",
                        "supportTags": [],
                        "spotMarkers": [],
                        "photoTags": [],
                        "summary": "",
                    },
                }
                enrichment = {
                    "poiType": "scenic-spot",
                    "routeType": "coast",
                    "supportTags": ["viewpoint", "food"],
                    "spotMarkers": ["checkin-point", "coffee-stop"],
                    "photoTags": ["夜景", "海岸线"],
                    "confidenceScore": "B",
                    "fixedSpotInfo": {
                        "city": "大连",
                        "region": "辽南",
                        "poiType": "scenic-spot",
                        "routeType": "coast",
                        "supportTags": ["viewpoint", "food"],
                        "spotMarkers": ["checkin-point", "coffee-stop"],
                        "photoTags": ["夜景", "海岸线"],
                        "summary": "适合夜骑打卡和咖啡停靠。",
                    },
                    "videoAnalysis": {
                        "summary": "较短摘要",
                        "sceneSummary": "海边夜景道路，适合机车停靠拍照。",
                        "routeHints": ["coast"],
                        "supportHints": ["viewpoint", "food"],
                    },
                }

                merged = merge_item_enrichment(item, enrichment)

                assert merged["routeType"] == "coast"
                assert merged["poiType"] == "scenic-spot"
                assert merged["confidenceScore"] == "B"
                assert merged["fixedSpotInfo"]["city"] == "大连"
                assert merged["fixedSpotInfo"]["region"] == "辽南"
                assert merged["fixedSpotInfo"]["supportTags"] == ["viewpoint", "food"]
                assert merged["videoAnalysis"]["summary"] == "原始摘要更详细一些"
                assert merged["videoAnalysis"]["sceneSummary"] == "海边夜景道路，适合机车停靠拍照。"


def test_collect_douyin_videos_extracts_direct_video_candidates_from_payload():
                                from scripts.collect_douyin_videos import extract_video_candidates_from_payload
                                from scripts.collect_douyin_videos import resolve_douyin_video_url

                                payload = r'''
<html>
    <head>
        <meta property="og:video" content="https://www.iesdouyin.com/aweme/v1/play/?video_id=123" />
    </head>
    <body>
        <script>
            window.__DATA__ = {"downloadAddr":"https:\/\/www.iesdouyin.com\/aweme\/v1\/playwm\/?video_id=abc"};
        </script>
    </body>
</html>
'''

                                candidates = extract_video_candidates_from_payload(payload, "https://www.douyin.com/video/123")
                                assert "https://www.iesdouyin.com/aweme/v1/playwm/?video_id=abc" in candidates

                                resolved = resolve_douyin_video_url(
                                                "https://www.douyin.com/video/123",
                                                payload,
                                                {"og:video": "https://www.iesdouyin.com/aweme/v1/play/?video_id=123"},
                                )
                                assert resolved == "https://www.iesdouyin.com/aweme/v1/play/?video_id=123"


def test_collect_douyin_videos_identifies_downloadable_candidates():
                                from scripts.collect_douyin_videos import is_douyin_candidate

                                assert is_douyin_candidate(
                                                {"platform": "douyin", "sourceUrl": "https://www.douyin.com/video/7480000000000000000"}
                                ) is True
                                assert is_douyin_candidate(
                                                {"platform": "douyin", "sourceUrl": "https://www.douyin.com/user/MS4wLjABAAAA"}
                                ) is False
                                assert is_douyin_candidate(
                                                {"platform": "douyin", "videoUrl": "https://www.iesdouyin.com/aweme/v1/play/?video_id=123"}
                                ) is True


def test_collect_douyin_videos_builds_raw_candidates_for_downloaded_items_only():
                                from scripts.collect_douyin_videos import build_raw_candidates

                                raw_candidates = build_raw_candidates(
                                                [
                                                                {
                                                                                "name": "大连滨海夜骑停靠点",
                                                                                "sourceUrl": "https://www.douyin.com/video/7480000000000000000",
                                                                                "videoUrl": "https://www.iesdouyin.com/aweme/v1/play/?video_id=123",
                                                                                "owner": "辽南骑士",
                                                                                "excerpt": "海边夜骑打卡。",
                                                                                "keywords": ["大连", "滨海路"],
                                                                                "imageUrls": ["https://example.com/cover.jpg"],
                                                                                "capturedAt": "2026-05-28T00:00:00+00:00",
                                                                                "downloadStatus": "downloaded",
                                                                                "localVideoPath": "data/raw/douyin_videos/dalian.mp4",
                                                                },
                                                                {
                                                                                "name": "未下载条目",
                                                                                "sourceUrl": "https://www.douyin.com/video/7480000000000000001",
                                                                                "downloadStatus": "missing-video-url",
                                                                },
                                                ]
                                )

                                assert len(raw_candidates) == 1
                                assert raw_candidates[0]["source_item_url"] == "https://www.douyin.com/video/7480000000000000000"
                                assert raw_candidates[0]["video_url"] == "https://www.iesdouyin.com/aweme/v1/play/?video_id=123"
                                assert raw_candidates[0]["local_video_path"] == "data/raw/douyin_videos/dalian.mp4"


def test_collect_douyin_videos_can_sync_downloaded_items_into_pending_queue(tmp_path):
                                import scripts.collect_douyin_videos as collector
                                import scripts.run_local_social_collection as local_collector

                                pending_queue_path = tmp_path / "candidate_spots.json"
                                original_queue_path = local_collector.CANDIDATE_QUEUE_PATH
                                local_collector.CANDIDATE_QUEUE_PATH = pending_queue_path
                                try:
                                                raw_candidates = collector.build_raw_candidates(
                                                                [
                                                                                {
                                                                                                "name": "大连滨海夜骑停靠点",
                                                                                                "sourceUrl": "https://www.douyin.com/video/7480000000000000000",
                                                                                                "videoUrl": "https://www.iesdouyin.com/aweme/v1/play/?video_id=123",
                                                                                                "owner": "辽南骑士",
                                                                                                "excerpt": "海边夜骑打卡。",
                                                                                                "keywords": ["大连", "滨海路"],
                                                                                                "imageUrls": ["https://example.com/cover.jpg"],
                                                                                                "capturedAt": "2026-05-28T00:00:00+00:00",
                                                                                                "downloadStatus": "downloaded",
                                                                                                "localVideoPath": "data/raw/douyin_videos/dalian.mp4",
                                                                                }
                                                                ]
                                                )
                                                queue_sync = local_collector.sync_pending_candidate_queue(raw_candidates)
                                                queue = json.loads(pending_queue_path.read_text(encoding="utf-8"))

                                                assert queue_sync["processed"] == 1
                                                assert queue_sync["added"] == 1
                                                assert queue[0]["name"] == "大连滨海夜骑停靠点"
                                                assert queue[0]["video_url"] == "https://www.iesdouyin.com/aweme/v1/play/?video_id=123"
                                                assert queue[0]["local_video_path"] == "data/raw/douyin_videos/dalian.mp4"
                                finally:
                                                local_collector.CANDIDATE_QUEUE_PATH = original_queue_path


def test_collect_douyin_videos_skips_duplicates_in_run_and_history():
                                from scripts.collect_douyin_videos import dedupe_manifest_items

                                items = [
                                                {
                                                                "dedupeKey": "https://www.douyin.com/video/a",
                                                                "sourceUrl": "https://www.douyin.com/video/a",
                                                                "videoUrl": "https://www.iesdouyin.com/aweme/v1/play/?video_id=a",
                                                                "downloadStatus": "pending",
                                                },
                                                {
                                                                "dedupeKey": "https://www.douyin.com/video/a",
                                                                "sourceUrl": "https://www.douyin.com/video/a",
                                                                "videoUrl": "https://www.iesdouyin.com/aweme/v1/play/?video_id=a",
                                                                "downloadStatus": "pending",
                                                },
                                                {
                                                                "dedupeKey": "https://www.douyin.com/video/b",
                                                                "sourceUrl": "https://www.douyin.com/video/b",
                                                                "videoUrl": "https://www.iesdouyin.com/aweme/v1/play/?video_id=b",
                                                                "downloadStatus": "pending",
                                                },
                                ]
                                registry = {
                                                "downloaded": [
                                                                {
                                                                                "dedupe_key": "https://www.douyin.com/video/b",
                                                                                "sourceUrl": "https://www.douyin.com/video/b",
                                                                                "videoUrl": "https://www.iesdouyin.com/aweme/v1/play/?video_id=b",
                                                                }
                                                ]
                                }

                                result, stats = dedupe_manifest_items(items, registry)

                                assert result[0]["downloadStatus"] == "pending"
                                assert result[1]["downloadStatus"] == "skipped-duplicate"
                                assert result[2]["downloadStatus"] == "skipped-downloaded-history"
                                assert stats == {
                                                "duplicates_in_run": 1,
                                                "already_downloaded": 1,
                                                "eligible": 1,
                                }


def test_collect_douyin_videos_builds_failure_event_messages_by_reason():
                                from scripts.collect_douyin_videos import build_failure_event_messages

                                messages = build_failure_event_messages(
                                                [
                                                                {
                                                                                "name": "解析失败视频",
                                                                                "sourceUrl": "https://www.douyin.com/video/a",
                                                                                "downloadStatus": "missing-video-url",
                                                                                "downloadError": "",
                                                                },
                                                                {
                                                                                "name": "网络失败视频",
                                                                                "sourceUrl": "https://www.douyin.com/video/b",
                                                                                "downloadStatus": "download-error",
                                                                                "downloadError": "timed out",
                                                                },
                                                                {
                                                                                "name": "写文件失败视频",
                                                                                "sourceUrl": "https://www.douyin.com/video/c",
                                                                                "downloadStatus": "download-error",
                                                                                "downloadError": "Permission denied",
                                                                },
                                                ]
                                )

                                assert len(messages) == 3
                                assert "解析不到视频地址 1 条" in messages[0]["message"]
                                assert "网络失败 1 条" in messages[1]["message"]
                                assert "写文件失败 1 条" in messages[2]["message"]


def test_collector_monitor_context_reads_dynamic_douyin_metrics(tmp_path):
                                import app.services.collector_monitor as monitor

                                original_status_path = monitor.COLLECTOR_STATUS_PATH
                                original_output_path = monitor.COLLECTOR_OUTPUT_PATH

                                status_path = tmp_path / "local_collection_status.json"
                                output_path = tmp_path / "douyin_video_manifest.json"
                                status_path.write_text(
                                                json.dumps(
                                                                {
                                                                                "collector_name": "douyin-python-video-collector",
                                                                                "state": "success",
                                                                                "run_mode": "once",
                                                                                "current_stage": "idle",
                                                                                "pipeline_status": "skipped",
                                                                                "script_command": ".venv/bin/python scripts/collect_douyin_videos.py --download-limit 5",
                                                                                "output_path": str(output_path),
                                                                                "log_path": str(tmp_path / "douyin_collection.log"),
                                                                                "expected_run_interval_minutes": 10,
                                                                                "download_limit": 5,
                                                                                "duplicate_candidates_in_run": 2,
                                                                                "skipped_already_downloaded": 3,
                                                                                "skipped_download_limit": 1,
                                                                                "pending_candidates_added": 4,
                                                                                "pending_candidates_updated": 1,
                                                                                "pending_candidates_total": 12,
                                                                                "recent_cycles": [
                                                                                                {
                                                                                                                "cycle": 1,
                                                                                                                "finished_at": "2026-05-28T00:00:00+00:00",
                                                                                                                "state": "success",
                                                                                                                "items_collected": 5,
                                                                                                                "tasks_completed": 8,
                                                                                                                "tasks_total": 8,
                                                                                                                "duration_seconds": 12.5,
                                                                                                                "pipeline_status": "skipped",
                                                                                                                "pending_candidates_added": 4,
                                                                                                                "pending_candidates_updated": 1,
                                                                                                                "pending_candidates_total": 12,
                                                                                                                "duplicate_candidates_in_run": 2,
                                                                                                                "skipped_already_downloaded": 3,
                                                                                                                "download_errors": 1,
                                                                                                }
                                                                                ],
                                                                                "events": [
                                                                                                {
                                                                                                                "at": "2026-05-28T00:00:01+00:00",
                                                                                                                "level": "warning",
                                                                                                                "message": "失败摘要：网络失败 1 条。样例：网络失败视频 · timed out",
                                                                                                }
                                                                                ],
                                                                },
                                                                ensure_ascii=False,
                                                ) + "\n",
                                                encoding="utf-8",
                                )
                                output_path.write_text(json.dumps({"items": [1, 2, 3]}, ensure_ascii=False) + "\n", encoding="utf-8")

                                monitor.COLLECTOR_STATUS_PATH = status_path
                                monitor.COLLECTOR_OUTPUT_PATH = output_path
                                try:
                                                context = monitor.get_collection_monitor_context()
                                                metrics = {item["label"]: item["value"] for item in context["monitor"]["metrics"]}
                                                summary = {item["label"]: item["value"] for item in context["monitor"]["summary"]}

                                                assert context["monitor"]["script_command"] == ".venv/bin/python scripts/collect_douyin_videos.py --download-limit 5"
                                                assert metrics["单轮下载上限"] == "5"
                                                assert metrics["本轮去重跳过"] == "2"
                                                assert metrics["历史已下载跳过"] == "3"
                                                assert "每 10 分钟运行一次" in summary["运行计划"]
                                                assert "本轮重复 2" in summary["去重结果"]
                                                assert "历史已下载 3" in context["monitor"]["recent_cycles"][0]["pending_delta"]
                                                assert context["monitor"]["pending_trend_cards"][3]["value"] == "2"
                                                assert context["monitor"]["pending_trend_cards"][4]["value"] == "3"
                                                assert context["monitor"]["events"][0]["message"] == "失败摘要：网络失败 1 条。样例：网络失败视频 · timed out"
                                finally:
                                                monitor.COLLECTOR_STATUS_PATH = original_status_path
                                                monitor.COLLECTOR_OUTPUT_PATH = original_output_path