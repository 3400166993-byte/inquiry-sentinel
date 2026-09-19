from __future__ import annotations

from dataclasses import asdict
import re

from .models import FinancialSnapshot, RiskDefinition, RiskFinding


RISK_DEFINITIONS: list[RiskDefinition] = [
    RiskDefinition(
        risk_id="cashflow_mismatch",
        title="经营现金流与收入/利润背离",
        description="收入或利润增长但经营现金流明显转弱，可能提示收入质量、回款或营运资本压力。",
        keywords=["现金流", "收入", "利润", "回款"],
        question_templates=[
            "请说明本期收入增长但经营活动现金流净额下降的原因。",
            "请结合客户回款、信用政策和结算安排，说明现金流恶化是否具有持续性。",
        ],
        procedure_templates=[
            "分析销售回款结构和期后回款情况。",
            "复核应收、预收、应付项目的变动对现金流的影响。",
        ],
    ),
    RiskDefinition(
        risk_id="receivables_growth",
        title="应收账款异常增长",
        description="应收账款增速显著高于收入增速，或应收余额占收入比例异常，可能提示回款风险或收入确认压力。",
        keywords=["应收账款", "账龄", "坏账", "回款"],
        question_templates=[
            "请说明应收账款增长显著高于收入增长的原因。",
            "请披露主要客户账龄、期后回款及坏账准备计提政策。",
        ],
        procedure_templates=[
            "执行主要客户函证和期后回款检查。",
            "复核坏账准备计提模型和管理层判断。",
        ],
    ),
    RiskDefinition(
        risk_id="inventory_pressure",
        title="存货积压与跌价风险",
        description="存货增速快于收入增速，或毛利率下降且库存上升，可能提示库存积压和跌价准备不足。",
        keywords=["存货", "跌价准备", "周转", "监盘"],
        question_templates=[
            "请说明存货增长与销售变化是否匹配。",
            "请说明跌价准备计提政策及库龄结构变化。",
        ],
        procedure_templates=[
            "执行存货监盘和库龄分析。",
            "检查后续销售价格和跌价准备测试结果。",
        ],
    ),
    RiskDefinition(
        risk_id="margin_volatility",
        title="毛利率异常波动",
        description="毛利率大幅下降或波动异常，可能提示产品结构、售价、成本确认或竞争压力变化。",
        keywords=["毛利率", "售价", "成本", "产品结构"],
        question_templates=[
            "请说明毛利率波动的主要原因及与行业趋势的差异。",
            "请结合产品结构和成本变动说明毛利率变化是否可持续。",
        ],
        procedure_templates=[
            "拆分产品线毛利率并复核主要成本构成。",
            "对比行业平均和主要竞争对手变化。",
        ],
    ),
    RiskDefinition(
        risk_id="related_party",
        title="关联交易、客户集中与资金占用",
        description="关联交易比重偏高、客户集中度高或担保余额上升，可能提示利益输送或披露不充分。",
        keywords=["关联交易", "关联方", "客户集中", "担保", "资金占用"],
        question_templates=[
            "请列示关联交易金额、定价依据及审批程序。",
            "请说明是否存在对关联方的资金占用或担保安排。",
        ],
        procedure_templates=[
            "比对关联方名录、合同、发票和收付款流水。",
            "核查董事会、股东会和信息披露公告。",
        ],
    ),
    RiskDefinition(
        risk_id="impairment_goodwill",
        title="资产减值与商誉减值",
        description="资产减值计提上升或商誉余额较高，可能提示减值测试假设偏乐观。",
        keywords=["减值", "商誉", "折现率", "测试"],
        question_templates=[
            "请说明商誉减值测试的关键假设及敏感性分析结果。",
            "请说明本期减值计提是否充分、是否存在一次性调节利润情形。",
        ],
        procedure_templates=[
            "复核减值模型参数和历史预测偏差。",
            "检查管理层预测与后续经营结果的一致性。",
        ],
    ),
    RiskDefinition(
        risk_id="guarantee",
        title="对外担保与或有负债",
        description="担保余额和或有负债上升，可能影响偿债能力和信息披露完整性。",
        keywords=["担保", "或有负债", "债务", "披露"],
        question_templates=[
            "请说明对外担保余额、审批程序及风险控制措施。",
            "请说明是否存在未及时披露的或有负债事项。",
        ],
        procedure_templates=[
            "核对担保合同、董事会决议和银行函证。",
            "检查是否已按要求披露相关或有事项。",
        ],
    ),
]

