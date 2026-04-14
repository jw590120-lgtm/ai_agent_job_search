import json
import os
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

load_dotenv()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-ai/DeepSeek-V2.5")
MAX_CONTENT_LENGTH = 1000
MAX_LLM_INPUT_LENGTH = 6000
LLM_TIMEOUT_SECONDS = 30

REQUIRED_JOB_FIELDS = [
    "title",
    "company",
    "location",
    "salary",
    "tech_tags",
    "requirements",
    "source",
    "job_url",
]


def _extract_json_block(raw_text: str) -> Optional[str]:
    """Extract JSON array/object from model output."""
    content = raw_text.strip()

    block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL)
    if block_match:
        content = block_match.group(1).strip()

    if content == "[]":
        return content

    first_bracket = content.find("[")
    last_bracket = content.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        return content[first_bracket : last_bracket + 1]

    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return content[first_brace : last_brace + 1]
    return None


def _normalize_job_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and validate extracted job JSON."""
    normalized = {key: payload.get(key) for key in REQUIRED_JOB_FIELDS}
    if not isinstance(normalized["tech_tags"], list):
        normalized["tech_tags"] = []
    normalized["salary"] = normalized["salary"] or "面议"
    return normalized


def _is_auth_401_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "401" in msg or "unauthorized" in msg


def _clean_search_content(content: str) -> str:
    """Trim noisy/overlong snippets before LLM extraction."""
    if not content:
        return ""
    cleaned = " ".join(str(content).split())
    return cleaned[:MAX_CONTENT_LENGTH]


@tool
def job_search_tool(search_query: str) -> str:
    """
    Search AI internship/campus job information via Tavily.

    Args:
        search_query: Query string, e.g. "AI Engineer 实习 生 北京".

    Returns:
        A JSON string containing a list of search results.
    """
    try:
        tavily_client = TavilyClient()
        response = tavily_client.search(
            query=search_query,
            search_depth="basic",
            max_results=4,
            include_answer=False,
        )

        results: List[Dict[str, str]] = []
        for item in response.get("results", []):
            cleaned_content = _clean_search_content(item.get("content", ""))
            if not cleaned_content:
                continue
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": cleaned_content,
                    "source": item.get("url", ""),
                }
            )

        return json.dumps(
            {
                "search_query": search_query,
                "results": results,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "error": "job_search_tool_failed",
                "message": str(exc),
                "search_query": search_query,
            },
            ensure_ascii=False,
        )


@tool
def info_extraction_tool(raw_job_text: str) -> List[Dict[str, Any]]:
    """
    Extract structured job information from unstructured text batch.

    Return a JSON-like list of jobs. If no qualified jobs, returns [].
    """
    try:
        raw_job_text = raw_job_text[:MAX_LLM_INPUT_LENGTH]
        llm = ChatOpenAI(
            model=MODEL_NAME,
            base_url=LLM_BASE_URL,
            temperature=0,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        prompt = f"""
你是一个招聘信息结构化解析器。请根据输入文本严格输出 JSON 数组，且只能输出 JSON 数组，不要输出额外说明。

规则：
1) 输入中可能包含多条岗位文本，你需要提取所有符合条件的岗位并组成 JSON 数组。
2) 仅当岗位属于 AI Engineer / 算法工程师 / 机器学习 / 大模型 / 计算机视觉 / 自然语言处理 相关的校招或实习岗位时，才保留。
3) 若没有任何符合条件的岗位，返回 []。
4) 数组中每个对象必须包含并仅包含以下字段：
   - title: 职位名称
   - company: 公司名称
   - location: 工作地点
   - salary: 薪资范围（若未知填 "面议"）
   - tech_tags: 技术关键词数组（如 ["LLM", "CV"]）
   - requirements: 核心技能摘要（简洁字符串）
   - source: 招聘网站
   - job_url: 岗位链接
5) 字段缺失时尽量从上下文推断；不能推断时用空字符串，salary 例外必须为 "面议"。
6) 输出示例（仅示例）：
[{{"title":"AI Engineer Intern","company":"某科技公司","location":"北京","salary":"面议","tech_tags":["LLM"],"requirements":"熟悉 Python 与深度学习框架","source":"某招聘网站","job_url":"https://example.com/job/1"}}]

待解析文本：
{raw_job_text}
""".strip()

        raw_response = llm.invoke(prompt).content
        if isinstance(raw_response, list):
            raw_response = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in raw_response
            )
        raw_response = str(raw_response).strip()

        json_block = _extract_json_block(raw_response)
        if not json_block:
            return []
        if json_block == "[]":
            return []

        payload = json.loads(json_block)
        if payload is None:
            return []

        # Backward compatibility: if model accidentally returns a single object.
        if isinstance(payload, dict):
            return [_normalize_job_payload(payload)]
        if not isinstance(payload, list):
            return []

        normalized_jobs: List[Dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                normalized_jobs.append(_normalize_job_payload(item))
        return normalized_jobs
    except Exception as exc:
        if _is_auth_401_error(exc):
            raise RuntimeError(
                "LLM authentication failed with 401 in info_extraction_tool. "
                "Please verify OPENAI_API_KEY / MODEL_NAME / LLM_BASE_URL."
            ) from exc
        return []
