from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from media_service.analyzers.query_understanding import QueryUnderstandingAnalyzer
from media_service.config.settings import default_window_annotation_root
from media_service.model.schemas import BatchSearchRequest, ExplainRequest, MediaAnnotation, RetrievalResult, SearchRequest, ScoreBreakdown
from media_service.retrieval.coarse_filter import WindowCandidate, filter_candidates_semantic
from media_service.retrieval.query_builder import build_query_state
from media_service.retrieval.sequence_ranker import rerank_with_previous
from media_service.retrieval.window_ranker import rank_candidates
from media_service.scoring.coherence import CoherenceScorer
from media_service.scoring.scorer import RetrievalScorer
from media_service.service.index_service import IndexService
from media_service.utils.io import read_annotation
from media_service.utils.text import split_texts
from media_service.windowing.schema import VideoWindowAnnotation
from media_service.windowing.storage import WindowIndexStorage


class RetrievalService:
    def __init__(self, index_service: IndexService | None = None) -> None:
        self.index_service = index_service or IndexService()
        self.query_analyzer = QueryUnderstandingAnalyzer()
        self.scorer = RetrievalScorer()
        self.coherence_scorer = CoherenceScorer()
        self.window_storage = WindowIndexStorage()

    def search(self, request: SearchRequest) -> Dict[str, Any]:
        annotation_root = Path(request.annotation_root).resolve()
        documents = self.index_service.get_index(annotation_root)
        duration_source_text = request.duration_text if request.duration_text else request.text
        intent = self.query_analyzer.analyze(duration_source_text, request.texts, request.index, request.prefer_media_type)
        if request.duration is not None and request.duration > 0:
            intent.estimated_duration = float(request.duration)
        should_use_window = self._should_use_window_level(
            search_mode=request.search_mode,
            window_level_preferred=request.window_level_preferred,
            intent=intent,
            text=request.text,
        )
        if should_use_window:
            window_results = self._search_window_level(request, intent)
            top_k = request.top_k
            return {
                "success": True,
                "intent": intent.model_dump(mode="json"),
                "count": len(window_results[:top_k]),
                "results": [item.model_dump(mode="json") for item in window_results[:top_k]],
            }
        results = self._rank_documents(documents, annotation_root, intent, explain=request.explain)
        return {
            "success": True,
            "intent": intent.model_dump(mode="json"),
            "count": len(results[: request.top_k]),
            "results": [result.model_dump(mode="json") for result in results[: request.top_k]],
        }

    def batch_search(self, request: BatchSearchRequest) -> Dict[str, Any]:
        lines = split_texts(request.texts)
        duration_lines = split_texts(request.duration_texts)
        durations = request.durations or []
        annotation_root = Path(request.annotation_root).resolve()
        documents = self.index_service.get_index(annotation_root)
        should_use_window = request.search_mode == "window_level"
        if request.window_level_preferred and request.search_mode != "window_level":
            should_use_window = True

        if should_use_window:
            window_items = self._batch_search_window_level(request, lines, duration_lines)
            if window_items or request.search_mode == "window_level":
                empty_result_indices = [
                    item.get("index", idx)
                    for idx, item in enumerate(window_items)
                    if len(item.get("results") or []) == 0
                ]
                response: Dict[str, Any] = {"success": True, "count": len(window_items), "items": window_items}
                if empty_result_indices:
                    response["has_empty_results"] = True
                    response["empty_result_indices"] = empty_result_indices
                    response["message"] = "some queries returned no retrieval results"
                else:
                    response["has_empty_results"] = False
                return response
        batches: List[Dict[str, Any]] = []
        previous_annotation: MediaAnnotation | None = None
        for index, line in enumerate(lines):
            duration_line = duration_lines[index] if index < len(duration_lines) else line
            intent = self.query_analyzer.analyze(duration_line, duration_lines or lines, index, request.prefer_media_type)
            if index < len(durations) and durations[index] > 0:
                intent.estimated_duration = float(durations[index])
            elif request.duration is not None and request.duration > 0:
                intent.estimated_duration = float(request.duration)
            results = self._rank_documents(documents, annotation_root, intent, previous_annotation=previous_annotation, explain=False)
            top_results = results[: request.top_k_per_line]
            if top_results:
                chosen = top_results[0]
                for doc in documents:
                    if doc.source_path == chosen.source_path:
                        previous_annotation = doc
                        break
            batches.append({
                "index": index,
                "text": line,
                "intent": intent.model_dump(mode="json"),
                "results": [item.model_dump(mode="json") for item in top_results],
            })
        return {"success": True, "count": len(batches), "items": batches}


    def explain(self, request: ExplainRequest) -> Dict[str, Any]:
        annotation = read_annotation(Path(request.annotation_path).resolve())
        intent = self.query_analyzer.analyze(request.text, request.texts, request.index, request.prefer_media_type)
        coherence_score, notes = self.coherence_scorer.score(annotation, intent)
        result = self.scorer.score(annotation, str(Path(request.annotation_path).resolve()), intent, coherence_score, notes, explain=True)
        return {"success": True, "intent": intent.model_dump(mode="json"), "result": result.model_dump(mode="json")}

    def debug_window_sources(self, annotation_root: str | None = None, window_annotation_root: str | None = None) -> Dict[str, Any]:
        roots = self._resolve_window_roots_from_values(annotation_root, window_annotation_root)
        details = []
        total_indices = 0
        total_windows = 0

        for root in roots:
            index_files = self.window_storage.list_indices(root)
            window_count = 0
            loaded_indices = 0
            load_errors = 0

            for path in index_files:
                try:
                    index = self.window_storage.load_index(path)
                    loaded_indices += 1
                    window_count += len(index.windows)
                except Exception:
                    load_errors += 1

            total_indices += loaded_indices
            total_windows += window_count
            details.append(
                {
                    "root": str(root),
                    "index_dir": str(self.window_storage.resolve_index_dir(root)),
                    "index_file_candidates": len(index_files),
                    "loaded_indices": loaded_indices,
                    "load_errors": load_errors,
                    "window_count": window_count,
                }
            )

        return {
            "success": True,
            "roots": [str(root) for root in roots],
            "total_loaded_indices": total_indices,
            "total_windows": total_windows,
            "details": details,
        }

    def _rank_documents(self, documents: List[MediaAnnotation], annotation_root: Path, intent, previous_annotation: MediaAnnotation | None = None, explain: bool = False):
        scored = []
        for document in documents:
            if document.status != "ok":
                continue
            if intent.prefer_media_type in {"image", "video"} and document.media_type != intent.prefer_media_type:
                continue
            coherence_score, notes = self.coherence_scorer.score(document, intent, previous_annotation)
            annotation_path = str((annotation_root / f"{document.relative_path}.json").resolve())
            scored.append(self.scorer.score(document, annotation_path, intent, coherence_score, notes, explain=explain))
        scored.sort(key=lambda item: item.score.total, reverse=True)
        return scored

    def _should_use_window_level(self, search_mode: str, window_level_preferred: bool, intent, text: str) -> bool:
        if search_mode == "window_level":
            return True
        if not window_level_preferred:
            return False
        if intent.preferred_role in {"transition", "background", "action"}:
            return True
        content = (text or "").lower()
        transition_keywords = ["然后", "接着", "随后", "转场", "过渡", "next", "then", "transition"]
        return any(token in content for token in transition_keywords)

    def _resolve_window_roots(self, request) -> List[Path]:
        return self._resolve_window_roots_from_values(request.annotation_root, request.window_annotation_root)

    def _resolve_window_roots_from_values(self, annotation_root: str | None, window_annotation_root: str | None) -> List[Path]:
        roots: List[Path] = []
        for root in [window_annotation_root, annotation_root, str(default_window_annotation_root())]:
            if not root:
                continue
            resolved = Path(root).resolve()
            if resolved not in roots:
                roots.append(resolved)
        return roots

    def _load_window_indices_from_roots(self, request) -> List:
        roots = self._resolve_window_roots(request)
        collected = []
        seen_source_paths: set[str] = set()
        for root in roots:
            for index in self._load_window_indices(root):
                source_path = str(index.source_path)
                if source_path in seen_source_paths:
                    continue
                seen_source_paths.add(source_path)
                collected.append(index)
        return collected

    def _build_fallback_candidates(self, windows: List[VideoWindowAnnotation], limit: int) -> List[WindowCandidate]:
        return [
            WindowCandidate(window=window, coarse_score=0.0, total_score=0.0)
            for window in windows[: max(limit, 1)]
        ]

    def _search_window_level(self, request: SearchRequest, intent) -> List[RetrievalResult]:
        window_indices = self._load_window_indices_from_roots(request)
        if not window_indices:
            return []

        query_state = build_query_state(request.text, intent)
        result_candidates = self._run_staged_window_retrieval(
            window_indices=window_indices,
            query_state=query_state,
            coarse_top_n=request.coarse_top_n,
            fine_top_k=request.fine_top_k,
            fallback_top_k=request.top_k,
        )

        top_k = request.top_k if request.fine_top_k <= 0 else min(request.top_k, request.fine_top_k)
        return [self._candidate_to_result(item, source_scope="window") for item in result_candidates[:top_k]]

    def _batch_search_window_level(self, request: BatchSearchRequest, lines: List[str], duration_lines: List[str]) -> List[Dict[str, Any]]:
        window_indices = self._load_window_indices_from_roots(request)
        if not window_indices:
            return []

        previous_selected: WindowCandidate | None = None
        items: List[Dict[str, Any]] = []
        durations = request.durations or []
        used_source_paths: Set[str] = set()
        used_window_ids: Set[str] = set()

        for index, line in enumerate(lines):
            duration_line = duration_lines[index] if index < len(duration_lines) else line
            # intent = self.query_analyzer.analyze(duration_line, duration_lines or lines, index, request.prefer_media_type)
            intent = self.query_analyzer.analyze(line,lines, index, request.prefer_media_type)
            if index < len(durations) and durations[index] > 0:
                intent.estimated_duration = float(durations[index])
            elif request.duration is not None and request.duration > 0:
                intent.estimated_duration = float(request.duration)
            query_state = build_query_state(
                line,
                intent,
                previous_selected_window_id=previous_selected.window.window_id if previous_selected else None,
                previous_style_signature=(
                    {
                        "brightness_mean": previous_selected.window.features.brightness_mean,
                        "motion_mean": previous_selected.window.features.motion_mean,
                    }
                    if previous_selected
                    else None
                ),
                previous_source_path=previous_selected.window.source_path if previous_selected else None,
            )

            staged_candidates = self._run_staged_window_retrieval(
                window_indices=window_indices,
                query_state=query_state,
                coarse_top_n=request.coarse_top_n,
                fine_top_k=request.fine_top_k,
                fallback_top_k=request.top_k_per_line,
                excluded_source_paths=used_source_paths,
                excluded_window_ids=used_window_ids,
            )
            ranked = staged_candidates
            if request.ranking_strategy == "cascade_sequence_v1" and ranked:
                ranked = rerank_with_previous(ranked, previous_selected, text=line)

            result_candidates = ranked
            top_results = [self._candidate_to_result(item, source_scope="window") for item in result_candidates[: request.top_k_per_line]]
            if result_candidates:
                previous_selected = result_candidates[0]
            if top_results:
                used_source_paths.update(result.source_path for result in top_results if result.source_path)
                used_window_ids.update(result.window_id for result in top_results if result.window_id)
            items.append(
                {
                    "index": index,
                    "text": line,
                    "intent": intent.model_dump(mode="json"),
                    "results": [item.model_dump(mode="json") for item in top_results],
                }
            )
        return items

    def _run_staged_window_retrieval(
        self,
        window_indices: List,
        query_state,
        coarse_top_n: int,
        fine_top_k: int,
        fallback_top_k: int,
        excluded_source_paths: Optional[Set[str]] = None,
        excluded_window_ids: Optional[Set[str]] = None,
    ) -> List[WindowCandidate]:
        groups = self._group_windows_by_source_and_level(window_indices)
        if not groups:
            return []

        all_fine_candidates: List[WindowCandidate] = []
        semantic_overrides: Dict[str, float] = {}
        matched_terms_overrides: Dict[str, List[str]] = {}

        for _source_path, level_map in groups.items():
            if not level_map:
                continue

            available_levels = sorted(level_map.keys())
            coarse_level = max(available_levels)
            fine_level = self._select_fine_level(level_map, query_state.estimated_duration)

            coarse_windows = level_map.get(coarse_level, [])
            fine_windows = level_map.get(fine_level, [])
            if not coarse_windows:
                coarse_windows = fine_windows
            if not fine_windows:
                fine_windows = coarse_windows
            if not coarse_windows and not fine_windows:
                continue

            if coarse_level == fine_level:
                coarse_candidates = filter_candidates_semantic(
                    fine_windows,
                    query_state,
                    coarse_top_n=max(coarse_top_n, fine_top_k, fallback_top_k),
                )
                if len(coarse_candidates) == 0:
                    continue
                fine_pool = fine_windows
            else:
                coarse_candidates = filter_candidates_semantic(
                    coarse_windows,
                    query_state,
                    coarse_top_n=coarse_top_n,
                )
                if len(coarse_candidates) == 0:
                    coarse_candidates = filter_candidates_semantic(
                        coarse_windows,
                        query_state,
                        coarse_top_n=max(coarse_top_n, fine_top_k, fallback_top_k),
                    )
                if len(coarse_candidates) == 0:
                    continue
                fine_pool = self._collect_overlapped_fine_windows(fine_windows, coarse_candidates)
                if len(fine_pool) == 0:
                    continue

            fine_candidates = [
                WindowCandidate(window=window, coarse_score=0.0, total_score=0.0)
                for window in fine_pool
            ]
            if not fine_candidates:
                continue

            coarse_assignment = self._assign_coarse_to_fine(fine_candidates, coarse_candidates)
            for fine in fine_candidates:
                candidate_key = self._candidate_key(fine)
                assigned = coarse_assignment.get(candidate_key)
                if not assigned:
                    continue
                semantic_overrides[candidate_key] = round(assigned.coarse_score, 4)
                matched_terms_overrides[candidate_key] = assigned.matched_terms
                fine.coarse_score = round(assigned.coarse_score, 4)
                fine.matched_terms = assigned.matched_terms

            all_fine_candidates.extend(fine_candidates)

        if not all_fine_candidates:
            return []

        ranked = rank_candidates(
            all_fine_candidates,
            query_state,
            fine_top_k=max(fine_top_k, fallback_top_k),
            semantic_overrides=semantic_overrides,
            matched_terms_overrides=matched_terms_overrides,
            excluded_source_paths=excluded_source_paths,
            excluded_window_ids=excluded_window_ids,
        )
        return ranked


    def _select_fine_level(self, level_map: Dict[float, List[VideoWindowAnnotation]], estimated_duration: float) -> float:
        available_levels = sorted(level_map.keys())
        if not available_levels:
            return 0.0
        if estimated_duration <= 0:
            return min(available_levels)

        def _level_score(level: float) -> tuple[float, float]:
            windows = level_map.get(level, [])
            if not windows:
                return (float("inf"), float(level))
            avg_duration = sum(window.duration_sec for window in windows) / len(windows)
            return (abs(avg_duration - estimated_duration), abs(level - estimated_duration))

        return min(available_levels, key=_level_score)

    def _group_windows_by_source_and_level(self, window_indices: List) -> Dict[str, Dict[float, List[VideoWindowAnnotation]]]:
        grouped: Dict[str, Dict[float, List[VideoWindowAnnotation]]] = defaultdict(lambda: defaultdict(list))
        for index in window_indices:
            for window in index.windows:
                grouped[str(window.source_path)][float(window.level)].append(window)
        return grouped

    def _collect_overlapped_fine_windows(
        self,
        fine_windows: List[VideoWindowAnnotation],
        coarse_candidates: List[WindowCandidate],
    ) -> List[VideoWindowAnnotation]:
        selected: List[VideoWindowAnnotation] = []
        seen_window_ids: set[str] = set()
        for fine in fine_windows:
            for coarse in coarse_candidates:
                overlap = self._overlap_duration(fine.start_sec, fine.end_sec, coarse.window.start_sec, coarse.window.end_sec)
                if overlap > 0:
                    if fine.window_id not in seen_window_ids:
                        selected.append(fine)
                        seen_window_ids.add(fine.window_id)
                    break
        return selected

    def _assign_coarse_to_fine(
        self,
        fine_candidates: List[WindowCandidate],
        coarse_candidates: List[WindowCandidate],
    ) -> Dict[str, WindowCandidate]:
        assignments: Dict[str, WindowCandidate] = {}
        for fine in fine_candidates:
            fine_key = self._candidate_key(fine)
            best_match: Optional[Tuple[WindowCandidate, float]] = None
            for coarse in coarse_candidates:
                if coarse.window.source_path != fine.window.source_path:
                    continue
                overlap = self._overlap_duration(
                    fine.window.start_sec,
                    fine.window.end_sec,
                    coarse.window.start_sec,
                    coarse.window.end_sec,
                )
                if overlap <= 0:
                    continue

                if best_match is None:
                    best_match = (coarse, overlap)
                    continue

                prev_coarse, prev_overlap = best_match
                if coarse.coarse_score > prev_coarse.coarse_score:
                    best_match = (coarse, overlap)
                elif coarse.coarse_score == prev_coarse.coarse_score and overlap > prev_overlap:
                    best_match = (coarse, overlap)

            if best_match is None and coarse_candidates:
                same_source = [c for c in coarse_candidates if c.window.source_path == fine.window.source_path]
                if same_source:
                    best = max(same_source, key=lambda c: c.coarse_score)
                    best_match = (best, 0.0)

            if best_match is not None:
                assignments[fine_key] = best_match[0]
        return assignments

    def _candidate_key(self, candidate: WindowCandidate) -> str:
        return f"{candidate.window.source_path}::{candidate.window.window_id}"

    def _overlap_duration(self, start_a: float, end_a: float, start_b: float, end_b: float) -> float:
        return max(0.0, min(end_a, end_b) - max(start_a, start_b))

    def _load_window_indices(self, window_root: Path):
        index_files = self.window_storage.list_indices(window_root)
        indices = []
        for path in index_files:
            try:
                indices.append(self.window_storage.load_index(path))
            except Exception:
                continue
        return indices

    def _flatten_windows(self, window_indices) -> List:
        windows = []
        for index in window_indices:
            windows.extend(index.windows)
        return windows

    def _candidate_to_result(self, candidate: WindowCandidate, source_scope: str = "window") -> RetrievalResult:
        breakdown = ScoreBreakdown(
            keyword_score=candidate.score_breakdown.get("semantic_score", 0.0),
            style_score=candidate.score_breakdown.get("style_score", 0.0),
            emotion_score=candidate.score_breakdown.get("emotion_score", 0.0),
            rhythm_score=candidate.score_breakdown.get("pace_score", 0.0),
            duration_fit_score=candidate.score_breakdown.get("duration_score", 0.0),
            coherence_score=candidate.score_breakdown.get("continuity_score", 0.0),
            total=candidate.total_score,
        )
        return RetrievalResult(
            source_path=candidate.window.source_path,
            relative_path=candidate.window.relative_path,
            media_type="video",
            annotation_path=candidate.window.source_path,
            score=breakdown,
            matched_terms=candidate.matched_terms,
            estimated_text_duration=0.0,
            media_duration=candidate.window.duration_sec,
            duration_fit_score=candidate.score_breakdown.get("duration_score", 0.0),
            continuity_notes=candidate.continuity_notes,
            annotation={"window": candidate.window.model_dump(mode="json")},
            window_id=candidate.window.window_id,
            window_level=candidate.window.level,
            start_sec=candidate.window.start_sec,
            end_sec=candidate.window.end_sec,
            source_scope=source_scope,
        )
