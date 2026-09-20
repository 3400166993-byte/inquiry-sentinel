from __future__ import annotations

import re
from dataclasses import fields
from typing import Any

from .models import DocumentContext, FinancialSnapshot

try:
    import pymupdf as fitz  # PyMuPDF 1.24+
except Exception:
    try:
        import fitz  # Older PyMuPDF releases.
    except Exception:  # pragma: no cover - Streamlit will show a user-facing error.
        fitz = None

PDF_SUPPORT_AVAILABLE = fitz is not None


MONEY_KEYWORDS = {
    "revenue": ["营业收入", "主营业务收入", "收入合计"],
    "net_profit": ["归属于上市公司股东的净利润", "净利润"],
    "cfo": ["经营活动产生的现金流量净额", "经营活动现金流量净额", "经营现金流"],
    "receivables": ["应收账款", "应收款项"],
    "inventory": ["存货"],
}

PERCENT_KEYWORDS = {
    "revenue_yoy": ["营业收入同比", "收入同比", "营业收入增长率", "营业收入"],
    "net_profit_yoy": ["净利润同比", "净利润增长率", "净利润"],
    "cfo_yoy": ["经营现金流同比", "经营活动现金流量净额同比", "经营活动产生的现金流量净额"],
    "receivables_yoy": ["应收账款同比", "应收账款增长率", "应收账款"],
    "inventory_yoy": ["存货同比", "存货增长率", "存货"],
    "gross_margin": ["毛利率", "综合毛利率"],
    "gross_margin_change": ["毛利率变动", "毛利率下降", "毛利率上升"],
    "related_party_ratio": ["关联交易占比", "关联销售占比"],
    "top5_customer_ratio": ["前五大客户", "前五名客户"],
    "asset_impairment_ratio": ["资产减值损失占比", "减值损失占比"],
    "goodwill_ratio": ["商誉占比"],
    "guarantee_ratio": ["担保余额占比", "对外担保占比"],
    "debt_ratio": ["资产负债率"],
}


def extract_text_from_pdf_bytes(data: bytes, source_name: str) -> DocumentContext:
    if fitz is None:
        raise RuntimeError("当前环境未安装 PyMuPDF，请先执行 pip install -r requirements.txt。")

    document = fitz.open(stream=data, filetype="pdf")
    pages: list[str] = []
    for page in document:
        pages.append(page.get_text("text"))

    text = "\n".join(pages)
    return DocumentContext(
        source_name=source_name,
        extracted_text=text,
        page_count=document.page_count,
        summary=build_document_summary(text),
        page_texts=pages,
    )


def extract_text_from_txt_bytes(data: bytes, source_name: str) -> DocumentContext:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="ignore")

    return DocumentContext(
        source_name=source_name,
        extracted_text=text,
        page_count=1,
        summary=build_document_summary(text),
        page_texts=[text],
    )


def build_document_summary(text: str, max_chars: int = 800) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + "..."


def normalize_pdf_text(text: str) -> str:
    """把 PDF 文本中的换行和分散空格压平，便于识别表格里的中文指标。"""
    return re.sub(r"\s+", "", text or "")


def _normalize_number(raw: str, unit: str | None = None) -> float | None:
    cleaned = raw.replace(",", "").replace("，", "").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if unit == "万":
        value *= 10_000
    elif unit == "亿":
        value *= 100_000_000
    return value


def _numbers_near_keyword(text: str, keyword: str, window: int = 90) -> list[tuple[float, str]]:
    results: list[tuple[float, str]] = []
    compact_text = normalize_pdf_text(text)
    compact_keyword = normalize_pdf_text(keyword)
    pattern = re.compile(re.escape(compact_keyword))
    number_pattern = re.compile(
        r"([-+]?\d{1,3}(?:[,，]\d{3})+|[-+]?\d+(?:\.\d+)?)(?:\s*)(亿|万)?(?:元)?"
    )
    for match in pattern.finditer(compact_text):
        snippet = compact_text[match.start() : match.end() + window]
        for num_match in number_pattern.finditer(snippet):
            raw = num_match.group(1)
            unit = num_match.group(2)
            after = snippet[num_match.end() : num_match.end() + 8]
            value = _normalize_number(raw, unit)
            if value is None:
                continue
            # 年份和页码很容易混入抽取结果，这里做一个轻量过滤。
            if 1900 <= value <= 2100 and unit is None:
                continue
            # 同比百分比不是金额候选，避免把 12.8% 当成当前期数值。
            if "%" in after or "个百分点" in after:
                continue
            results.append((value, snippet.strip()))
        if results:
            break
    return results


