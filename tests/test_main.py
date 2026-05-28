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


            "spot_markers": ["checkin-point", "coffee-stop"],
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
        original_candidate = candidate_path.read_text(encoding="utf-8")

        keyframe_dir.mkdir(parents=True, exist_ok=True)
        keyframe_path.write_bytes(b"fake-jpeg-data")

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
        finally:
                candidate_path.write_text(original_candidate, encoding="utf-8")
                if keyframe_path.exists():
                        keyframe_path.unlink()
                if keyframe_dir.exists():
                        keyframe_dir.rmdir()


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
    "run_mode": "loop",
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
        assert "循环常驻" in html
        assert "已完成" in html
        assert "adapted openclaw export -&gt; normalized raw candidates" in html
        assert "待审批增量：新增 5 · 更新 2 · 队列总量 31" in html
        assert "新增待审批" in html
        assert "上一轮 3 · 最近 3 轮累计 8" in html
        assert "队列总量" in html
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
    "state": "sleeping",
    "run_mode": "loop",
    "current_stage": "sleeping",
    "pipeline_status": "success",
    "last_heartbeat": "2026-05-28T09:05:00+00:00",
    "last_pipeline_at": "2026-05-28T09:04:58+00:00",
    "items_collected": 4,
    "cycle_count": 3,
    "current_task_index": 108,
    "tasks_completed": 21,
    "tasks_total": 108,
    "current_task": "等待下一轮采集",
    "next_run_at": "2099-05-28T09:10:00+00:00",
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
        {"at": "2026-05-28T09:05:00+00:00", "level": "info", "message": "等待 300 秒后开始下一轮采集。"}
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
        assert payload["monitor"]["health"]["label"] == "等待下一轮"
        assert payload["monitor"]["run_mode_label"] == "循环常驻"
        assert payload["monitor"]["current_stage_label"] == "等待下一轮"
        assert payload["monitor"]["pipeline_status_label"] == "已完成"
        assert payload["monitor"]["current_task"] == "等待下一轮采集"
        assert payload["monitor"]["metrics"][2]["value"] == "1"
        assert payload["monitor"]["recent_cycles"][0]["cycle"] == "3"
        assert payload["monitor"]["pending_queue_delta"]["added"] == "1"
        assert payload["monitor"]["recent_cycles"][0]["pending_delta"] == "新增 1 · 更新 3 · 队列总量 28"
        assert payload["monitor"]["pending_trend_cards"][0]["value"] == "1"
        assert payload["monitor"]["pending_trend_cards"][0]["hint"] == "上一轮 2 · 最近 3 轮累计 3"


    def test_local_collector_monitor_start_and_stop_routes_return_feedback(client, monkeypatch):
        from app.blueprints.pages import moto as moto_pages

        monkeypatch.setattr(moto_pages, "start_local_collector", lambda interval_seconds: {"pid": 12345, "interval_seconds": interval_seconds})
        monkeypatch.setattr(moto_pages, "stop_local_collector", lambda: {"pid": 12345})

        start_response = client.post(
            "/moto/collector/monitor/start",
            data={"interval_seconds": "600"},
            follow_redirects=False,
        )
        assert start_response.status_code == 302
        assert "monitor_message=" in start_response.headers["Location"]
        assert "12345" in start_response.headers["Location"]

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