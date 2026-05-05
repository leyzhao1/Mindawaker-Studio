from __future__ import annotations

from pathlib import Path

from media_service.model.schemas import BatchSearchRequest, QueryIntent, RetrievalResult, ScoreBreakdown, SearchRequest
from media_service.retrieval.coarse_filter import filter_candidates_semantic
from media_service.retrieval.query_builder import QueryState
from media_service.service.retrieval_service import RetrievalService
from media_service.windowing.schema import (
    VideoWindowAnnotation,
    VideoWindowIndex,
    WindowBuildConfig,
    WindowFeatures,
    WindowKey,
    WindowSemanticTag,
)


class StubIndexService:
    def get_index(self, annotation_root: Path):
        return []


def _build_window_index(tmp_path: Path) -> VideoWindowIndex:
    source_path = str((tmp_path / "videos" / "clip.mp4").resolve())
    window = VideoWindowAnnotation(
        window_id="window-a",
        source_path=source_path,
        relative_path="videos/clip.mp4",
        level=5.0,
        window_size_sec=5.0,
        stride_sec=2.5,
        start_sec=0.0,
        end_sec=5.0,
        duration_sec=5.0,
        sample_count=5,
        sample_fps=1.0,
        features=WindowFeatures(
            brightness_mean=55.0,
            saturation_mean=45.0,
            motion_mean=30.0,
            readability_score=78.0,
        ),
        semantic=WindowSemanticTag(
            caption="calm city transition",
            objects=["city"],
            scene_tags=["transition"],
            action_tags=["walk"],
        ),
    )
    return VideoWindowIndex(
        source_path=source_path,
        relative_path="videos/clip.mp4",
        file_name="clip.mp4",
        duration_sec=10.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[5.0]),
        windows=[window],
    )


def _build_multi_level_window_index(tmp_path: Path) -> VideoWindowIndex:
    source_path = str((tmp_path / "videos" / "multi.mp4").resolve())
    coarse_window = VideoWindowAnnotation(
        window_id="coarse-10",
        source_path=source_path,
        relative_path="videos/multi.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        sample_count=10,
        sample_fps=1.0,
        features=WindowFeatures(
            brightness_mean=62.0,
            saturation_mean=35.0,
            motion_mean=20.0,
            readability_score=80.0,
        ),
        semantic=WindowSemanticTag(
            caption="calm city transition",
            objects=["city"],
            scene_tags=["street"],
            action_tags=["walk"],
        ),
    )
    fine_hit = VideoWindowAnnotation(
        window_id="fine-2-hit",
        source_path=source_path,
        relative_path="videos/multi.mp4",
        level=2.0,
        window_size_sec=2.0,
        stride_sec=1.0,
        start_sec=4.0,
        end_sec=6.0,
        duration_sec=2.0,
        sample_count=2,
        sample_fps=1.0,
        features=WindowFeatures(
            brightness_mean=60.0,
            saturation_mean=34.0,
            motion_mean=20.0,
            readability_score=82.0,
        ),
        semantic=WindowSemanticTag(
            caption="window detail",
            objects=["road"],
            scene_tags=["urban"],
            action_tags=["walking"],
        ),
    )
    fine_miss = VideoWindowAnnotation(
        window_id="fine-2-miss",
        source_path=source_path,
        relative_path="videos/multi.mp4",
        level=2.0,
        window_size_sec=2.0,
        stride_sec=1.0,
        start_sec=12.0,
        end_sec=14.0,
        duration_sec=2.0,
        sample_count=2,
        sample_fps=1.0,
        features=WindowFeatures(
            brightness_mean=20.0,
            saturation_mean=80.0,
            motion_mean=70.0,
            readability_score=30.0,
        ),
        semantic=WindowSemanticTag(
            caption="indoor office",
            objects=["computer"],
            scene_tags=["room"],
            action_tags=["typing"],
        ),
    )

    return VideoWindowIndex(
        source_path=source_path,
        relative_path="videos/multi.mp4",
        file_name="multi.mp4",
        duration_sec=20.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 10.0]),
        windows=[coarse_window, fine_hit, fine_miss],
    )