def _percent_near_keyword(text: str, keyword: str, window: int = 100) -> tuple[float, str] | None:
    compact_text = normalize_pdf_text(text)
    compact_keyword = normalize_pdf_text(keyword)
    pattern = re.compile(re.escape(compact_keyword))
    percent_pattern = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(?:个百分点|%)")
    for match in pattern.finditer(compact_text):
        snippet = compact_text[match.start() : match.end() + window]
        pct_match = percent_pattern.search(snippet)
        if pct_match:
            value = float(pct_match.group(1))
            context = snippet[max(0, pct_match.start() - 24) : pct_match.start()]
            if any(word in context for word in ("下降", "减少", "下滑", "负增长", "减幅", "降幅")):
                value = -abs(value)
            return value, snippet.strip()
    return None


def _parse_summary_cell(line: str) -> tuple[float | None, bool]:
    """解析摘要表格中的单元格，第二个返回值表示该行是否是可识别的表格单元格。"""
    cleaned = re.sub(r"\s+", "", line or "").strip()
    if not cleaned:
        return None, False
    if "不适用" in cleaned or cleaned in {"--", "-", "无"}:
        return None, True

    number_pattern = re.compile(r"[-+−]?(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?")
    match = number_pattern.search(cleaned)
    if not match:
        return None, False

    raw = match.group(0).replace("−", "-")
    try:
        value = float(raw.replace(",", "").replace("，", ""))
    except ValueError:
        return None, False

    context = cleaned[: match.start()]
    if any(word in context for word in ("减少", "下降", "下滑", "降低", "减幅", "降幅")):
        value = -abs(value)
    if cleaned.startswith(("(", "（")) and cleaned.endswith((")", "）")):
        value = -abs(value)
    return value, True


def _extract_summary_rows(text: str) -> dict[str, dict[str, object]]:
    """读取上交所摘要常见的“本期/上期/增减%”纵向表格。"""
    lines = [re.sub(r"\s+", "", line) for line in (text or "").splitlines() if line.strip()]
    row_labels = {
        "revenue": ["营业收入"],
        "net_profit": ["归属于上市公司股东的净利润"],
        "cfo": ["经营活动产生的现金流量净额"],
    }
    all_labels = [label for labels in row_labels.values() for label in labels]
    rows: dict[str, dict[str, object]] = {}

    for field_name, labels in row_labels.items():
        for start in range(len(lines)):
            matched_span = 0
            for span in range(1, 4):
                candidate = "".join(lines[start : start + span])
                if any(label in candidate for label in labels):
                    matched_span = span
                    break
            if not matched_span:
                continue

            cells: list[float | None] = []
            raw_cells: list[str] = []
            for current in lines[start + matched_span : min(len(lines), start + matched_span + 6)]:
                if len(cells) >= 3:
                    break
                current_compact = re.sub(r"\s+", "", current)
                if any(label in current_compact for label in all_labels):
                    break
                value, recognized = _parse_summary_cell(current)
                if not recognized:
                    continue
                cells.append(value)
                raw_cells.append(current)

            if len(cells) >= 2:
                rows[field_name] = {
                    "current": cells[0],
                    "prior": cells[1],
                    "yoy": cells[2] if len(cells) >= 3 else None,
                    "raw": " / ".join(raw_cells),
                }
                break
    return rows


