from __future__ import annotations

from .models import FinancialSnapshot


DEMO_SCENARIOS: dict[str, dict] = {
    "应收账款与现金流背离": {
        "snapshot": FinancialSnapshot(
            company_name="星河装备股份有限公司",
            industry="高端制造",
            report_period="2025年度",
            revenue=1280_000_000,
            revenue_yoy=12.8,
            net_profit=86_000_000,
            net_profit_yoy=3.2,
            cfo=-24_000_000,
            cfo_yoy=-138.5,
            receivables=512_000_000,
            receivables_yoy=46.3,
            inventory=260_000_000,
            inventory_yoy=15.1,
            gross_margin=18.4,
            gross_margin_change=-6.8,
            related_party_ratio=6.5,
            top5_customer_ratio=41.2,
            asset_impairment_ratio=1.2,
            goodwill_ratio=0.0,
            guarantee_ratio=2.1,
            debt_ratio=58.0,
            notes="主营业务扩张较快，但经营现金流转负，应收账款回款压力明显。",
        ),
        "summary": "公司收入保持增长，但经营活动现金流净额转负，应收账款大幅增加，回款质量值得关注。",
    },
    "存货与毛利率压力": {
        "snapshot": FinancialSnapshot(
            company_name="晨曦消费电子有限公司",
            industry="消费电子",
            report_period="2025年度",
            revenue=940_000_000,
            revenue_yoy=-4.7,
            net_profit=12_000_000,
            net_profit_yoy=-68.9,
            cfo=9_000_000,
            cfo_yoy=-42.0,
            receivables=110_000_000,
            receivables_yoy=8.5,
            inventory=315_000_000,
            inventory_yoy=39.4,
            gross_margin=11.7,
            gross_margin_change=-9.6,
            related_party_ratio=3.0,
            top5_customer_ratio=55.0,
            asset_impairment_ratio=4.6,
            goodwill_ratio=18.0,
            guarantee_ratio=0.0,
            debt_ratio=63.0,
            notes="产品价格战加剧，存货周转和毛利率同时承压。",
        ),
        "summary": "公司收入回落、毛利率下滑、存货增长较快，且资产减值计提上升，适合做库存风险和减值风险演示。",
    },
    "关联交易与集中度风险": {
        "snapshot": FinancialSnapshot(
            company_name="云桥科技集团",
            industry="软件与信息服务",
            report_period="2025年度",
            revenue=680_000_000,
            revenue_yoy=28.4,
            net_profit=31_000_000,
            net_profit_yoy=18.2,
            cfo=14_000_000,
            cfo_yoy=6.8,
            receivables=188_000_000,
            receivables_yoy=34.9,
            inventory=12_000_000,
            inventory_yoy=4.0,
            gross_margin=42.5,
            gross_margin_change=1.8,
            related_party_ratio=22.0,
            top5_customer_ratio=78.0,
            asset_impairment_ratio=0.8,
            goodwill_ratio=9.0,
            guarantee_ratio=12.5,
            debt_ratio=37.0,
            notes="大客户集中度较高，关联交易和担保余额同步上升。",
        ),
        "summary": "公司增长迅速，但收入集中度、关联交易和对外担保均偏高，适合做监管问询场景。",
    },
}


def default_snapshot() -> FinancialSnapshot:
    return DEMO_SCENARIOS["应收账款与现金流背离"]["snapshot"]


def default_summary() -> str:
    return DEMO_SCENARIOS["应收账款与现金流背离"]["summary"]