def _build_non_overlapped_multi_level_window_index(tmp_path: Path) -> VideoWindowIndex:
    source_path = str((tmp_path / "videos" / "no-overlap.mp4").resolve())
    coarse_window = VideoWindowAnnotation(
        window_id="coarse-10",
        source_path=source_path,
        relative_path="videos/no-overlap.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        sample_count=10,
        sample_fps=1.0,
        features=WindowFeatures(
            brightness_mean=62.0,
            saturation_mean=35.0,
            motion_mean=20.0,
            readability_score=80.0,
        ),
        semantic=WindowSemanticTag(
            caption="calm city transition",
            objects=["city"],
            scene_tags=["street"],
            action_tags=["walk"],
        ),
    )
    fine_a = VideoWindowAnnotation(
        window_id="fine-a",
        source_path=source_path,
        relative_path="videos/no-overlap.mp4",
        level=2.0,
        window_size_sec=2.0,
        stride_sec=1.0,
        start_sec=12.0,
        end_sec=14.0,
        duration_sec=2.0,
        sample_count=2,
        sample_fps=1.0,
        features=WindowFeatures(
            brightness_mean=58.0,
            saturation_mean=33.0,
            motion_mean=22.0,
            readability_score=78.0,
        ),
        semantic=WindowSemanticTag(caption="far segment A"),
    )
    fine_b = VideoWindowAnnotation(
        window_id="fine-b",
        source_path=source_path,
        relative_path="videos/no-overlap.mp4",
        level=2.0,
        window_size_sec=2.0,
        stride_sec=1.0,
        start_sec=16.0,
        end_sec=18.0,
        duration_sec=2.0,
        sample_count=2,
        sample_fps=1.0,
        features=WindowFeatures(
            brightness_mean=56.0,
            saturation_mean=32.0,
            motion_mean=23.0,
            readability_score=79.0,
        ),
        semantic=WindowSemanticTag(caption="far segment B"),
    )

    return VideoWindowIndex(
        source_path=source_path,
        relative_path="videos/no-overlap.mp4",
        file_name="no-overlap.mp4",
        duration_sec=24.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 10.0]),
        windows=[coarse_window, fine_a, fine_b],
    )


def _build_two_source_window_indices(tmp_path: Path) -> list[VideoWindowIndex]:
    source_a = str((tmp_path / "videos" / "source-a.mp4").resolve())
    source_b = str((tmp_path / "videos" / "source-b.mp4").resolve())

    index_a = VideoWindowIndex(
        source_path=source_a,
        relative_path="videos/source-a.mp4",
        file_name="source-a.mp4",
        duration_sec=20.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 10.0]),
        windows=[
            VideoWindowAnnotation(
                window_id="a-coarse",
                source_path=source_a,
                relative_path="videos/source-a.mp4",
                level=10.0,
                window_size_sec=10.0,
                stride_sec=5.0,
                start_sec=0.0,
                end_sec=10.0,
                duration_sec=10.0,
                semantic=WindowSemanticTag(caption="city transition"),
            ),
            VideoWindowAnnotation(
                window_id="a-fine-1",
                source_path=source_a,
                relative_path="videos/source-a.mp4",
                level=2.0,
                window_size_sec=2.0,
                stride_sec=1.0,
                start_sec=0.0,
                end_sec=2.0,
                duration_sec=2.0,
                features=WindowFeatures(readability_score=95.0),
                semantic=WindowSemanticTag(caption="city transition"),
            ),
            VideoWindowAnnotation(
                window_id="a-fine-2",
                source_path=source_a,
                relative_path="videos/source-a.mp4",
                level=2.0,
                window_size_sec=2.0,
                stride_sec=1.0,
                start_sec=2.0,
                end_sec=4.0,
                duration_sec=2.0,
                features=WindowFeatures(readability_score=92.0),
                semantic=WindowSemanticTag(caption="city transition"),
            ),
        ],
    )

    index_b = VideoWindowIndex(
        source_path=source_b,
        relative_path="videos/source-b.mp4",
        file_name="source-b.mp4",
        duration_sec=20.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 10.0]),
        windows=[
            VideoWindowAnnotation(
                window_id="b-coarse",
                source_path=source_b,
                relative_path="videos/source-b.mp4",
                level=10.0,
                window_size_sec=10.0,
                stride_sec=5.0,
                start_sec=0.0,
                end_sec=10.0,
                duration_sec=10.0,
                semantic=WindowSemanticTag(caption="city transition"),
            ),
            VideoWindowAnnotation(
                window_id="b-fine-1",
                source_path=source_b,
                relative_path="videos/source-b.mp4",
                level=2.0,
                window_size_sec=2.0,
                stride_sec=1.0,
                start_sec=0.0,
                end_sec=2.0,
                duration_sec=2.0,
                features=WindowFeatures(readability_score=80.0),
                semantic=WindowSemanticTag(caption="city transition"),
            ),
        ],
    )

    return [index_a, index_b]

    service = RetrievalService(index_service=StubIndexService())
    window_index = _build_window_index(tmp_path)

    monkeypatch.setattr(service, "_load_window_indices", lambda _root: [window_index])

    request = SearchRequest(
        text="转场到城市街道",
        annotation_root=str(tmp_path),
        window_annotation_root=str(tmp_path),
        top_k=1,
        search_mode="window_level",
        ranking_strategy="cascade_v1",
        coarse_top_n=10,
        fine_top_k=5,
    )

    response = service.search(request)

    assert response["success"] is True
    assert response["count"] == 1
    assert response["results"][0]["source_scope"] == "window"
    assert response["results"][0]["window_id"] == "window-a"


