import ast
from pathlib import Path

import pandas as pd
import streamlit as st

CSV_PATH = Path("ai_jobs.csv")


def parse_tags(value: object) -> list[str]:
    if pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return [str(tag).strip() for tag in parsed if str(tag).strip()]
    except (ValueError, SyntaxError):
        pass
    return [item.strip() for item in text.split(",") if item.strip()]


@st.cache_data
def load_data() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame(
            columns=[
                "title",
                "company",
                "location",
                "salary",
                "tech_tags",
                "requirements",
                "source",
                "job_url",
            ]
        )

    df = pd.read_csv(CSV_PATH)
    for col in ["title", "company", "location", "salary", "requirements", "source", "job_url"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("")

    if "tech_tags" not in df.columns:
        df["tech_tags"] = ""
    df["parsed_tags"] = df["tech_tags"].apply(parse_tags)
    return df


def filter_data(df: pd.DataFrame, company_keyword: str, selected_tags: list[str]) -> pd.DataFrame:
    filtered = df.copy()

    if company_keyword:
        filtered = filtered[
            filtered["company"].astype(str).str.contains(company_keyword, case=False, na=False)
        ]

    if selected_tags:
        filtered = filtered[
            filtered["parsed_tags"].apply(lambda tags: any(tag in tags for tag in selected_tags))
        ]

    return filtered


def build_tag_stats(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame({"tech_tag": [], "count": []})

    exploded = df["parsed_tags"].explode()
    exploded = exploded.dropna()
    exploded = exploded[exploded.astype(str).str.strip() != ""]
    if exploded.empty:
        return pd.DataFrame({"tech_tag": [], "count": []})

    tag_stats = exploded.value_counts().head(10).reset_index()
    tag_stats.columns = ["tech_tag", "count"]
    return tag_stats


st.set_page_config(page_title="AI Agent 求职助手数据看板", layout="wide")
st.title("AI Agent 求职助手数据看板")

data = load_data()
all_tags = sorted({tag for tags in data.get("parsed_tags", pd.Series(dtype=object)) for tag in tags})

with st.sidebar:
    st.header("筛选条件")
    company_keyword = st.text_input("公司名称搜索", placeholder="输入公司关键词")
    selected_tags = st.multiselect("技术标签筛选", options=all_tags)

filtered_data = filter_data(data, company_keyword, selected_tags)
tag_stats = build_tag_stats(filtered_data)

metric_col, = st.columns(1)
metric_col.metric("当前岗位总数", len(filtered_data))

st.subheader("Top 10 技术栈频次")
if tag_stats.empty:
    st.info("当前筛选条件下暂无可展示的技术标签数据。")
else:
    st.bar_chart(tag_stats.set_index("tech_tag")["count"])

st.subheader("岗位明细")
display_df = filtered_data.drop(columns=["parsed_tags"], errors="ignore")
st.dataframe(display_df, use_container_width=True, hide_index=True)
