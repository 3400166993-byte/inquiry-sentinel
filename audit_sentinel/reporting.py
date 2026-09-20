from __future__ import annotations

import io
import json
import textwrap
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    REPORTLAB_AVAILABLE = False

from .models import AnalysisResult, RiskFinding


def findings_to_frame(findings: list[RiskFinding]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in findings:
        question = item.llm_questions or item.suggested_question
        procedure = item.llm_procedures or item.suggested_procedure
        rows.append(
            {
                "风险类型": item.title,
                "风险等级": item.severity,
                "风险分": round(item.score, 1),
                "核心证据": "；".join(item.evidence),
                "证据页码": "、".join(str(ref.page) for ref in item.evidence_references if ref.page) or "指标复核表",
                "证据来源": "；".join(ref.quote for ref in item.evidence_references),
                "可能问询问题": "；".join(question),
                "建议审计程序": "；".join(procedure),
                "相似案例数": len(item.supporting_cases),
                "AI生成声明": "本结果由AI生成，仅作辅助分析，不构成审计、法律或投资意见。",
            }
        )
    return pd.DataFrame(rows)


def result_to_json_bytes(result: AnalysisResult) -> bytes:
    payload = result.to_dict()
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def result_to_csv_bytes(result: AnalysisResult) -> bytes:
    frame = findings_to_frame(result.findings)
    return frame.to_csv(index=False).encode("utf-8-sig")


def result_to_markdown(result: AnalysisResult) -> str:
    lines = [
        "# 问询前哨分析报告",
        "",
        f"- 公司：{result.snapshot.company_name}",
        f"- 报告期：{result.snapshot.report_period}",
        f"- 来源文件：{result.document.source_name}",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 模型/模式：{result.generated_by}",
        "",
        "## 总体结论",
        "",
        result.summary,
        "",
        "## 风险明细",
        "",
    ]

    for index, finding in enumerate(result.findings, start=1):
        questions = finding.llm_questions or finding.suggested_question
        procedures = finding.llm_procedures or finding.suggested_procedure
        lines.extend(
            [
                f"### {index}. {finding.title}（{finding.severity}，{finding.score:.1f}分）",
                "",
                f"解释：{finding.llm_summary or finding.explanation}",
                "",
                "证据：",
            ]
        )
        lines.extend([f"- {item}" for item in finding.evidence])
        if finding.evidence_references:
            lines.append("")
            lines.append("证据链：")
            for reference in finding.evidence_references:
                location = f"第{reference.page}页" if reference.page else "指标复核表"
                lines.append(f"- {location}｜{reference.source}｜{reference.quote}")
        lines.append("")
        lines.append("可能问询问题：")
        lines.extend([f"- {item}" for item in questions])
        lines.append("")
        lines.append("建议审计程序：")
        lines.extend([f"- {item}" for item in procedures])
        if finding.supporting_cases:
            lines.append("")
            lines.append("相似案例：")
            for case in finding.supporting_cases:
                lines.append(f"- {case.title}（{case.source}，匹配度 {case.score:.1f}）")
        lines.append("")

    lines.extend(
        [
            "## 免责声明",
            "",
            "本报告由AI生成，仅用于课程、竞赛和内部辅助分析，不构成审计、法律或投资意见。正式使用前应由专业人员复核原始年报、监管函件和底层凭证。",
        ]
    )
    return "\n".join(lines)


def result_to_markdown_bytes(result: AnalysisResult) -> bytes:
    return result_to_markdown(result).encode("utf-8")


def _register_chinese_font() -> str:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab 未安装，无法生成 PDF。")

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"
    except Exception:
        pass

    candidates = [
        Path("C:/Windows/Fonts/msyh.ttf"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("ChineseFont", str(path)))
            return "ChineseFont"
        except Exception:
            continue
    return "Helvetica"


def _wrap_text(text: str, width: int = 42) -> str:
    text = text.replace("\n", " ").strip()
    if not text:
        return ""
    return "<br/>".join(textwrap.wrap(text, width=width, break_long_words=True))


def result_to_pdf_bytes(result: AnalysisResult) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("未安装 reportlab，暂不能生成 PDF。")

    font_name = _register_chinese_font()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CNTitle", fontName=font_name, fontSize=18, leading=24, spaceAfter=12))
    styles.add(ParagraphStyle(name="CNHeading", fontName=font_name, fontSize=13, leading=18, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="CNBody", fontName=font_name, fontSize=9.5, leading=14))
    styles.add(ParagraphStyle(name="CNSmall", fontName=font_name, fontSize=8, leading=11))

    story = [
        Paragraph("问询前哨分析报告", styles["CNTitle"]),
        Paragraph(f"公司：{result.snapshot.company_name}", styles["CNBody"]),
        Paragraph(f"报告期：{result.snapshot.report_period}", styles["CNBody"]),
        Paragraph(f"来源文件：{result.document.source_name}", styles["CNBody"]),
        Paragraph(f"生成模式：{result.generated_by}", styles["CNBody"]),
        Spacer(1, 8),
        Paragraph("总体结论", styles["CNHeading"]),
        Paragraph(_wrap_text(result.summary, 58), styles["CNBody"]),
        Spacer(1, 8),
        Paragraph("风险明细", styles["CNHeading"]),
    ]

    table_data = [["风险类型", "等级", "分数", "核心证据", "建议问询"]]
    for finding in result.findings:
        questions = finding.llm_questions or finding.suggested_question
        table_data.append(
            [
                Paragraph(_wrap_text(finding.title, 10), styles["CNSmall"]),
                Paragraph(finding.severity, styles["CNSmall"]),
                Paragraph(f"{finding.score:.1f}", styles["CNSmall"]),
                Paragraph(_wrap_text("；".join(finding.evidence), 26), styles["CNSmall"]),
                Paragraph(_wrap_text("；".join(questions[:2]), 26), styles["CNSmall"]),
            ]
        )

    table = Table(table_data, colWidths=[74, 32, 34, 180, 180], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph("证据链", styles["CNHeading"]))
    for finding in result.findings:
        for reference in finding.evidence_references[:2]:
            location = f"第{reference.page}页" if reference.page else "指标复核表"
            story.append(
                Paragraph(
                    _wrap_text(f"{finding.title}｜{location}｜{reference.quote}", 92),
                    styles["CNSmall"],
                )
            )
    story.append(Spacer(1, 10))
    story.append(Paragraph("免责声明", styles["CNHeading"]))
    story.append(
        Paragraph(
            "本报告由AI生成，仅用于课程、竞赛和内部辅助分析，不构成审计、法律或投资意见。正式使用前应由专业人员复核。",
            styles["CNBody"],
        )
    )
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def diagnostics_to_frame(diagnostics: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"指标": "文本字符数", "结果": diagnostics.get("text_chars", 0), "说明": "PDF/TXT 成功提取出的文本长度"},
            {"指标": "文本页数", "结果": diagnostics.get("text_pages", 0), "说明": "原始文件页数或文本页数"},
            {"指标": "文件类型", "结果": diagnostics.get("document_type", "未知"), "说明": "摘要版通常不含完整附注和明细科目"},
            {"指标": "抽取字段数量", "结果": diagnostics.get("filled_fields", 0), "说明": "年报或手工录入中成功获得的核心字段数"},
            {"指标": "正文风险信号", "结果": diagnostics.get("text_signal_count", 0), "说明": "从年报正文识别出的待核查风险表述"},
            {"指标": "抽取状态", "结果": diagnostics.get("extraction_status", "未知"), "说明": "字段少时不能直接解释为企业无风险"},
            {"指标": "风险规则触发数", "结果": diagnostics.get("finding_count", 0), "说明": "进入报告的风险点数量"},
            {"指标": "证据覆盖率", "结果": diagnostics.get("evidence_coverage", "0%"), "说明": "每个风险点是否有可复核证据"},
            {"指标": "页码证据覆盖率", "结果": diagnostics.get("page_evidence_coverage", "0%"), "说明": "风险点是否能定位到年报页码"},
            {"指标": "证据链条数", "结果": diagnostics.get("evidence_reference_count", 0), "说明": "原文摘录或指标复核证据的数量"},
            {"指标": "案例匹配覆盖率", "结果": diagnostics.get("case_coverage", "0%"), "说明": "每个风险点是否匹配到相似监管案例"},
            {"指标": "结构化输出", "结果": "通过", "说明": "支持 JSON、CSV、Markdown、PDF 下载"},
        ]
    )