def test_window_level_preferred_can_fallback_file_level(monkeypatch, tmp_path):
    service = RetrievalService(index_service=StubIndexService())

    monkeypatch.setattr(service, "_load_window_indices", lambda _root: [])

    fake_file_result = RetrievalResult(
        source_path="/tmp/file.mp4",
        relative_path="videos/file.mp4",
        media_type="video",
        annotation_path="/tmp/file.mp4.json",
        score=ScoreBreakdown(total=0.9),
        source_scope="file",
    )

    monkeypatch.setattr(service, "_rank_documents", lambda *args, **kwargs: [fake_file_result])
    monkeypatch.setattr(
        service.query_analyzer,
        "analyze",
        lambda *args, **kwargs: QueryIntent(preferred_role="transition", estimated_duration=4.0),
    )

    request = SearchRequest(
        text="转场镜头",
        annotation_root=str(tmp_path),
        top_k=1,
        search_mode="file_level",
        window_level_preferred=True,
    )

    response = service.search(request)

    assert response["success"] is True
    assert response["count"] == 1
    assert response["results"][0]["source_scope"] == "file"


def test_window_level_staged_retrieval_prefers_fine_windows(monkeypatch, tmp_path):
    service = RetrievalService(index_service=StubIndexService())
    window_index = _build_multi_level_window_index(tmp_path)

    monkeypatch.setattr(service, "_load_window_indices", lambda _root: [window_index])

    request = SearchRequest(
        text="city transition",
        annotation_root=str(tmp_path),
        window_annotation_root=str(tmp_path),
        top_k=2,
        search_mode="window_level",
        coarse_top_n=5,
        fine_top_k=5,
    )

    response = service.search(request)

    assert response["success"] is True
    assert response["count"] >= 1
    top = response["results"][0]
    assert top["window_level"] == 2.0
    assert top["window_id"] == "fine-2-hit"
    assert top["score"]["keyword_score"] > 0


def test_window_level_staged_retrieval_fallbacks_to_all_fine_when_no_overlap(monkeypatch, tmp_path):
    service = RetrievalService(index_service=StubIndexService())
    window_index = _build_non_overlapped_multi_level_window_index(tmp_path)

    monkeypatch.setattr(service, "_load_window_indices", lambda _root: [window_index])

    request = SearchRequest(
        text="city transition",
        annotation_root=str(tmp_path),
        window_annotation_root=str(tmp_path),
        top_k=2,
        search_mode="window_level",
        coarse_top_n=5,
        fine_top_k=5,
    )

    response = service.search(request)

    assert response["success"] is True
    returned_ids = {item["window_id"] for item in response["results"]}
    assert returned_ids.issubset({"fine-a", "fine-b"})
    assert response["results"][0]["window_level"] == 2.0