RISK_DEFINITION_BY_ID = {item.risk_id: item for item in RISK_DEFINITIONS}


def _pct(value: float | None) -> str:
    if value is None:
        return "未提供"
    return f"{value:.1f}%"


def _severity(score: float) -> str:
    if score >= 80:
        return "高"
    if score >= 55:
        return "中"
    return "低"


def _add_evidence(items: list[str], text: str | None) -> None:
    if text and text not in items:
        items.append(text)


def evaluate_snapshot(snapshot: FinancialSnapshot) -> list[RiskFinding]:
    findings: list[RiskFinding] = []

    revenue_yoy = snapshot.revenue_yoy
    net_profit_yoy = snapshot.net_profit_yoy
    cfo = snapshot.cfo
    cfo_yoy = snapshot.cfo_yoy
    receivables_yoy = snapshot.receivables_yoy
    inventory_yoy = snapshot.inventory_yoy
    gross_margin = snapshot.gross_margin
    gross_margin_change = snapshot.gross_margin_change
    related_party_ratio = snapshot.related_party_ratio
    top5_customer_ratio = snapshot.top5_customer_ratio
    asset_impairment_ratio = snapshot.asset_impairment_ratio
    goodwill_ratio = snapshot.goodwill_ratio
    guarantee_ratio = snapshot.guarantee_ratio

    # 1. Cash flow mismatch
    score = 0.0
    evidence: list[str] = []
    if revenue_yoy is not None and cfo_yoy is not None:
        gap = revenue_yoy - cfo_yoy
        if gap > 20:
            score += min(40, gap * 1.3)
            _add_evidence(evidence, f"收入同比增长{_pct(revenue_yoy)}，经营现金流同比{_pct(cfo_yoy)}，二者背离明显。")
    if snapshot.revenue is not None and cfo is not None and cfo < 0:
        score += 20
        _add_evidence(evidence, "经营活动现金流净额为负。")
    if snapshot.net_profit is not None and cfo is not None and snapshot.net_profit > 0 and cfo < 0:
        score += 25
        _add_evidence(evidence, "净利润为正但经营现金流为负。")
    if score >= 35:
        findings.append(
            RiskFinding(
                risk_id="cashflow_mismatch",
                title="经营现金流与收入/利润背离",
                score=min(score, 100),
                severity=_severity(score),
                evidence=evidence,
                explanation="收入增长或利润确认与经营现金流表现不一致，可能提示收入质量、回款或营运资本压力。",
                suggested_question=RISK_DEFINITIONS[0].question_templates.copy(),
                suggested_procedure=RISK_DEFINITIONS[0].procedure_templates.copy(),
            )
        )

    # 2. Receivables growth
    score = 0.0
    evidence = []
    if receivables_yoy is not None and revenue_yoy is not None:
        if receivables_yoy - revenue_yoy > 15:
            score += min(45, (receivables_yoy - revenue_yoy) * 1.5)
            _add_evidence(evidence, f"应收账款同比增长{_pct(receivables_yoy)}，高于收入同比{_pct(revenue_yoy)}。")
    if snapshot.receivables is not None and snapshot.revenue is not None and snapshot.revenue > 0:
        ratio = snapshot.receivables / snapshot.revenue * 100
        if ratio > 35:
            score += min(35, (ratio - 35) * 1.2)
            _add_evidence(evidence, f"应收账款占收入比约{ratio:.1f}%。")
    if top5_customer_ratio is not None and top5_customer_ratio > 60:
        score += 10
        _add_evidence(evidence, f"前五大客户收入占比{_pct(top5_customer_ratio)}，客户集中度较高。")
    if score >= 35:
        findings.append(
            RiskFinding(
                risk_id="receivables_growth",
                title="应收账款异常增长",
                score=min(score, 100),
                severity=_severity(score),
                evidence=evidence,
                explanation="应收账款增速和余额占比异常，可能提示回款压力或收入确认质量问题。",
                suggested_question=RISK_DEFINITIONS[1].question_templates.copy(),
                suggested_procedure=RISK_DEFINITIONS[1].procedure_templates.copy(),
            )
        )

    # 3. Inventory pressure
    score = 0.0
    evidence = []
    if inventory_yoy is not None and revenue_yoy is not None and inventory_yoy - revenue_yoy > 15:
        score += min(40, (inventory_yoy - revenue_yoy) * 1.4)
        _add_evidence(evidence, f"存货同比增长{_pct(inventory_yoy)}，高于收入同比{_pct(revenue_yoy)}。")
    if gross_margin_change is not None and gross_margin_change <= -5:
        score += min(30, abs(gross_margin_change) * 2)
        _add_evidence(evidence, f"毛利率变动{gross_margin_change:.1f}个百分点，下降明显。")
    if gross_margin is not None and gross_margin < 15:
        score += 10
        _add_evidence(evidence, f"毛利率仅{gross_margin:.1f}%，处于偏低水平。")
    if score >= 35:
        findings.append(
            RiskFinding(
                risk_id="inventory_pressure",
                title="存货积压与跌价风险",
                score=min(score, 100),
                severity=_severity(score),
                evidence=evidence,
                explanation="存货增长和毛利率下滑可能联动出现，提示库存积压或跌价准备计提不足。",
                suggested_question=RISK_DEFINITIONS[2].question_templates.copy(),
                suggested_procedure=RISK_DEFINITIONS[2].procedure_templates.copy(),
            )
        )

    # 4. Margin volatility
    score = 0.0
    evidence = []
    if gross_margin_change is not None and abs(gross_margin_change) >= 8:
        score += min(50, abs(gross_margin_change) * 3)
        _add_evidence(evidence, f"毛利率同比变动{gross_margin_change:.1f}个百分点。")
    if gross_margin is not None and gross_margin < 20:
        score += 15
        _add_evidence(evidence, f"毛利率为{gross_margin:.1f}%，低于常见制造业或服务业中高值区间。")
    if score >= 40:
        findings.append(
            RiskFinding(
                risk_id="margin_volatility",
                title="毛利率异常波动",
                score=min(score, 100),
                severity=_severity(score),
                evidence=evidence,
                explanation="毛利率波动可能来自产品结构、价格、成本或收入确认差异，值得进一步核查。",
                suggested_question=RISK_DEFINITIONS[3].question_templates.copy(),
                suggested_procedure=RISK_DEFINITIONS[3].procedure_templates.copy(),
            )
        )

    # 5. Related party / concentration
    score = 0.0
    evidence = []
    if related_party_ratio is not None and related_party_ratio >= 10:
        score += min(35, (related_party_ratio - 10) * 2.5 + 15)
        _add_evidence(evidence, f"关联交易占比{_pct(related_party_ratio)}。")
    if top5_customer_ratio is not None and top5_customer_ratio >= 60:
        score += min(25, (top5_customer_ratio - 60) * 1.2 + 10)
        _add_evidence(evidence, f"前五大客户收入占比{_pct(top5_customer_ratio)}。")
    if guarantee_ratio is not None and guarantee_ratio >= 8:
        score += min(25, guarantee_ratio * 2)
        _add_evidence(evidence, f"对外担保余额占比{_pct(guarantee_ratio)}。")
    if score >= 35:
        findings.append(
            RiskFinding(
                risk_id="related_party",
                title="关联交易、客户集中与资金占用",
                score=min(score, 100),
                severity=_severity(score),
                evidence=evidence,
                explanation="关联交易、客户集中和担保余额同步偏高时，需要重点关注公允性、披露完整性和资金占用风险。",
                suggested_question=RISK_DEFINITIONS[4].question_templates.copy(),
                suggested_procedure=RISK_DEFINITIONS[4].procedure_templates.copy(),
            )
        )

    # 6. Impairment / goodwill
    score = 0.0
    evidence = []
    if asset_impairment_ratio is not None and asset_impairment_ratio >= 3:
        score += min(35, asset_impairment_ratio * 4)
        _add_evidence(evidence, f"资产减值计提占比{_pct(asset_impairment_ratio)}。")
    if goodwill_ratio is not None and goodwill_ratio >= 10:
        score += min(35, (goodwill_ratio - 10) * 1.2 + 15)
        _add_evidence(evidence, f"商誉占比{_pct(goodwill_ratio)}。")
    if score >= 35:
        findings.append(
            RiskFinding(
                risk_id="impairment_goodwill",
                title="资产减值与商誉减值",
                score=min(score, 100),
                severity=_severity(score),
                evidence=evidence,
                explanation="资产减值或商誉减值测试假设偏乐观时，可能成为问询重点。",
                suggested_question=RISK_DEFINITIONS[5].question_templates.copy(),
                suggested_procedure=RISK_DEFINITIONS[5].procedure_templates.copy(),
            )
        )

    # 7. Guarantee
    score = 0.0
    evidence = []
    if guarantee_ratio is not None and guarantee_ratio >= 8:
        score += min(60, guarantee_ratio * 4)
        _add_evidence(evidence, f"对外担保余额占比{_pct(guarantee_ratio)}。")
    if score >= 35:
        findings.append(
            RiskFinding(
                risk_id="guarantee",
                title="对外担保与或有负债",
                score=min(score, 100),
                severity=_severity(score),
                evidence=evidence,
                explanation="担保余额较高时，信息披露完整性、审批程序和偿债风险都需要核查。",
                suggested_question=RISK_DEFINITIONS[6].question_templates.copy(),
                suggested_procedure=RISK_DEFINITIONS[6].procedure_templates.copy(),
            )
        )

    findings.sort(key=lambda item: item.score, reverse=True)
    return findings


