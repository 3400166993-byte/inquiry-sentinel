from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .case_library import retrieve_similar_cases
from .llm_client import LLMSettings, chat_completion, parse_json_object
from .models import AnalysisResult, DocumentContext, FinancialSnapshot, RiskFinding, SimilarCase
from .rules import evaluate_snapshot, evaluate_text_signals


def _fallback_llm_payload(finding: RiskFinding, cases: list[SimilarCase]) -> dict[str, Any]:
    questions = finding.suggested_question[:]
    procedures = finding.suggested_procedure[:]
    if cases:
        questions = [f"{questions[0]}（参考相似案例：{cases[0].title}）"] + questions[1:]
    summary = finding.explanation
    if cases:
        summary += f" 相似监管/审计案例显示，类似问题通常会追问：{cases[0].question}"
    return {
        "summary": summary,
        "questions": questions,
        "procedures": procedures,
        "confidence": round(min(0.95, finding.score / 100), 2),
    }


def _build_case_context(cases: list[SimilarCase]) -> str:
    if not cases:
        return "无相似案例。"
    parts = []
    for index, case in enumerate(cases, start=1):
        parts.append(
            f"{index}. 标题：{case.title}\n"
            f"   来源：{case.source}\n"
            f"   摘要：{case.summary}\n"
            f"   问题：{case.question}\n"
            f"   程序：{case.procedure}\n"
            f"   匹配度：{case.score:.1f}"
        )
    return "\n".join(parts)


def enrich_finding_with_llm(
    settings: LLMSettings,
    snapshot: FinancialSnapshot,
    document: DocumentContext,
    finding: RiskFinding,
    cases: list[SimilarCase],
) -> dict[str, Any]:
    if not settings.enabled:
        return _fallback_llm_payload(finding, cases)

    system_prompt = (
        "你是财务审计与交易所问询分析助手。"
        "你必须只输出JSON对象，不要输出多余文字。"
        "内容应围绕会计、审计、财务披露风险，不要给出法律结论。"
        "结果必须包含 summary, questions, procedures, confidence 四个字段。"
    )
    user_payload = {
        "company": snapshot.company_name,
        "industry": snapshot.industry,
        "report_period": snapshot.report_period,
        "document_summary": document.summary,
        "risk": {
            "title": finding.title,
            "score": finding.score,
            "severity": finding.severity,
            "evidence": finding.evidence,
            "base_explanation": finding.explanation,
            "default_questions": finding.suggested_question,
            "default_procedures": finding.suggested_procedure,
        },
        "similar_cases": [
            {
                "title": case.title,
                "source": case.source,
                "risk_type": case.risk_type,
                "summary": case.summary,
                "question": case.question,
                "procedure": case.procedure,
                "score": case.score,
            }
            for case in cases
        ],
    }
    user_prompt = (
        "请基于下面的输入，为该风险生成更专业的问询问题与审计程序。"
        "要求：\n"
        "1. questions 至少3条，尽量具体。\n"
        "2. procedures 至少3条，尽量可执行。\n"
        "3. summary 1-2句，突出风险逻辑。\n"
        "4. confidence 取 0 到 1 的小数。\n"
        "5. 只返回JSON对象，不要加Markdown代码块。\n\n"
        f"{json.dumps(user_payload, ensure_ascii=False)}"
    )

    try:
        raw = chat_completion(settings, system_prompt, user_prompt)
        parsed = parse_json_object(raw)
        return {
            "summary": str(parsed.get("summary") or finding.explanation),
            "questions": [str(item) for item in parsed.get("questions", []) if str(item).strip()],
            "procedures": [str(item) for item in parsed.get("procedures", []) if str(item).strip()],
            "confidence": float(parsed.get("confidence") or 0.7),
        }
    except Exception:
        return _fallback_llm_payload(finding, cases)