def test_batch_window_level_staged_retrieval_supports_cascade_sequence(monkeypatch, tmp_path):
    service = RetrievalService(index_service=StubIndexService())
    window_index = _build_multi_level_window_index(tmp_path)

    monkeypatch.setattr(service, "_load_window_indices", lambda _root: [window_index])

    request = BatchSearchRequest(
        texts="city transition\ncity street",
        annotation_root=str(tmp_path),
        window_annotation_root=str(tmp_path),
        search_mode="window_level",
        ranking_strategy="cascade_sequence_v1",
        top_k_per_line=1,
        coarse_top_n=5,
        fine_top_k=5,
    )

    response = service.batch_search(request)

    assert response["success"] is True
    assert response["count"] == 2
    assert len(response["items"]) == 2
    for item in response["items"]:
        assert item["results"]
        assert item["results"][0]["window_level"] == 2.0


def test_window_level_staged_retrieval_skips_sources_without_coarse_hits(tmp_path):
    service = RetrievalService(index_service=StubIndexService())

    source_hit = str((tmp_path / "videos" / "hit.mp4").resolve())
    source_noise = str((tmp_path / "videos" / "noise.mp4").resolve())

    hit_index = VideoWindowIndex(
        source_path=source_hit,
        relative_path="videos/hit.mp4",
        file_name="hit.mp4",
        duration_sec=20.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 10.0]),
        windows=[
            VideoWindowAnnotation(
                window_id="hit-coarse",
                source_path=source_hit,
                relative_path="videos/hit.mp4",
                level=10.0,
                window_size_sec=10.0,
                stride_sec=5.0,
                start_sec=0.0,
                end_sec=10.0,
                duration_sec=10.0,
                semantic=WindowSemanticTag(caption="city transition"),
            ),
            VideoWindowAnnotation(
                window_id="hit-fine",
                source_path=source_hit,
                relative_path="videos/hit.mp4",
                level=2.0,
                window_size_sec=8.0,
                stride_sec=1.0,
                start_sec=0.0,
                end_sec=8.0,
                duration_sec=8.0,
                features=WindowFeatures(readability_score=10.0),
                semantic=WindowSemanticTag(caption="matched fine"),
            ),
        ],
    )

    noise_index = VideoWindowIndex(
        source_path=source_noise,
        relative_path="videos/noise.mp4",
        file_name="noise.mp4",
        duration_sec=20.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 10.0]),
        windows=[
            VideoWindowAnnotation(
                window_id="noise-coarse",
                source_path=source_noise,
                relative_path="videos/noise.mp4",
                level=10.0,
                window_size_sec=10.0,
                stride_sec=5.0,
                start_sec=0.0,
                end_sec=10.0,
                duration_sec=10.0,
                semantic=WindowSemanticTag(caption="indoor office typing"),
            ),
            VideoWindowAnnotation(
                window_id="noise-fine",
                source_path=source_noise,
                relative_path="videos/noise.mp4",
                level=2.0,
                window_size_sec=2.0,
                stride_sec=1.0,
                start_sec=0.0,
                end_sec=2.0,
                duration_sec=2.0,
                features=WindowFeatures(readability_score=95.0),
                semantic=WindowSemanticTag(caption="strong duration but no coarse hit"),
            ),
        ],
    )

    ranked = service._run_staged_window_retrieval(
        window_indices=[hit_index, noise_index],
        query_state=QueryState(text="city transition", keywords=["city transition"], estimated_duration=2.0),
        coarse_top_n=5,
        fine_top_k=5,
        fallback_top_k=5,
    )

    returned_ids = {item.window.window_id for item in ranked}
    assert "hit-fine" in returned_ids
    assert "noise-fine" not in returned_ids




