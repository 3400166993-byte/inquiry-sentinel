from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Optional


@dataclass
class FinancialSnapshot:
    company_name: str = "示例公司"
    industry: str = "制造业"
    report_period: str = "2025年度"
    currency_unit: str = "元"

    revenue: Optional[float] = None
    revenue_yoy: Optional[float] = None
    net_profit: Optional[float] = None
    net_profit_yoy: Optional[float] = None
    cfo: Optional[float] = None
    cfo_yoy: Optional[float] = None
    receivables: Optional[float] = None
    receivables_yoy: Optional[float] = None
    inventory: Optional[float] = None
    inventory_yoy: Optional[float] = None
    gross_margin: Optional[float] = None
    gross_margin_change: Optional[float] = None
    related_party_ratio: Optional[float] = None
    top5_customer_ratio: Optional[float] = None
    asset_impairment_ratio: Optional[float] = None
    goodwill_ratio: Optional[float] = None
    guarantee_ratio: Optional[float] = None
    debt_ratio: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def filled_fields(self) -> int:
        values = [
            self.revenue,
            self.revenue_yoy,
            self.net_profit,
            self.net_profit_yoy,
            self.cfo,
            self.cfo_yoy,
            self.receivables,
            self.receivables_yoy,
            self.inventory,
            self.inventory_yoy,
            self.gross_margin,
            self.gross_margin_change,
            self.related_party_ratio,
            self.top5_customer_ratio,
            self.asset_impairment_ratio,
            self.goodwill_ratio,
            self.guarantee_ratio,
            self.debt_ratio,
        ]
        return sum(value is not None for value in values)


@dataclass
class DocumentContext:
    source_name: str
    extracted_text: str = ""
    page_count: int = 0
    summary: str = ""
    page_texts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "page_count": self.page_count,
            "summary": self.summary,
            "text_chars": len(self.extracted_text),
        }


@dataclass
class EvidenceReference:
    label: str
    quote: str
    source: str
    page: int | None = None
    confidence: str = "中"


@dataclass
class RiskDefinition:
    risk_id: str
    title: str
    description: str
    keywords: list[str]
    question_templates: list[str]
    procedure_templates: list[str]


@dataclass
class SimilarCase:
    title: str
    source: str
    risk_type: str
    summary: str
    question: str
    procedure: str
    keywords: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class RiskFinding:
    risk_id: str
    title: str
    score: float
    severity: str
    evidence: list[str]
    explanation: str
    suggested_question: list[str]
    suggested_procedure: list[str]
    evidence_references: list[EvidenceReference] = field(default_factory=list)
    supporting_cases: list[SimilarCase] = field(default_factory=list)
    llm_summary: str = ""
    llm_questions: list[str] = field(default_factory=list)
    llm_procedures: list[str] = field(default_factory=list)
    llm_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["supporting_cases"] = [asdict(case) for case in self.supporting_cases]
        return data


@dataclass
class AnalysisResult:
    snapshot: FinancialSnapshot
    document: DocumentContext
    findings: list[RiskFinding]
    summary: str
    diagnostics: dict[str, Any]
    generated_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "document": self.document.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "summary": self.summary,
            "diagnostics": self.diagnostics,
            "generated_by": self.generated_by,
        }
