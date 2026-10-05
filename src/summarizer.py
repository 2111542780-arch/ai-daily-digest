"""LLM-powered news summarization."""
from __future__ import annotations
import asyncio, logging, os
from typing import Any
logger = logging.getLogger(__name__)
_PROVIDERS = {
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "key_env": "DEEPSEEK_API_KEY"},
    "anthropic": {"base_url": None, "key_env": "ANTHROPIC_API_KEY"},
}
_ITEM_SYSTEM_PROMPT = """你是一位专业新闻编辑，负责为普通读者整理每日综合新闻。
请将用户提供的新闻摘要用{language}写成不超过{max_chars}字的中文摘要。
要求：
1. 先说最核心的事实，不说“该文章介绍了”等废话。
2. 保留人物、公司、数字、时间等关键事实。
3. 最后用一句很短的话说明为什么值得关注或可能影响什么。
4. 不编造原文没有的信息。
5. 不做投资买卖建议。"""
_OVERVIEW_SYSTEM_PROMPT = """你是一位专业新闻主编。下面是今天从 AI/科技、中国、国际、财经四个板块筛选出的新闻。
请输出“今日最重要的 3 件事”，每件一行，格式：
1. **事件**：为什么值得关注。
2. **事件**：为什么值得关注。
3. **事件**：为什么值得关注。
只选择真正重要、影响面大的事件；不要重复同一件事。总长度 500 字以内。"""

def _build_client(provider: str) -> Any:
    cfg = _PROVIDERS.get(provider)
    if cfg is None: raise ValueError(f"Unknown provider: {provider!r}")
    key = os.getenv(cfg["key_env"], "")
    if not key: raise EnvironmentError(f"{cfg['key_env']} is not set")
    if provider == "anthropic":
        import anthropic
        return anthropic.AsyncAnthropic(api_key=key)
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=key, base_url=cfg["base_url"])

async def _summarize_one(client, item, user_cfg):
    cfg = user_cfg.get("llm", {})
    provider, model = cfg.get("provider", "openai"), cfg.get("model", "gpt-4o-mini")
    language = "中文" if cfg.get("summary_language", "zh") == "zh" else "English"
    max_chars = cfg.get("max_summary_chars", 140)
    prompt = _ITEM_SYSTEM_PROMPT.format(language=language, max_chars=max_chars)
    user = f"栏目：{item.get('category','')}\n标题：{item['title']}\n原文摘要：{item['summary'][:800]}"
    try:
        if provider == "anthropic":
            r = await client.messages.create(model=model, max_tokens=300, system=prompt, messages=[{"role":"user","content":user}])
            return r.content[0].text.strip()
        r = await client.chat.completions.create(model=model, max_tokens=300, messages=[{"role":"system","content":prompt},{"role":"user","content":user}])
        return r.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("LLM summarization failed for %r: %s", item["title"], exc)
        return item.get("summary", item["title"])[:max_chars]

async def summarize_all(items, user_cfg):
    client = _build_client(user_cfg.get("llm", {}).get("provider", "openai"))
    summaries = await asyncio.gather(*[_summarize_one(client, item, user_cfg) for item in items])
    for item, summary in zip(items, summaries): item["summary_zh"] = summary
    return items

async def generate_overview(items, user_cfg):
    if not items: return ""
    cfg = user_cfg.get("llm", {})
    provider, model = cfg.get("provider", "openai"), cfg.get("model", "gpt-4o-mini")
    client = _build_client(provider)
    bullets = "\n".join(f"- [{i.get('category','')}] {i['title']}: {i.get('summary_zh', i['summary'][:150])}" for i in items)
    try:
        if provider == "anthropic":
            r = await client.messages.create(model=model, max_tokens=500, system=_OVERVIEW_SYSTEM_PROMPT, messages=[{"role":"user","content":bullets}])
            return r.content[0].text.strip()
        r = await client.chat.completions.create(model=model, max_tokens=500, messages=[{"role":"system","content":_OVERVIEW_SYSTEM_PROMPT},{"role":"user","content":bullets}])
        return r.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Overview generation failed: %s", exc)
        return ""
