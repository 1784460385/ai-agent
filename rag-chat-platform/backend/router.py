import json
import logging
import re

from openai import AsyncOpenAI

from config import DEEPSEEK_BASE_URL, DEFAULT_MODEL
from folders import folder_map
from route_cache import (
    route_cache_get,
    route_cache_put,
    route_cache_stats,
)
from safe_strings import safe_exception_message

log = logging.getLogger("rag.router")


def rule_based_route(query: str, user_id: int) -> list[str] | None:
    """基于关键词的快速路由。未命中时返回 None。"""
    catalog = folder_map(user_id)
    matched: list[str] = []
    for dept_key, dept_info in catalog.items():
        for keyword in dept_info.get("keywords", []):
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            if pattern.search(query):
                matched.append(dept_key)
                break
    return matched or None


async def llm_based_route(query: str, api_key: str, base_url: str, model: str, user_id: int) -> list[str]:
    """调用 DeepSeek 判断部门。失败时回退到全部部门。"""
    catalog = folder_map(user_id)
    if not catalog:
        return []
    descriptions = "\n".join(
        f"- {key}: {info['name']}，{info['description']}" for key, info in catalog.items()
    )
    keys = list(catalog.keys())
    system_prompt = f"""你是一个知识库路由助手。请根据用户的问题，判断该问题应该查询哪些文件夹。

可选的文件夹：
{descriptions}

规则：
1. 如果问题明确属于某个文件夹，返回该文件夹的 key。
2. 如果问题涉及多个文件夹，返回多个 key。
3. 如果无法判断，返回所有文件夹的 key。
4. 你必须只返回一个 JSON 对象，格式为：{{"departments": ["key1", "key2"]}}，不要返回其他任何内容。

无法判断时返回：{{"departments": {json.dumps(keys, ensure_ascii=False)}}}
"""
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or DEEPSEEK_BASE_URL,
            max_retries=0,
            timeout=30,
        )
        response = await client.chat.completions.create(
            model=model or DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        departments = result.get("departments", [])
        valid = [item for item in departments if item in catalog]
        return valid or list(catalog.keys())
    except Exception as exc:  # noqa: BLE001
        # 完整堆栈进日志,前端完全看不到内部异常
        log.exception("LLM 路由失败 user=%s", user_id)
        log.debug("LLM 路由原始异常: %s", safe_exception_message(exc, secret=api_key))
        return list(catalog.keys())


async def route_query(query: str, api_key: str, base_url: str, model: str, user_id: int) -> tuple[list[str], str]:
    """先规则，未命中再调用 LLM。返回 (部门列表, rule|llm)。

    LLM 结果走 5 分钟 TTL 缓存 — 同一 query 在窗口内复用,
    避免每个用户每个问题都触发一次外部 LLM 调用。
    """
    # 0) 先查缓存(规则命中本身已是无副作用,这里只缓存 LLM 路径)
    cached = route_cache_get(user_id, query)
    if cached is not None:
        log.debug("路由缓存命中 user=%s query=%r → %s", user_id, query[:80], cached[0])
        return cached

    # 1) 关键词规则
    rule_result = rule_based_route(query, user_id)
    if rule_result:
        log.info("规则命中 query=%r → %s", query[:80], rule_result)
        result = (rule_result, "rule")
        # 规则结果也缓存(规则很快,但免去重复编译正则)
        route_cache_put(user_id, query, result)
        return result

    # 2) LLM 兜底
    log.info("规则未命中,调用 LLM 兜底 query=%r", query[:80])
    llm_result = await llm_based_route(query, api_key, base_url, model, user_id)
    log.info("LLM 路由结果 query=%r → %s", query[:80], llm_result)
    result = (llm_result, "llm")
    route_cache_put(user_id, query, result)
    log.debug("路由缓存状态: %s", route_cache_stats())
    return result
