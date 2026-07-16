"""Generic Report exporters (PRD Section 14: "PDF for presentation, Excel for audit and
custom analysis, CSV/JSON for data portability"; Phase 7).

Every exporter operates on the generic `reporting.Report` model rather than one of the
twelve report types specifically -- a `Report` is just a title, `ReportMetadata`, and a
list of `ReportSection(heading, rows)`, so the same four functions serve all twelve.

Decimal values are converted to plain strings for CSV/JSON (exact, no float rounding --
these formats are for data portability/audit trail fidelity) and to native floats for
Excel/PDF (Section 14 calls Excel out for "custom analysis," which implies computable
cells; this conversion is presentation-only and the engine itself never reads these
exported cells back in).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .reporting import Report


class _ReportJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


def export_json(report: Report) -> str:
    payload = {
        "title": report.title,
        "metadata": {
            "model_date": report.metadata.model_date.isoformat(),
            "scenario_name": report.metadata.scenario_name,
            "model_version": report.metadata.model_version,
            "assumptions_note": report.metadata.assumptions_note,
        },
        "sections": [{"heading": section.heading, "rows": section.rows} for section in report.sections],
    }
    return json.dumps(payload, indent=2, cls=_ReportJSONEncoder)


def export_csv(report: Report) -> str:
    """One block per section, separated by a blank line -- CSV has no native concept of
    multiple tables in a single file, and Section 14 doesn't require one file per
    section."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Report", report.title])
    writer.writerow(["Model date", report.metadata.model_date.isoformat()])
    writer.writerow(["Scenario", report.metadata.scenario_name])
    writer.writerow(["Model version", report.metadata.model_version])
    writer.writerow(["Assumptions", report.metadata.assumptions_note])
    for section in report.sections:
        writer.writerow([])
        writer.writerow([section.heading])
        if not section.rows:
            continue
        columns = list(section.rows[0].keys())
        writer.writerow(columns)
        for row in section.rows:
            writer.writerow([row.get(column, "") for column in columns])
    return buffer.getvalue()


def _excel_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    return value


def export_excel(report: Report) -> bytes:
    """One sheet per section plus a leading Metadata sheet carrying the Section 12
    model date/scenario/version/assumptions requirement. Sheet names are truncated to
    Excel's 31-character limit and de-duplicated if that truncation collides."""
    workbook = Workbook()
    metadata_sheet = workbook.active
    metadata_sheet.title = "Metadata"
    metadata_sheet.append(["Report", report.title])
    metadata_sheet.append(["Model date", report.metadata.model_date])
    metadata_sheet.append(["Scenario", report.metadata.scenario_name])
    metadata_sheet.append(["Model version", report.metadata.model_version])
    metadata_sheet.append(["Assumptions", report.metadata.assumptions_note])

    used_names = {"Metadata"}
    for section in report.sections:
        base_name = section.heading[:31] or "Section"
        name = base_name
        suffix = 1
        while name in used_names:
            suffix += 1
            name = f"{base_name[:28]}~{suffix}"
        used_names.add(name)
        sheet = workbook.create_sheet(title=name)
        if section.rows:
            columns = list(section.rows[0].keys())
            sheet.append(columns)
            for row in section.rows:
                sheet.append([_excel_value(row.get(column)) for column in columns])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _pdf_value(value: object) -> str:
    return "" if value is None else str(value)


def export_pdf(report: Report) -> bytes:
    """Title/metadata block followed by one table per section, satisfying Section 12's
    "model date, scenario name, assumptions, and model version" display requirement."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(report.title, styles["Title"]),
        Paragraph(
            f"Model date: {report.metadata.model_date} | Scenario: {report.metadata.scenario_name} | "
            f"Model version: {report.metadata.model_version}",
            styles["Normal"],
        ),
        Paragraph(report.metadata.assumptions_note, styles["Italic"]),
        Spacer(1, 12),
    ]
    for section in report.sections:
        story.append(Paragraph(section.heading, styles["Heading2"]))
        if section.rows:
            columns = list(section.rows[0].keys())
            data = [columns] + [[_pdf_value(row.get(column)) for column in columns] for row in section.rows]
            table = Table(data, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ]
                )
            )
            story.append(table)
        story.append(Spacer(1, 12))
    doc.build(story)
    return buffer.getvalue()
