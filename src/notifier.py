"""WeChat notification via Server酱 (ftqq.com)."""
from __future__ import annotations
import logging, os
import httpx
from .utils import format_time_delta, get_beijing_time

logger = logging.getLogger(__name__)
_SERVERCHAN_API = "https://sctapi.ftqq.com/{key}.send"
_MAX_DESP_BYTES = 32 * 1024
_TRACK_ORDER = ["ai", "china", "international", "finance"]
_TRACK_DEFAULTS = {"ai": "🤖 AI / 科技", "china": "🇨🇳 中国", "international": "🌍 国际", "finance": "💰 财经 / 投资"}

def _render_item(item: dict, index: int, display_cfg: dict) -> str:
    lines = [f"**{index}. {item['title']}**"]
    summary = item.get("summary_zh") or item.get("summary", "")
    if summary: lines.append(summary)
    meta = []
    if display_cfg.get("show_source", True): meta.append(f"📰 {item.get('source_name', '')}")
    if display_cfg.get("show_time", True): meta.append(f"🕐 {format_time_delta(item['published'])}")
    if display_cfg.get("show_links", True) and item.get("url"): meta.append(f"🔗 [原文]({item['url']})")
    if meta: lines.append("  ".join(meta))
    return "\n".join(lines)

def _build_desp(tracks, overview, display_cfg, tracks_cfg):
    sections = []
    if overview: sections.append(f"## 🔥 今日最重要的 3 件事\n\n{overview}\n\n---")
    counter = 1
    for key in _TRACK_ORDER:
        items = tracks.get(key, [])
        if not items: continue
        label = tracks_cfg.get(key, {}).get("label", _TRACK_DEFAULTS[key])
        sections.append(f"## {label}")
        for item in items:
            sections.append(_render_item(item, counter, display_cfg))
            counter += 1
        sections.append("---")
    now = get_beijing_time().strftime("%Y-%m-%d %H:%M")
    sections.append(f"*由 AI Daily Digest 自动生成 · {now}*")
    return "\n\n".join(sections)

async def send_wechat(tracks, overview, schedule, user_cfg):
    key = os.getenv("SERVERCHAN_KEY", "")
    if not key:
        logger.error("SERVERCHAN_KEY is not set — skipping WeChat notification.")
        return
    display_cfg = user_cfg.get("display", {})
    tracks_cfg = user_cfg.get("tracks", {})
    now = get_beijing_time()
    total = sum(len(v) for v in tracks.values())
    title = f"{schedule.get('label', '📰 AI 日报')} · {now.strftime('%Y-%m-%d')} 共{total}条"
    url = _SERVERCHAN_API.format(key=key)
    desp = _build_desp(tracks, overview, display_cfg, tracks_cfg)
    async with httpx.AsyncClient(timeout=15) as client:
        await _post_message(client, url, title, desp)

async def _post_message(client, url, title, desp):
    title = title[:32]
    data = {"title": title, "desp": desp.encode("utf-8")[:_MAX_DESP_BYTES].decode("utf-8", errors="ignore")}
    try:
        resp = await client.post(url, data=data)
        result = resp.json()
        if result.get("code") == 0: logger.info("WeChat message sent: %s", title)
        else: logger.warning("Server酱 returned error: %s", result)
    except Exception as exc:
        logger.error("Failed to send WeChat message: %s", exc)
