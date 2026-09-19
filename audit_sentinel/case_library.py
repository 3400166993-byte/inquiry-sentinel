from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .models import SimilarCase


DEFAULT_CASES: list[SimilarCase] = [
    SimilarCase(
        title="年报问询中关于应收账款回收风险的追问",
        source="交易所问询函公开案例",
        risk_type="应收账款",
        summary="要求说明应收账款增长原因、期后回款、坏账准备计提充分性及主要客户信用变化。",
        question="请结合客户账龄、期后回款情况和坏账政策，说明应收账款大幅增长的合理性。",
        procedure="函证主要客户，检查期后回款，复核坏账准备计提模型。",
        keywords=["应收账款", "回款", "坏账", "客户", "账龄"],
    ),
    SimilarCase(
        title="存货跌价准备与库存积压问询",
        source="交易所问询函公开案例",
        risk_type="存货",
        summary="关注存货增长、周转变慢、产品降价及跌价准备是否充分。",
        question="请说明存货增长与收入变化是否匹配，跌价准备计提是否充分。",
        procedure="执行存货监盘，测试库龄，检查后续销售价格。",
        keywords=["存货", "跌价准备", "周转", "积压", "监盘"],
    ),
    SimilarCase(
        title="关联交易和资金占用风险案例",
        source="监管处罚公开案例",
        risk_type="关联交易",
        summary="重点核查关联方交易定价公允性、披露完整性以及是否存在资金占用。",
        question="请列示关联交易定价依据及资金流向，说明是否存在未披露的资金占用。",
        procedure="比对关联方名录，检查银行流水，核对合同、发票和付款路径。",
        keywords=["关联交易", "资金占用", "关联方", "定价", "披露"],
    ),
    SimilarCase(
        title="经营现金流与利润背离问询",
        source="年报监管问询公开案例",
        risk_type="现金流",
        summary="对净利润增长但经营现金流持续为负的情况，要求说明收入质量和回款能力。",
        question="请说明净利润与经营现金流背离的主要原因及改善措施。",
        procedure="分析销售回款、预收款、应付项目和客户结算政策。",
        keywords=["现金流", "净利润", "回款", "利润", "背离"],
    ),
    SimilarCase(
        title="商誉减值与并购整合风险案例",
        source="审计监管案例",
        risk_type="商誉",
        summary="关注并购形成的商誉是否存在减值迹象，减值测试假设是否合理。",
        question="请说明商誉减值测试的关键假设、预测期增长率和折现率依据。",
        procedure="复核管理层模型，比较历史预测与实际完成情况，必要时引入专家复核。",
        keywords=["商誉", "减值", "并购", "折现率", "测试"],
    ),
    SimilarCase(
        title="对外担保和或有负债披露不足案例",
        source="行政处罚公开案例",
        risk_type="担保",
        summary="对对外担保余额、审批程序和披露时点进行核查，防止信息披露遗漏。",
        question="请说明对外担保余额、审批程序及是否存在未及时披露情形。",
        procedure="核对董事会决议、担保合同、披露公告与银行函证。",
        keywords=["担保", "或有负债", "披露", "审批", "银行函证"],
    ),
]


def build_default_case_library() -> list[SimilarCase]:
    return [SimilarCase(**asdict(case)) for case in DEFAULT_CASES]


def _normalize_keywords(raw: str | Iterable[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        normalized = raw.replace("，", ",").replace("；", ",").replace(";", ",")
        parts = [item.strip() for item in normalized.split(",")]
        return [item for item in parts if item]
    return [str(item).strip() for item in raw if str(item).strip()]


DOMAIN_TERMS = [
    "应收账款",
    "回款",
    "坏账",
    "存货",
    "跌价",
    "周转",
    "关联交易",
    "关联方",
    "资金占用",
    "现金流",
    "净利润",
    "商誉",
    "减值",
    "担保",
    "客户集中",
    "毛利率",
    "收入",
    "利润",
]


def _extract_terms(text: str) -> set[str]:
    text = text or ""
    terms: set[str] = set()
    for term in DOMAIN_TERMS:
        if term in text:
            terms.add(term)
    return terms


def load_case_library_from_file(file_name: str, content: bytes) -> list[SimilarCase]:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".json":
        payload = json.loads(content.decode("utf-8"))
        records = payload if isinstance(payload, list) else payload.get("cases", [])
    elif suffix == ".csv":
        decoded = content.decode("utf-8-sig")
        records = list(csv.DictReader(decoded.splitlines()))
    else:
        raise ValueError("仅支持 JSON 或 CSV 案例库文件。")

    cases: list[SimilarCase] = []
    for item in records:
        cases.append(
            SimilarCase(
                title=str(item.get("title") or item.get("名称") or "未命名案例"),
                source=str(item.get("source") or item.get("来源") or "用户上传"),
                risk_type=str(item.get("risk_type") or item.get("风险类型") or "未知"),
                summary=str(item.get("summary") or item.get("summary_text") or item.get("摘要") or ""),
                question=str(item.get("question") or item.get("问题") or ""),
                procedure=str(item.get("procedure") or item.get("程序") or ""),
                keywords=_normalize_keywords(item.get("keywords") or item.get("关键词")),
            )
        )
    return cases


def score_case(query_terms: list[str], case: SimilarCase) -> float:
    query_text = " ".join(query_terms)
    query_terms_set = _extract_terms(query_text)
    case_terms = set(case.keywords)
    case_terms.update(_extract_terms(case.title))
    case_terms.update(_extract_terms(case.summary))

    if not query_terms_set or not case_terms:
        return 0.0

    overlap = len(query_terms_set & case_terms)
    if overlap == 0:
        return 0.0
    return round(min(1.0, overlap / max(3, len(query_terms_set) / 1.5)) * 100, 2)


def retrieve_similar_cases(query_terms: list[str], library: list[SimilarCase], top_k: int = 3) -> list[SimilarCase]:
    scored: list[SimilarCase] = []
    for case in library:
        case_copy = SimilarCase(**asdict(case))
        case_copy.score = score_case(query_terms, case_copy)
        if case_copy.score > 0:
            scored.append(case_copy)
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]