def test_window_level_staged_retrieval_fallbacks_when_all_coarse_miss(tmp_path):
    service = RetrievalService(index_service=StubIndexService())

    source_a = str((tmp_path / "videos" / "miss-a.mp4").resolve())
    source_b = str((tmp_path / "videos" / "miss-b.mp4").resolve())

    miss_a_index = VideoWindowIndex(
        source_path=source_a,
        relative_path="videos/miss-a.mp4",
        file_name="miss-a.mp4",
        duration_sec=20.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 10.0]),
        windows=[
            VideoWindowAnnotation(
                window_id="miss-a-coarse",
                source_path=source_a,
                relative_path="videos/miss-a.mp4",
                level=10.0,
                window_size_sec=10.0,
                stride_sec=5.0,
                start_sec=0.0,
                end_sec=10.0,
                duration_sec=10.0,
                semantic=WindowSemanticTag(caption="indoor office typing"),
            ),
            VideoWindowAnnotation(
                window_id="miss-a-fine",
                source_path=source_a,
                relative_path="videos/miss-a.mp4",
                level=2.0,
                window_size_sec=3.0,
                stride_sec=1.0,
                start_sec=2.0,
                end_sec=5.0,
                duration_sec=3.0,
                features=WindowFeatures(readability_score=90.0),
                semantic=WindowSemanticTag(caption="fallback candidate a"),
            ),
        ],
    )

    miss_b_index = VideoWindowIndex(
        source_path=source_b,
        relative_path="videos/miss-b.mp4",
        file_name="miss-b.mp4",
        duration_sec=20.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 10.0]),
        windows=[
            VideoWindowAnnotation(
                window_id="miss-b-coarse",
                source_path=source_b,
                relative_path="videos/miss-b.mp4",
                level=10.0,
                window_size_sec=10.0,
                stride_sec=5.0,
                start_sec=0.0,
                end_sec=10.0,
                duration_sec=10.0,
                semantic=WindowSemanticTag(caption="night room computer"),
            ),
            VideoWindowAnnotation(
                window_id="miss-b-fine",
                source_path=source_b,
                relative_path="videos/miss-b.mp4",
                level=2.0,
                window_size_sec=8.0,
                stride_sec=1.0,
                start_sec=0.0,
                end_sec=8.0,
                duration_sec=8.0,
                features=WindowFeatures(readability_score=20.0),
                semantic=WindowSemanticTag(caption="fallback candidate b"),
            ),
        ],
    )

    ranked = service._run_staged_window_retrieval(
        window_indices=[miss_a_index, miss_b_index],
        query_state=QueryState(text="city transition", keywords=["city transition"], estimated_duration=3.0),
        coarse_top_n=5,
        fine_top_k=5,
        fallback_top_k=5,
    )

    assert ranked
    returned_ids = {item.window.window_id for item in ranked}
    assert returned_ids.issubset({"miss-a-fine", "miss-b-fine"})
    assert ranked[0].window.window_id == "miss-a-fine"


def test_coarse_filter_semantic_ignores_nonsemantic_penalties(monkeypatch, tmp_path):
    source_path = str((tmp_path / "videos" / "semantic-only.mp4").resolve())
    query_state = QueryState(text="city transition", keywords=["city transition"])

    semantic_hit = VideoWindowAnnotation(
        window_id="hit",
        source_path=source_path,
        relative_path="videos/semantic-only.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        features=WindowFeatures(
            brightness_mean=2.0,
            saturation_mean=2.0,
            motion_mean=1.0,
            readability_score=1.0,
        ),
        semantic=WindowSemanticTag(caption="city transition"),
    )
    semantic_miss = VideoWindowAnnotation(
        window_id="miss",
        source_path=source_path,
        relative_path="videos/semantic-only.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=10.0,
        end_sec=20.0,
        duration_sec=10.0,
        features=WindowFeatures(
            brightness_mean=90.0,
            saturation_mean=90.0,
            motion_mean=90.0,
            readability_score=100.0,
        ),
        semantic=WindowSemanticTag(caption="empty hallway"),
    )

    candidates = filter_candidates_semantic([semantic_miss, semantic_hit], query_state, coarse_top_n=1)

    assert candidates[0].window.window_id == "hit"


