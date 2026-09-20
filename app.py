from __future__ import annotations

import math
from dataclasses import fields
from typing import Any

import pandas as pd
import streamlit as st

from audit_sentinel.agents import run_analysis
from audit_sentinel.case_library import build_default_case_library, load_case_library_from_file
from audit_sentinel.llm_client import LLMSettings, default_settings
from audit_sentinel.models import DocumentContext, FinancialSnapshot
from audit_sentinel.pdf_tools import PDF_SUPPORT_AVAILABLE, extract_snapshot_from_text, extract_text_from_pdf_bytes, extract_text_from_txt_bytes
from audit_sentinel.reporting import (
    REPORTLAB_AVAILABLE,
    diagnostics_to_frame,
    findings_to_frame,
    result_to_csv_bytes,
    result_to_json_bytes,
    result_to_markdown_bytes,
    result_to_pdf_bytes,
)
from audit_sentinel.sample_data import DEMO_SCENARIOS


st.set_page_config(
    page_title="问询前哨",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    .metric-card {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 12px 14px;
        background: #ffffff;
    }
    .risk-high {color: #b91c1c; font-weight: 700;}
    .risk-mid {color: #b45309; font-weight: 700;}
    .risk-low {color: #166534; font-weight: 700;}
    .subtle {color: #6b7280; font-size: 0.92rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


NUMERIC_FIELDS = {
    "revenue",
    "revenue_yoy",
    "net_profit",
    "net_profit_yoy",
    "cfo",
    "cfo_yoy",
    "receivables",
    "receivables_yoy",
    "inventory",
    "inventory_yoy",
    "gross_margin",
    "gross_margin_change",
    "related_party_ratio",
    "top5_customer_ratio",
    "asset_impairment_ratio",
    "goodwill_ratio",
    "guarantee_ratio",
    "debt_ratio",
}

FIELD_LABELS = {
    "company_name": "公司名称",
    "industry": "行业",
    "report_period": "报告期",
    "currency_unit": "货币单位",
    "revenue": "营业收入",
    "revenue_yoy": "营业收入同比%",
    "net_profit": "净利润",
    "net_profit_yoy": "净利润同比%",
    "cfo": "经营现金流净额",
    "cfo_yoy": "经营现金流同比%",
    "receivables": "应收账款",
    "receivables_yoy": "应收账款同比%",
    "inventory": "存货",
    "inventory_yoy": "存货同比%",
    "gross_margin": "毛利率%",
    "gross_margin_change": "毛利率变动百分点",
    "related_party_ratio": "关联交易占比%",
    "top5_customer_ratio": "前五大客户占比%",
    "asset_impairment_ratio": "资产减值占比%",
    "goodwill_ratio": "商誉占比%",
    "guarantee_ratio": "担保余额占比%",
    "debt_ratio": "资产负债率%",
    "notes": "备注",
}


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def snapshot_to_editor_frame(snapshot: FinancialSnapshot) -> pd.DataFrame:
    row: dict[str, Any] = {}
    for field in fields(FinancialSnapshot):
        row[FIELD_LABELS.get(field.name, field.name)] = getattr(snapshot, field.name)
    return pd.DataFrame([row])


def editor_frame_to_snapshot(frame: pd.DataFrame) -> FinancialSnapshot:
    reverse_labels = {label: key for key, label in FIELD_LABELS.items()}
    row = frame.iloc[0].to_dict()
    payload: dict[str, Any] = {}
    for label, value in row.items():
        key = reverse_labels.get(label, label)
        value = _clean_value(value)
        if key in NUMERIC_FIELDS and value is not None:
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = None
        payload[key] = value
    for field in fields(FinancialSnapshot):
        payload.setdefault(field.name, None if field.name in NUMERIC_FIELDS else "")
    payload["company_name"] = payload.get("company_name") or "待分析公司"
    payload["industry"] = payload.get("industry") or "未识别行业"
    payload["report_period"] = payload.get("report_period") or "年度报告"
    payload["currency_unit"] = payload.get("currency_unit") or "元"
    payload["notes"] = payload.get("notes") or ""
    return FinancialSnapshot(**payload)


def parse_uploaded_document(uploaded_file) -> tuple[DocumentContext, FinancialSnapshot, list[str]]:
    file_name = uploaded_file.name
    data = uploaded_file.getvalue()
    suffix = file_name.lower().split(".")[-1]
    if suffix == "pdf":
        document = extract_text_from_pdf_bytes(data, file_name)
    elif suffix in {"txt", "md"}:
        document = extract_text_from_txt_bytes(data, file_name)
    else:
        raise ValueError("仅支持 PDF、TXT 或 Markdown 文件。")
    if not document.extracted_text.strip():
        raise ValueError("文件中没有可提取的文本，可能是扫描图片版 PDF。请换用可复制文字的年报 PDF。")
    snapshot, notes = extract_snapshot_from_text(document.extracted_text, file_name)
    return document, snapshot, notes


def severity_class(severity: str) -> str:
    if severity == "高":
        return "risk-high"
    if severity == "中":
        return "risk-mid"
    return "risk-low"


def render_model_settings() -> LLMSettings:
    provider = st.sidebar.selectbox("模型服务", ["演示模式", "DeepSeek", "通义千问", "自定义兼容接口"], index=0)
    settings = default_settings(provider)

    if provider != "演示模式":
        visitor_key = st.sidebar.text_input("API Key", type="password", key=f"api_key_{provider}").strip()
        if settings.api_key and not visitor_key:
            # Server credentials must stay private and use the configured endpoint.
            st.sidebar.caption(f"已使用服务器配置的模型：{settings.model}")
        else:
            settings.api_key = visitor_key
            settings.base_url = st.sidebar.text_input("Base URL", value=settings.base_url, key=f"base_url_{provider}")
            settings.model = st.sidebar.text_input("模型名称", value=settings.model, key=f"model_{provider}")
        settings.temperature = st.sidebar.slider("生成温度", min_value=0.0, max_value=1.0, value=0.2, step=0.05)
        settings.timeout = st.sidebar.slider("请求超时秒数", min_value=10, max_value=120, value=45, step=5)
    else:
        st.sidebar.info("演示模式使用规则引擎和本地案例库，不调用外部 API。")

    return settings


def render_downloads(result) -> None:
    safe_company = result.snapshot.company_name.replace("/", "_").replace("\\", "_")
    cols = st.columns(4)
    cols[0].download_button(
        "下载 JSON",
        data=result_to_json_bytes(result),
        file_name=f"{safe_company}_问询风险.json",
        mime="application/json",
        use_container_width=True,
    )
    cols[1].download_button(
        "下载 CSV",
        data=result_to_csv_bytes(result),
        file_name=f"{safe_company}_风险明细.csv",
        mime="text/csv",
        use_container_width=True,
    )
    cols[2].download_button(
        "下载 Markdown",
        data=result_to_markdown_bytes(result),
        file_name=f"{safe_company}_分析报告.md",
        mime="text/markdown",
        use_container_width=True,
    )
    try:
        pdf_bytes = result_to_pdf_bytes(result)
        cols[3].download_button(
            "下载 PDF",
            data=pdf_bytes,
            file_name=f"{safe_company}_分析报告.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as exc:
        cols[3].warning(f"PDF 生成失败：{exc}")


st.title("问询前哨")
st.caption("上市公司年报问询风险预警与审计程序生成系统")

settings = render_model_settings()

with st.sidebar:
    st.divider()
    st.subheader("问询案例库（可选）")
    case_library = build_default_case_library()
    case_file = st.file_uploader(
        "上传案例库 CSV / JSON",
        type=["csv", "json"],
        help="这里仅上传问询函/处罚案例库，不要上传上市公司年报 PDF。",
    )
    if case_file is not None:
        try:
            case_library = load_case_library_from_file(case_file.name, case_file.getvalue())
            st.success(f"已加载 {len(case_library)} 条案例。")
        except Exception as exc:
            st.error(f"案例库加载失败：{exc}")
            case_library = build_default_case_library()
    st.caption(f"当前案例库：{len(case_library)} 条")
    if not PDF_SUPPORT_AVAILABLE:
        st.warning("当前环境未安装 PDF 抽取增强包，PDF 上传需安装 requirements-full.txt。")
    if not REPORTLAB_AVAILABLE:
        st.warning("当前环境未安装 PDF 导出增强包，PDF 下载暂不可用。")

left, right = st.columns([0.58, 0.42], gap="large")

with left:
    st.subheader("输入数据")
    source_mode = st.radio(
        "数据来源",
        ["上传上市公司年报 PDF", "使用内置演示样例"],
        horizontal=True,
    )

    document: DocumentContext
    snapshot: FinancialSnapshot
    auto_snapshot: FinancialSnapshot
    extraction_notes: list[str] = []
    upload_error: str | None = None

    if source_mode == "上传上市公司年报 PDF":
        uploaded = st.file_uploader(
            "上传上市公司年报 PDF",
            type=["pdf", "txt", "md"],
            help="支持可复制文字的 PDF；扫描图片版 PDF 需要先 OCR。",
        )
        if uploaded is not None:
            try:
                document, snapshot, extraction_notes = parse_uploaded_document(uploaded)
                auto_snapshot = snapshot
                st.success(
                    f"已读取 {document.source_name}，页数/文本块：{document.page_count}，"
                    f"成功抽取 {snapshot.filled_fields()} 个核心字段。"
                )
            except Exception as exc:
                upload_error = str(exc)
                st.error(f"文件解析失败：{upload_error}")
                document = DocumentContext(source_name=uploaded.name, summary="")
                snapshot = FinancialSnapshot(company_name="待分析公司")
                auto_snapshot = snapshot
        else:
            demo = DEMO_SCENARIOS["应收账款与现金流背离"]
            document = DocumentContext(source_name="待上传文件（演示样例）", summary=demo["summary"])
            snapshot = demo["snapshot"]
            auto_snapshot = snapshot
            st.info("请在这里上传上市公司年报 PDF；没有文件时可切换到“使用内置演示样例”。")
    else:
        scenario_name = st.selectbox("演示场景", list(DEMO_SCENARIOS.keys()))
        demo = DEMO_SCENARIOS[scenario_name]
        document = DocumentContext(source_name=f"内置演示样例：{scenario_name}", summary=demo["summary"])
        snapshot = demo["snapshot"]
        auto_snapshot = snapshot

    st.subheader("核心指标复核")
    edited_frame = st.data_editor(
        snapshot_to_editor_frame(snapshot),
        num_rows="fixed",
        use_container_width=True,
        hide_index=True,
        key="snapshot_editor",
    )
    snapshot = editor_frame_to_snapshot(edited_frame)

    with st.expander("抽取痕迹", expanded=False):
        st.write(f"自动抽取字段数：{auto_snapshot.filled_fields()} / 18")
        if extraction_notes:
            for note in extraction_notes[:12]:
                st.write(note)
        else:
            st.write("当前没有自动抽取痕迹，可能使用的是演示样例或手工录入数据。")

with right:
    st.subheader("分析设置")
    top_k = st.slider("最多输出风险点", min_value=3, max_value=7, value=5, step=1)
    st.write("输出内容")
    st.checkbox("结构化风险表", value=True, disabled=True)
    st.checkbox("相似问询案例", value=True, disabled=True)
    st.checkbox("审计核查程序", value=True, disabled=True)
    st.checkbox("AI 生成声明", value=True, disabled=True)

    can_run = source_mode == "使用内置演示样例" or (uploaded is not None and upload_error is None)
    if st.button("开始多智能体分析", type="primary", use_container_width=True, disabled=not can_run):
        with st.spinner("正在执行：规则识别 → 案例检索 → 问询生成 → 审计复核"):
            st.session_state["analysis_result"] = run_analysis(
                snapshot=snapshot,
                document=document,
                case_library=case_library,
                settings=settings,
                top_k=top_k,
            )

    st.markdown(
        "<p class='subtle'>AI生成声明：系统输出仅用于辅助分析，不构成审计、法律或投资意见。</p>",
        unsafe_allow_html=True,
    )

result = st.session_state.get("analysis_result")

if result is None:
    st.divider()
    st.info("点击“开始多智能体分析”后展示风险结果。")
    st.stop()

st.divider()
st.subheader("风险总览")

is_summary_document = "摘要" in document.source_name or "摘要" in document.summary[:500]

if (
    source_mode == "上传上市公司年报 PDF"
    and uploaded is not None
    and upload_error is None
    and auto_snapshot.filled_fields() < 12
    and not is_summary_document
):
    st.warning(
        f"当前 PDF 文本已读取，但自动抽取到的核心字段为 {auto_snapshot.filled_fields()} / 18。"
        "风险为 0 不代表企业没有风险，可能是表格结构、扫描文字或指标命名导致抽取不足。"
        "请先在“核心指标复核”表格中补充或修正指标，再重新分析。"
    )

if (
    source_mode == "上传上市公司年报 PDF"
    and uploaded is not None
    and upload_error is None
    and is_summary_document
):
    st.info(
        f"当前上传的是公告摘要，自动抽取到 {auto_snapshot.filled_fields()} / 18 个字段。"
        "摘要通常只包含主要财务数据，不含完整附注；当前结果只覆盖摘要中可验证的风险。"
        "如需分析应收账款、存货、关联交易等项目，请上传同一报告的全文 PDF。"
    )

if (
    source_mode == "上传上市公司年报 PDF"
    and uploaded is not None
    and upload_error is None
    and not result.findings
    and auto_snapshot.filled_fields() < 12
    and not is_summary_document
):
    st.error("本次结果暂不能作为“无风险”结论，请先补充核心指标。")

high_count = sum(1 for item in result.findings if item.severity == "高")
mid_count = sum(1 for item in result.findings if item.severity == "中")
low_count = sum(1 for item in result.findings if item.severity == "低")
avg_score = sum(item.score for item in result.findings) / max(1, len(result.findings))

metrics = st.columns(4)
metrics[0].metric("风险点", len(result.findings))
metrics[1].metric("高风险", high_count)
metrics[2].metric("中风险", mid_count)
metrics[3].metric("平均风险分", f"{avg_score:.1f}")

st.write(result.summary)

tab_result, tab_cases, tab_eval, tab_export = st.tabs(["风险明细", "案例与证据", "量化评估", "导出"])

with tab_result:
    if not result.findings:
        st.success("当前指标未触发重点风险规则。")
    else:
        st.dataframe(findings_to_frame(result.findings), use_container_width=True, hide_index=True)
        for index, finding in enumerate(result.findings, start=1):
            css_class = severity_class(finding.severity)
            with st.expander(f"{index}. {finding.title}｜{finding.severity}风险｜{finding.score:.1f}分", expanded=index == 1):
                st.markdown(f"风险等级：<span class='{css_class}'>{finding.severity}</span>", unsafe_allow_html=True)
                st.write(finding.llm_summary or finding.explanation)
                st.write("核心证据")
                for item in finding.evidence:
                    st.write(f"- {item}")
                st.write("可能问询问题")
                for item in finding.llm_questions or finding.suggested_question:
                    st.write(f"- {item}")
                st.write("建议审计程序")
                for item in finding.llm_procedures or finding.suggested_procedure:
                    st.write(f"- {item}")

with tab_cases:
    for finding in result.findings:
        st.markdown(f"**{finding.title}**")
        if not finding.supporting_cases:
            st.write("未匹配到相似案例。")
            continue
        for case in finding.supporting_cases:
            st.write(f"- {case.title}｜{case.source}｜匹配度 {case.score:.1f}")
            st.caption(case.summary)

with tab_eval:
    st.dataframe(diagnostics_to_frame(result.diagnostics), use_container_width=True, hide_index=True)
    if result.findings:
        severity_frame = pd.DataFrame(
            {
                "等级": ["高", "中", "低"],
                "数量": [high_count, mid_count, low_count],
            }
        )
        st.bar_chart(severity_frame, x="等级", y="数量")

with tab_export:
    render_downloads(result)
    st.caption("导出文件均包含 AI 生成声明和结构化字段，可作为方案书、演示视频和技术报告的素材。")
