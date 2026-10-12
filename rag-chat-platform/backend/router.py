import json
import re

from openai import AsyncOpenAI

from config import DEEPSEEK_BASE_URL, DEFAULT_MODEL
from folders import folder_map


def rule_based_route(query: str) -> list[str] | None:
    """基于关键词的快速路由。未命中时返回 None。"""
    catalog = folder_map()
    matched: list[str] = []
    for dept_key, dept_info in catalog.items():
        for keyword in dept_info.get("keywords", []):
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            if pattern.search(query):
                matched.append(dept_key)
                break
    return matched or None


def _safe_error(exc: Exception, api_key: str) -> str:
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "***")
    return text[:300]


async def llm_based_route(query: str, api_key: str, base_url: str, model: str) -> list[str]:
    """调用 DeepSeek 判断部门。失败时回退到全部部门。"""
    catalog = folder_map()
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
    except Exception as exc:
        print(f"[WARN] LLM 路由失败: {_safe_error(exc, api_key)}，回退到全部文件夹")
        return list(catalog.keys())


async def route_query(query: str, api_key: str, base_url: str, model: str) -> tuple[list[str], str]:
    """先规则，未命中再调用 LLM。返回 (部门列表, rule|llm)。"""
    rule_result = rule_based_route(query)
    if rule_result:
        print(f"[ROUTER] 规则命中: {rule_result}")
        return rule_result, "rule"

    print("[ROUTER] 规则未命中，调用 LLM 兜底...")
    llm_result = await llm_based_route(query, api_key, base_url, model)
    print(f"[ROUTER] LLM 路由结果: {llm_result}")
    return llm_result, "llm"