def infer_company_name(text: str, fallback: str = "待分析公司") -> str:
    patterns = [
        r"公司中文名称[:：\s]+([^\n\r]{4,40})",
        r"公司名称[:：\s]+([^\n\r]{4,40})",
        r"([一-龥A-Za-z0-9（）()]{4,40}(?:股份有限公司|有限责任公司|集团有限公司))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = re.sub(r"\s+", "", match.group(1)).strip("：: ")
            if 4 <= len(value) <= 50:
                return value
    return fallback


def infer_report_period(text: str, fallback: str = "年度报告") -> str:
    patterns = [
        r"(20\d{2})\s*年\s*(半年度报告|半年度报告摘要|年度报告|年度报告摘要)",
        r"(20\d{2})\s*(半年度报告|半年度报告摘要|年度报告|年度报告摘要)",
        r"(20\d{2})\s*年报",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            suffix = match.group(2) if match.lastindex and match.lastindex >= 2 else "年度报告"
            return f"{match.group(1)}年" + ("半年度" if "半年度" in suffix else "年度")
    return fallback


def extract_snapshot_from_text(text: str, source_name: str = "") -> tuple[FinancialSnapshot, list[str]]:
    snapshot = FinancialSnapshot(
        company_name=infer_company_name(text),
        report_period=infer_report_period(text),
        notes=f"来源文件：{source_name}" if source_name else "",
    )
    evidence_notes: list[str] = []

    extracted_money: dict[str, list[tuple[float, str]]] = {}
    for field_name, keywords in MONEY_KEYWORDS.items():
        for keyword in keywords:
            found = _numbers_near_keyword(text, keyword)
            if found:
                extracted_money[field_name] = found
                value, snippet = found[0]
                setattr(snapshot, field_name, value)
                evidence_notes.append(f"{field_name}: {snippet[:160]}")
                break

    summary_rows = _extract_summary_rows(text)
    summary_yoy_fields: set[str] = set()
    for field_name, row in summary_rows.items():
        current = row.get("current")
        yoy = row.get("yoy")
        if isinstance(current, (int, float)):
            setattr(snapshot, field_name, float(current))
        yoy_field = {
            "revenue": "revenue_yoy",
            "net_profit": "net_profit_yoy",
            "cfo": "cfo_yoy",
        }.get(field_name)
        if yoy_field:
            summary_yoy_fields.add(yoy_field)
        if yoy_field and isinstance(yoy, (int, float)):
            setattr(snapshot, yoy_field, float(yoy))
        evidence_notes.append(f"{field_name}表格行: {row.get('raw', '')}")

    for field_name, keywords in PERCENT_KEYWORDS.items():
        if getattr(snapshot, field_name, None) is not None:
            continue
        # 表格明确给出“不适用”时，不允许从下一行的百分比变化回退取值。
        if field_name in summary_yoy_fields:
            continue
        for keyword in keywords:
            found = _percent_near_keyword(text, keyword)
            if found:
                value, snippet = found
                setattr(snapshot, field_name, value)
                evidence_notes.append(f"{field_name}: {snippet[:160]}")
                break

    # 年报表格有时不直接写“同比”，只给当前期和上期金额，这里补算同比。
    yoy_pairs = {
        "revenue": "revenue_yoy",
        "net_profit": "net_profit_yoy",
        "cfo": "cfo_yoy",
        "receivables": "receivables_yoy",
        "inventory": "inventory_yoy",
    }
    for money_field, yoy_field in yoy_pairs.items():
        if getattr(snapshot, yoy_field) is not None:
            continue
        candidates = extracted_money.get(money_field, [])
        if len(candidates) < 2:
            continue
        current, prior = candidates[0][0], candidates[1][0]
        if prior == 0:
            continue
        yoy = (current - prior) / abs(prior) * 100
        if -1000 <= yoy <= 1000:
            setattr(snapshot, yoy_field, round(yoy, 2))
            evidence_notes.append(f"{yoy_field}: 根据当前期和上期金额计算得到 {yoy:.2f}%")

    if snapshot.gross_margin_change is not None:
        # “下降 5 个百分点”在正则中会抽成正数，这里结合上下文修正方向。
        lower_context = text[:3000]
        if "毛利率下降" in lower_context and snapshot.gross_margin_change > 0:
            snapshot.gross_margin_change *= -1

    return snapshot, evidence_notes


def update_snapshot_from_dict(snapshot: FinancialSnapshot, updates: dict[str, Any]) -> FinancialSnapshot:
    allowed = {field.name for field in fields(FinancialSnapshot)}
    for key, value in updates.items():
        if key not in allowed:
            continue
        if value == "":
            value = None
        setattr(snapshot, key, value)
    return snapshot
