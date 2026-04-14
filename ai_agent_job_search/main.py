import json
import os
from typing import Any, Dict, List, Optional, Set

import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from agent import info_extraction_tool, job_search_tool

load_dotenv()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-ai/DeepSeek-V2.5")

TARGET_JOBS = 50
MAX_ITERATIONS = 20


def is_auth_401_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "401" in msg or "unauthorized" in msg


def generate_next_query(
    llm: ChatOpenAI, valid_jobs_count: int, used_queries: List[str]
) -> Optional[str]:
    """Use LLM as planning brain to generate a fresh search query."""
    prompt = f"""
你是一个招聘岗位搜索策略规划器。
目标：收集 AI Engineer 相关的校招/实习岗位。
当前已收集数量：{valid_jobs_count}
已使用关键词：{used_queries if used_queries else "无"}

请生成 1 条新的中文搜索关键词，要求：
1) 不能与已使用关键词重复。
2) 聚焦 AI Engineer / LLM / NLP / CV / 机器学习 相关校招或实习岗位。
3) 输出仅为关键词本身，不要解释，不要编号，不要引号。
""".strip()

    try:
        response = llm.invoke(prompt).content
        if isinstance(response, list):
            response = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in response
            )
        query = str(response).strip().strip('"').strip("'")

        if not query or query in used_queries:
            return None
        return query
    except Exception as exc:
        if is_auth_401_error(exc):
            raise RuntimeError(
                "LLM authentication failed with 401 while generating query. "
                "Please verify OPENAI_API_KEY / MODEL_NAME / LLM_BASE_URL."
            ) from exc
        print(f"[WARN] 关键词生成失败: {exc}")
        return None


def parse_search_results(search_output: str) -> List[Dict[str, Any]]:
    """Safely parse search tool output."""
    try:
        payload = json.loads(search_output)
        if not isinstance(payload, dict):
            return []
        if payload.get("error"):
            print(f"[WARN] 搜索工具报错: {payload.get('message', 'unknown error')}")
            return []
        results = payload.get("results", [])
        return results if isinstance(results, list) else []
    except Exception as exc:
        print(f"[WARN] 解析搜索结果失败: {exc}")
        return []


def build_dedup_key(job: Dict[str, Any]) -> str:
    """Deduplicate by job_url first, fallback to company+title."""
    job_url = str(job.get("job_url", "")).strip()
    if job_url:
        return f"url::{job_url}"
    company = str(job.get("company", "")).strip().lower()
    title = str(job.get("title", "")).strip().lower()
    return f"ct::{company}::{title}"


def main() -> None:
    llm_brain = ChatOpenAI(
        model=MODEL_NAME,
        base_url=LLM_BASE_URL,
        temperature=0.2,
    )
    valid_jobs: List[Dict[str, Any]] = []
    used_queries: List[str] = []
    seen_keys: Set[str] = set()

    iteration = 0
    while len(valid_jobs) < TARGET_JOBS and iteration < MAX_ITERATIONS:
        iteration += 1
        print(f"\n--- 迭代 {iteration}/{MAX_ITERATIONS} ---")

        query = generate_next_query(llm_brain, len(valid_jobs), used_queries)
        if not query:
            print("[WARN] 本轮未获得新关键词，跳过。")
            continue
        used_queries.append(query)
        print(f"[INFO] 使用关键词: {query}")

        try:
            search_output = job_search_tool.invoke({"search_query": query})
        except Exception as exc:
            print(f"[WARN] 调用 job_search_tool 失败: {exc}")
            continue

        results = parse_search_results(search_output)
        if not results:
            print("[INFO] 未获得有效搜索结果。")
            continue

        # Batch multiple search snippets into a single extraction call.
        batch_text = "\n\n".join(
            [
                (
                    f"岗位{i + 1}:\n"
                    f"标题: {item.get('title', '')}\n"
                    f"内容: {item.get('content', '')}\n"
                    f"来源: {item.get('source', '')}\n"
                    f"链接: {item.get('url', '')}"
                )
                for i, item in enumerate(results)
            ]
        )

        try:
            extracted_jobs = info_extraction_tool.invoke({"raw_job_text": batch_text})
        except Exception as exc:
            if is_auth_401_error(exc):
                raise RuntimeError(
                    "LLM authentication failed with 401 while extracting job info. "
                    "Program terminated to avoid invalid retries."
                ) from exc
            print(f"[WARN] 调用 info_extraction_tool 失败: {exc}")
            continue

        if not extracted_jobs or not isinstance(extracted_jobs, list):
            print(f"当前找到 {len(valid_jobs)}/{TARGET_JOBS} 个岗位")
            continue

        for extracted in extracted_jobs:
            if not isinstance(extracted, dict):
                continue
            if not extracted.get("salary"):
                extracted["salary"] = "面议"

            dedup_key = build_dedup_key(extracted)
            if dedup_key in seen_keys:
                continue

            seen_keys.add(dedup_key)
            valid_jobs.append(extracted)
            if len(valid_jobs) >= TARGET_JOBS:
                break

        print(f"当前找到 {len(valid_jobs)}/{TARGET_JOBS} 个岗位")

    if iteration >= MAX_ITERATIONS and len(valid_jobs) < TARGET_JOBS:
        print(
            f"[INFO] 达到最大迭代次数 {MAX_ITERATIONS}，提前结束。当前收集 {len(valid_jobs)} 条。"
        )

    with open("ai_jobs.json", "w", encoding="utf-8") as f:
        json.dump(valid_jobs, f, ensure_ascii=False, indent=2)

    df = pd.DataFrame(valid_jobs)
    df.to_csv("ai_jobs.csv", index=False, encoding="utf-8-sig")

    print("[DONE] 已导出: ai_jobs.json, ai_jobs.csv")


if __name__ == "__main__":
    main()
