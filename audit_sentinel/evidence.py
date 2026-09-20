from __future__ import annotations

import re

from .models import DocumentContext, EvidenceReference, FinancialSnapshot, RiskFinding


RISK_TERMS: dict[str, list[str]] = {
    "cashflow_mismatch": [
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
        "经营现金流",
        "销售商品、提供劳务收到的现金",
    ],
    "receivables_growth": ["应收账款", "坏账准备", "账龄", "期后回款"],
    "inventory_pressure": ["存货", "存货跌价准备", "库龄", "存货周转"],
    "margin_volatility": ["毛利率", "主营业务毛利率", "营业成本"],
    "related_party": ["关联交易", "关联方", "前五大客户", "对外担保"],
    "impairment_goodwill": ["资产减值", "商誉", "减值测试", "可收回金额"],
    "guarantee": ["对外担保", "担保余额", "或有负债", "被担保方"],
}


def _snippet(page_text: str, position: int, radius: int = 115) -> str:
    start = max(0, position - radius)
    end = min(len(page_text), position + radius)
    cleaned = re.sub(r"\s+", " ", page_text[start:end]).strip()
    if start > 0:
        cleaned = "…" + cleaned
    if end < len(page_text):
        cleaned += "…"
    return cleaned


def _metric_reference(snapshot: FinancialSnapshot, finding: RiskFinding, source: str) -> EvidenceReference:
    return EvidenceReference(
        label="指标复核表",
        quote="；".join(finding.evidence),
        source=source or "核心指标复核表",
        confidence="中",
    )


def build_evidence_references(
    finding: RiskFinding,
    snapshot: FinancialSnapshot,
    document: DocumentContext,
) -> list[EvidenceReference]:
    """把风险规则绑定到原文页码；找不到原文时保留指标复核证据。"""
    references: list[EvidenceReference] = []
    terms = RISK_TERMS.get(finding.risk_id, [])
    pages = document.page_texts or ([document.extracted_text] if document.extracted_text else [])
    for page_number, page_text in enumerate(pages, start=1):
        for term in terms:
            position = page_text.find(term)
            if position < 0:
                continue
            references.append(
                EvidenceReference(
                    label="年报原文",
                    quote=_snippet(page_text, position),
                    source=document.source_name,
                    page=page_number if document.page_count > 1 else None,
                    confidence="待核验",
                )
            )
            break
        if len(references) >= 2:
            break

    metric_reference = _metric_reference(snapshot, finding, document.source_name)
    if not references:
        references.append(metric_reference)
    elif finding.evidence:
        references.append(metric_reference)
    return references