def _text_context(text: str, keyword: str, window: int = 80) -> str:
    position = text.find(keyword)
    if position < 0:
        return ""
    start = max(0, position - 30)
    end = min(len(text), position + len(keyword) + window)
    return text[start:end]


def evaluate_text_signals(text: str) -> list[RiskFinding]:
    """补充识别正文中的明确风险表述，避免表格抽取不完整时误显示为零风险。"""
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return []

    signal_rules = [
        (
            "cashflow_mismatch",
            ["经营活动产生的现金流量净额"],
            ["为负", "负数", "下降", "减少", "下滑"],
            ["营业收入", "净利润", "回款"],
            "年报正文出现经营现金流转弱或为负的表述，但当前财务表格字段可能未完整抽取。",
        ),
        (
            "receivables_growth",
            ["应收账款"],
            ["增长", "增加", "上升", "扩大"],
            ["回款", "坏账", "账龄", "信用", "逾期"],
            "年报正文同时提到应收账款增长和回款/坏账相关事项，建议核对账龄和期后回款。",
        ),
        (
            "inventory_pressure",
            ["存货"],
            ["增长", "增加", "上升", "积压", "周转"],
            ["跌价", "减值", "库龄", "滞销"],
            "年报正文出现存货规模或周转压力表述，建议进一步核查库龄和跌价准备。",
        ),
        (
            "margin_volatility",
            ["毛利率"],
            ["下降", "下滑", "波动", "降低"],
            [],
            "年报正文出现毛利率下降或波动表述，建议拆分产品线核查价格和成本变化。",
        ),
        (
            "related_party",
            ["关联交易"],
            ["占比", "定价", "披露", "关联方", "公允"],
            [],
            "年报正文出现关联交易相关表述，建议核查定价公允性、审批程序和披露完整性。",
        ),
        (
            "impairment_goodwill",
            ["商誉"],
            ["减值", "测试", "折现", "预测"],
            [],
            "年报正文出现商誉减值测试相关表述，建议复核关键假设和预测偏差。",
        ),
        (
            "guarantee",
            ["担保"],
            ["余额", "审批", "披露", "或有负债", "风险"],
            [],
            "年报正文出现对外担保或或有负债相关表述，建议核对审批、合同和披露。",
        ),
    ]

    findings: list[RiskFinding] = []
    for risk_id, primary_terms, secondary_terms, context_terms, explanation in signal_rules:
        primary = next((term for term in primary_terms if term in compact), None)
        if not primary:
            continue
        local_context = _text_context(compact, primary, window=180)
        secondary = next((term for term in secondary_terms if term in compact), None)
        if not secondary:
            continue
        if secondary not in local_context:
            continue
        if context_terms and not any(term in local_context for term in context_terms):
            continue

        definition = RISK_DEFINITION_BY_ID[risk_id]
        evidence = [local_context]
        findings.append(
            RiskFinding(
                risk_id=risk_id,
                title=definition.title,
                score=52.0,
                severity="中",
                evidence=[f"正文信号：{evidence[0]}"],
                explanation=explanation + "该项属于文本信号，仍需回到原始报表和凭证核实。",
                suggested_question=definition.question_templates.copy(),
                suggested_procedure=definition.procedure_templates.copy(),
            )
        )

    findings.sort(key=lambda item: item.score, reverse=True)
    return findings