def test_coarse_filter_uses_token_synonyms(monkeypatch, tmp_path):
    import media_service.retrieval.coarse_filter as coarse_filter

    monkeypatch.setattr(
        coarse_filter,
        "get_synonyms",
        lambda term: ["automobile"] if term == "car" else [],
    )

    source_path = str((tmp_path / "videos" / "syn.mp4").resolve())
    window = VideoWindowAnnotation(
        window_id="syn-hit",
        source_path=source_path,
        relative_path="videos/syn.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        semantic=WindowSemanticTag(objects=["automobile"]),
    )
    query_state = QueryState(text="car", keywords=["car"])

    candidates = filter_candidates_semantic([window], query_state, coarse_top_n=1)

    assert candidates[0].coarse_score > 0






def test_batch_window_level_staged_retrieval_avoids_repeated_source(monkeypatch, tmp_path):
    service = RetrievalService(index_service=StubIndexService())
    indices = _build_two_source_window_indices(tmp_path)

    monkeypatch.setattr(service, "_load_window_indices", lambda _root: indices)

    request = BatchSearchRequest(
        texts="city transition\ncity transition",
        annotation_root=str(tmp_path),
        window_annotation_root=str(tmp_path),
        search_mode="window_level",
        ranking_strategy="single_stage",
        top_k_per_line=1,
        coarse_top_n=5,
        fine_top_k=5,
    )

    response = service.batch_search(request)

    assert response["success"] is True
    assert len(response["items"]) == 2
    first = response["items"][0]["results"][0]
    second = response["items"][1]["results"][0]
    assert first["source_path"] != second["source_path"]


def test_batch_window_level_staged_retrieval_allows_repeat_when_candidates_insufficient(monkeypatch, tmp_path):
    service = RetrievalService(index_service=StubIndexService())
    single_index = _build_multi_level_window_index(tmp_path)

    monkeypatch.setattr(service, "_load_window_indices", lambda _root: [single_index])

    request = BatchSearchRequest(
        texts="city transition\ncity transition",
        annotation_root=str(tmp_path),
        window_annotation_root=str(tmp_path),
        search_mode="window_level",
        ranking_strategy="single_stage",
        top_k_per_line=1,
        coarse_top_n=5,
        fine_top_k=5,
    )

    response = service.batch_search(request)

    assert response["success"] is True
    assert len(response["items"]) == 2
    first = response["items"][0]["results"][0]
    second = response["items"][1]["results"][0]
    assert first["source_path"] == second["source_path"]

    service = RetrievalService(index_service=StubIndexService())

    source_path = str((tmp_path / "videos" / "duration-level.mp4").resolve())
    level_map = {
        2.0: [
            VideoWindowAnnotation(
                window_id="l2-a",
                source_path=source_path,
                relative_path="videos/duration-level.mp4",
                level=2.0,
                window_size_sec=2.0,
                stride_sec=1.0,
                start_sec=0.0,
                end_sec=2.0,
                duration_sec=2.0,
            )
        ],
        5.0: [
            VideoWindowAnnotation(
                window_id="l5-a",
                source_path=source_path,
                relative_path="videos/duration-level.mp4",
                level=5.0,
                window_size_sec=5.0,
                stride_sec=2.5,
                start_sec=0.0,
                end_sec=5.0,
                duration_sec=5.0,
            )
        ],
        10.0: [
            VideoWindowAnnotation(
                window_id="l10-a",
                source_path=source_path,
                relative_path="videos/duration-level.mp4",
                level=10.0,
                window_size_sec=10.0,
                stride_sec=5.0,
                start_sec=0.0,
                end_sec=10.0,
                duration_sec=10.0,
            )
        ],
    }

    fine_level = service._select_fine_level(level_map, estimated_duration=4.3)

    assert fine_level == 5.0


