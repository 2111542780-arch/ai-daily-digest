"""Filter, deduplicate, score and split news into four user-facing categories."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from .utils import CONFIG_DIR, load_seen_urls, load_yaml, save_seen_urls

logger = logging.getLogger(__name__)
_SOURCE_WEIGHT = {"critical": 1.0, "high": 0.8, "medium": 0.5}
_CATEGORY_ORDER = ["ai", "china", "international", "finance"]

def _keyword_score(item: dict, kw_cfg: dict) -> float:
    text = (item["title"] + " " + item["summary"][:300]).lower()
    score = 0.0
    for kw in kw_cfg.get("critical", []):
        if kw.lower() in text: score += 10
    for kw in kw_cfg.get("high", []):
        if kw.lower() in text: score += 5
    for kw in kw_cfg.get("medium", []):
        if kw.lower() in text: score += 2
    return score

def _recency_bonus(published: datetime) -> float:
    now = datetime.now(timezone.utc)
    if published.tzinfo is None: published = published.replace(tzinfo=timezone.utc)
    diff_hours = (now - published).total_seconds() / 3600
    if diff_hours < 3: return 5
    if diff_hours < 6: return 3
    if diff_hours < 12: return 1
    return 0

def _category(item: dict) -> str | None:
    tags = set(item.get("source_tags") or [])
    for category in _CATEGORY_ORDER:
        if category in tags: return category
    return None

def filter_and_score_tracks(raw_items: list[dict], user_cfg: dict, lookback_hours: int) -> dict[str, list[dict]]:
    kw_cfg = load_yaml(CONFIG_DIR / "keywords.yaml").get("keywords", {})
    filt_cfg = user_cfg.get("filter", {})
    tracks_cfg = user_cfg.get("tracks", {})
    block_kws = [k.lower() for k in (filt_cfg.get("block_keywords") or [])]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    seen_urls = load_seen_urls()
    candidates = []

    for item in raw_items:
        published = item["published"]
        if published.tzinfo is None: published = published.replace(tzinfo=timezone.utc)
        if published < cutoff or not item.get("url") or item["url"] in seen_urls: continue
        text_lower = (item["title"] + " " + item["summary"]).lower()
        if any(bk in text_lower for bk in block_kws): continue
        category = _category(item)
        if not category: continue
        item["category"] = category
        candidates.append(item)

    tracks = {k: [] for k in _CATEGORY_ORDER}
    for category in _CATEGORY_ORDER:
        cfg = tracks_cfg.get(category, {})
        min_score = float(cfg.get("min_score", 1))
        max_items = int(cfg.get("max_items", 5))
        pool = [i for i in candidates if i["category"] == category]
        for item in pool:
            keyword = _keyword_score(item, kw_cfg)
            source_weight = _SOURCE_WEIGHT.get(item.get("source_priority", "medium"), 0.5)
            item["score"] = keyword * source_weight + _recency_bonus(item["published"])
        ranked = sorted(pool, key=lambda x: x["score"], reverse=True)
        tracks[category] = [i for i in ranked if i["score"] >= min_score][:max_items]

    save_seen_urls([item["url"] for items in tracks.values() for item in items])
    logger.info("Categories — %s", ", ".join(f"{k}: {len(tracks[k])}" for k in _CATEGORY_ORDER))
    return tracks