def compose_overall_summary(
    settings: LLMSettings,
    snapshot: FinancialSnapshot,
    document: DocumentContext,
    findings: list[RiskFinding],
) -> str:
    if not findings:
        return "未识别到明显风险点，但建议继续补充年报原文与关键指标后复核。"

    lead = findings[0]
    if not settings.enabled:
        return (
            f"{snapshot.company_name} 识别到 {len(findings)} 个重点风险点，"
            f"其中最突出的是“{lead.title}”。"
            f"{lead.explanation} 建议先围绕该项展开审计核查。"
        )

    system_prompt = (
        "你是上市公司年报问询分析总控助手。"
        "只输出JSON对象，字段为 summary。"
        "summary 要在2-3句内概括整体风险画像与优先级。"
    )
    payload = {
        "company": snapshot.company_name,
        "industry": snapshot.industry,
        "document_summary": document.summary,
        "findings": [
            {
                "title": finding.title,
                "severity": finding.severity,
                "score": finding.score,
                "evidence": finding.evidence,
                "explanation": finding.explanation,
            }
            for finding in findings[:5]
        ],
    }
    user_prompt = f"请根据以下输入，输出summary字段：{json.dumps(payload, ensure_ascii=False)}"
    try:
        raw = chat_completion(settings, system_prompt, user_prompt)
        parsed = parse_json_object(raw)
        return str(parsed.get("summary") or "")
    except Exception:
        return (
            f"{snapshot.company_name} 识别到 {len(findings)} 个重点风险点，"
            f"其中最突出的是“{lead.title}”。"
            f"{lead.explanation} 建议先围绕该项展开审计核查。"
        )


def run_analysis(
    snapshot: FinancialSnapshot,
    document: DocumentContext,
    case_library: list[SimilarCase],
    settings: LLMSettings,
    top_k: int = 5,
) -> AnalysisResult:
    findings = evaluate_snapshot(snapshot)
    text_findings = evaluate_text_signals(document.extracted_text)
    findings_by_id = {finding.risk_id: finding for finding in findings}
    for text_finding in text_findings:
        existing = findings_by_id.get(text_finding.risk_id)
        if existing is None:
            findings.append(text_finding)
            findings_by_id[text_finding.risk_id] = text_finding
            continue
        existing.score = max(existing.score, text_finding.score)
        existing.evidence.extend(item for item in text_finding.evidence if item not in existing.evidence)
        if "文本信号" not in existing.explanation:
            existing.explanation += " 同时发现正文风险信号，建议结合原文复核。"
    findings.sort(key=lambda item: item.score, reverse=True)
    enriched: list[RiskFinding] = []

    for finding in findings[:top_k]:
        query_terms = [finding.title] + finding.evidence + finding.suggested_question + finding.suggested_procedure
        query_terms.extend(snapshot.industry.split())
        cases = retrieve_similar_cases(query_terms, case_library, top_k=3)
        llm_payload = enrich_finding_with_llm(settings, snapshot, document, finding, cases)
        finding.supporting_cases = cases
        finding.llm_summary = str(llm_payload.get("summary") or finding.explanation)
        finding.llm_questions = [str(item) for item in llm_payload.get("questions", []) if str(item).strip()]
        finding.llm_procedures = [str(item) for item in llm_payload.get("procedures", []) if str(item).strip()]
        finding.llm_confidence = float(llm_payload.get("confidence") or 0.0)
        enriched.append(finding)

    summary = compose_overall_summary(settings, snapshot, document, enriched)

    evidence_covered = sum(1 for finding in enriched if finding.evidence)
    case_covered = sum(1 for finding in enriched if finding.supporting_cases)
    is_summary = "摘要" in document.source_name or "摘要" in document.summary[:500]
    diagnostics = {
        "filled_fields": snapshot.filled_fields(),
        "finding_count": len(enriched),
        "evidence_coverage": f"{(evidence_covered / max(1, len(enriched))) * 100:.0f}%",
        "case_coverage": f"{(case_covered / max(1, len(enriched))) * 100:.0f}%",
        "llm_mode": settings.provider if settings.enabled else "演示模式",
        "text_chars": len(document.extracted_text),
        "text_pages": document.page_count,
        "text_signal_count": len(text_findings),
        "document_type": "公告摘要" if is_summary else "报告/文本",
        "extraction_status": (
            "摘要版核心字段已抽取"
            if is_summary and snapshot.filled_fields() >= 5
            else
            "字段充足"
            if snapshot.filled_fields() >= 12
            else "字段部分抽取，已启用正文信号补充"
            if text_findings
            else "字段不足，建议人工复核"
        ),
    }

    generated_by = (
        f"{settings.provider} / {settings.model}"
        if settings.enabled
        else "演示模式（规则引擎 + 本地案例库）"
    )

    return AnalysisResult(
        snapshot=snapshot,
        document=document,
        findings=enriched,
        summary=summary,
        diagnostics=diagnostics,
        generated_by=generated_by,
    )