def test_select_fine_level_defaults_to_min_without_duration(tmp_path):
    service = RetrievalService(index_service=StubIndexService())

    source_path = str((tmp_path / "videos" / "duration-default.mp4").resolve())
    level_map = {
        10.0: [
            VideoWindowAnnotation(
                window_id="l10-a",
                source_path=source_path,
                relative_path="videos/duration-default.mp4",
                level=10.0,
                window_size_sec=10.0,
                stride_sec=5.0,
                start_sec=0.0,
                end_sec=10.0,
                duration_sec=10.0,
            )
        ],
        2.0: [
            VideoWindowAnnotation(
                window_id="l2-a",
                source_path=source_path,
                relative_path="videos/duration-default.mp4",
                level=2.0,
                window_size_sec=2.0,
                stride_sec=1.0,
                start_sec=0.0,
                end_sec=2.0,
                duration_sec=2.0,
            )
        ],
    }

    fine_level = service._select_fine_level(level_map, estimated_duration=0.0)

    assert fine_level == 2.0

    source_path = str((tmp_path / "videos" / "flower.mp4").resolve())
    query_state = QueryState(text="colour fish", keywords=["colour fish"])

    window = VideoWindowAnnotation(
        window_id="flower-window",
        source_path=source_path,
        relative_path="videos/flower.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        semantic=WindowSemanticTag(caption="colored flower in bright nature"),
    )

    candidate = filter_candidates_semantic([window], query_state, coarse_top_n=1)[0]

    assert candidate.coarse_score < 0.3


def test_semantic_coarse_true_object_match_is_high(tmp_path):
    source_path = str((tmp_path / "videos" / "fish.mp4").resolve())
    query_state = QueryState(text="fish", keywords=["fish"])

    window = VideoWindowAnnotation(
        window_id="fish-window",
        source_path=source_path,
        relative_path="videos/fish.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        semantic=WindowSemanticTag(objects=["fish"]),
    )

    candidate = filter_candidates_semantic([window], query_state, coarse_top_n=1)[0]

    assert candidate.coarse_score > 0.75


def test_semantic_coarse_synonym_assisted_match_improves(monkeypatch, tmp_path):
    import media_service.retrieval.coarse_filter as coarse_filter

    monkeypatch.setattr(
        coarse_filter,
        "get_synonyms",
        lambda term: ["automobile"] if term == "car" else [],
    )

    source_path = str((tmp_path / "videos" / "car.mp4").resolve())
    window = VideoWindowAnnotation(
        window_id="car-window",
        source_path=source_path,
        relative_path="videos/car.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        semantic=WindowSemanticTag(objects=["automobile"]),
    )

    without_syn = filter_candidates_semantic([window], QueryState(text="car", keywords=["car"]), coarse_top_n=1)[0].coarse_score

    monkeypatch.setattr(
        coarse_filter,
        "get_synonyms",
        lambda term: [],
    )
    without_support = filter_candidates_semantic([window], QueryState(text="car", keywords=["car"]), coarse_top_n=1)[0].coarse_score

    assert without_syn > without_support


def test_semantic_coarse_chinese_matching_works(tmp_path):
    source_path = str((tmp_path / "videos" / "cn.mp4").resolve())
    query_state = QueryState(text="城市 转场", keywords=["城市 转场"])

    window = VideoWindowAnnotation(
        window_id="cn-window",
        source_path=source_path,
        relative_path="videos/cn.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        semantic=WindowSemanticTag(scene_tags=["城市", "街道"], action_tags=["转场"]),
    )

    candidate = filter_candidates_semantic([window], query_state, coarse_top_n=1)[0]

    assert candidate.coarse_score > 0.6


def test_semantic_coarse_empty_query_and_window_edge_cases(tmp_path):
    source_path = str((tmp_path / "videos" / "edge.mp4").resolve())
    query_state = QueryState(text="", keywords=[])

    empty_window = VideoWindowAnnotation(
        window_id="edge-window",
        source_path=source_path,
        relative_path="videos/edge.mp4",
        level=10.0,
        window_size_sec=10.0,
        stride_sec=5.0,
        start_sec=0.0,
        end_sec=10.0,
        duration_sec=10.0,
        semantic=WindowSemanticTag(),
    )

    candidate = filter_candidates_semantic([empty_window], query_state, coarse_top_n=1)[0]

    assert candidate.coarse_score == 0.5
