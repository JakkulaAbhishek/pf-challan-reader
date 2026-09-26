#!/usr/bin/env python3
"""
EPF Combined Challan Extractor
================================
Reads one or more EPFO "Combined Challan of A/C No. 01, 02, 10, 21 & 22"
PDF files (the kind downloaded from unifiedportal-emp.epfindia.gov.in) and
extracts, per wage month:

    - Establishment code & name
    - TRRN / ECR Id / LIN
    - Wage month
    - Total subscribers & total wages (EPF / EPS / EDLI)
    - Administration Charges (total)
    - Employer's Share (total)
    - Employee's Share (total)
    - Grand Total
    - Date the challan was generated (system generated date)
    - Statutory due date (15th of the month following the wage month)
    - Deposit status: "Allowed" / "Disallowed"
      (flags late deposit of employee's contribution, relevant for
       disallowance under Sec 36(1)(va) r.w.s 2(24)(x) of the
       Income-tax Act, 1961)

Output: a single, formatted .xlsx workbook with one row per challan
(one PDF can contain many challans/pages - e.g. one per month).

USAGE
-----
    python epf_challan_extractor.py <input_path> [-o OUTPUT.xlsx]

    <input_path> can be:
        - a single PDF file, or
        - a folder containing multiple PDF files (all *.pdf are scanned)

EXAMPLES
--------
    python epf_challan_extractor.py challan.pdf
    python epf_challan_extractor.py ./challans_folder -o epf_summary.xlsx

DEPENDENCIES
------------
    pip install pdfplumber openpyxl

NOTE ON THE "ALLOWED/DISALLOWED" COLUMN
----------------------------------------
The PDF only tells us the date the *challan* was system-generated from the
uploaded ECR - it is not proof of the actual bank remittance date. This
script uses the challan-generation date as the best available proxy for
the deposit date, and compares it against the statutory due date (15 days
from the end of the wage month, per EPF Scheme para 38). Verify the real
bank payment/UTR date before relying on this for a tax audit report -
see the "Note" column in the output for this caveat.

Output workbook has three sheets:
    1. "EPF Challan Summary" - colour-coded, one row per challan
    2. "Dashboard"            - KPI cards + charts (trend, contribution
                                 mix, subscriber growth, compliance)
    3. "Notes"                - methodology / caveats

--------------------------------------------------------------------
Author   : Jakkula Abhishek
Email    : jakkulaabhishek5@gmail.com
--------------------------------------------------------------------
"""

import argparse
import glob
import os
import re
import sys
from calendar import monthrange
from datetime import date, datetime

try:
    import pdfplumber
except ImportError:
    sys.exit("Missing dependency. Install with:  pip install pdfplumber")

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.formatting.rule import CellIsRule
except ImportError:
    sys.exit("Missing dependency. Install with:  pip install openpyxl")

AUTHOR_NAME = "Jakkula Abhishek"
AUTHOR_EMAIL = "jakkulaabhishek5@gmail.com"
BRAND_TITLE = "EPF Challan Compliance & Analytics Report"

# Brand colour palette
CLR_PRIMARY = "1F4E78"     # deep blue - title band
CLR_ACCENT = "2E75B6"      # medium blue - header row
CLR_ACCENT2 = "9DC3E6"     # light blue - sub headers
CLR_GOLD = "FFC000"        # gold - branding highlight
CLR_GREEN = "C6EFCE"       # allowed
CLR_GREEN_TXT = "006100"
CLR_RED = "FFC7CE"         # disallowed
CLR_RED_TXT = "9C0006"
CLR_BAND = "EDF3FB"        # light banding for alternate rows
CLR_WHITE = "FFFFFF"


MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11,
    "DECEMBER": 12,
}

NUM_RE = r"[\d,]+(?:\.\d+)?"


def _num(s):
    """Convert a string like '1,23,456' or '0' to a float. Returns None if blank."""
    if s is None:
        return None
    s = s.replace(",", "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_challan_text(text, source_file, page_no):
    """Extract one challan's fields from a single page of extracted text.

    Returns a dict, or None if this page doesn't look like a challan page.
    """
    if "EMPLOYEES' PROVIDENT FUND ORGANISATION" not in text.upper():
        return None

    rec = {"source_file": source_file, "page": page_no}

    def find(pattern, group=1, flags=0, cast=str):
        m = re.search(pattern, text, flags)
        if not m:
            return None
        val = m.group(group)
        return cast(val) if val is not None else None

    rec["trrn"] = find(r"TRRN\s*([0-9]+)")
    rec["ecr_id"] = find(r"ECR\s*Id\s*([0-9]+)")
    rec["lin"] = find(r"LIN\s*:?\s*([0-9]+)")

    m = re.search(
        r"Establishment Code\s*&\s*Name\s+(\S+)\s+(.*?)\s+Dues for the wage month",
        text, re.DOTALL,
    )
    rec["establishment_code"] = m.group(1) if m else None
    rec["establishment_name"] = re.sub(r"\s+", " ", m.group(2)).strip() if m else None

    m = re.search(
        r"Dues for the wage month of\s*([A-Za-z]+)\s*([0-9]{4})", text
    )
    if m:
        month_name = m.group(1).upper()
        year = int(m.group(2))
        month_num = MONTHS.get(month_name)
        rec["wage_month"] = f"{month_name.title()} {year}"
        rec["wage_month_num"] = month_num
        rec["wage_year"] = year
    else:
        rec["wage_month"] = None
        rec["wage_month_num"] = None
        rec["wage_year"] = None

    m = re.search(
        r"Total Subscribers\s*:\s*(\d+)\s+(\d+)\s+(\d+)", text
    )
    if m:
        rec["subscribers_epf"], rec["subscribers_eps"], rec["subscribers_edli"] = (
            int(m.group(1)), int(m.group(2)), int(m.group(3))
        )
    else:
        rec["subscribers_epf"] = rec["subscribers_eps"] = rec["subscribers_edli"] = None

    m = re.search(
        rf"Total Wages\s*:\s*({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})", text
    )
    if m:
        rec["wages_epf"] = _num(m.group(1))
        rec["wages_eps"] = _num(m.group(2))
        rec["wages_edli"] = _num(m.group(3))
    else:
        rec["wages_epf"] = rec["wages_eps"] = rec["wages_edli"] = None

    # Particulars rows - last number on the line is the row's TOTAL column.
    m = re.search(
        rf"1\s+Administration Charges\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})",
        text,
    )
    rec["admin_charges_total"] = _num(m.group(6)) if m else None

    m = re.search(
        rf"2\s+Employer's Share Of\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})",
        text,
    )
    rec["employer_share_total"] = _num(m.group(6)) if m else None

    m = re.search(
        rf"3\s+Employee's Share Of\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})\s+({NUM_RE})",
        text,
    )
    rec["employee_share_total"] = _num(m.group(6)) if m else None

    m = re.search(rf"Grand Total\s*:.*?({NUM_RE})\s*$", text, re.MULTILINE)
    rec["grand_total"] = _num(m.group(1)) if m else None

    m = re.search(
        r"generated challan on\s*(\d{2}-[A-Z]{3}-\d{4})\s+([\d:]+)", text
    )
    if m:
        try:
            rec["generated_on"] = datetime.strptime(
                f"{m.group(1)} {m.group(2)}", "%d-%b-%Y %H:%M"
            )
        except ValueError:
            rec["generated_on"] = None
    else:
        rec["generated_on"] = None

    # Statutory due date: 15 days from the close of the wage month
    # (EPF Scheme 1952, para 38 - contributions payable within 15 days
    # of the close of the month).
    if rec["wage_month_num"] and rec["wage_year"]:
        last_day = monthrange(rec["wage_year"], rec["wage_month_num"])[1]
        month_end = date(rec["wage_year"], rec["wage_month_num"], last_day)
        # add 15 days, rolling into the next month correctly
        due = date.fromordinal(month_end.toordinal() + 15)
        rec["due_date"] = due
    else:
        rec["due_date"] = None

    # Allowed / Disallowed status - compares challan-generation date to
    # the statutory due date. See module docstring for the caveat.
    if rec["generated_on"] and rec["due_date"]:
        if rec["generated_on"].date() <= rec["due_date"]:
            rec["status"] = "Allowed"
        else:
            rec["status"] = "Disallowed"
    else:
        rec["status"] = "Unknown"

    return rec


def extract_from_pdf(path):
    records = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            rec = parse_challan_text(text, os.path.basename(path), i)
            if rec:
                records.append(rec)
    return records


def gather_pdfs(input_path):
    if os.path.isdir(input_path):
        return sorted(glob.glob(os.path.join(input_path, "*.pdf")))
    if os.path.isfile(input_path) and input_path.lower().endswith(".pdf"):
        return [input_path]
    sys.exit(f"'{input_path}' is not a PDF file or a folder containing PDFs.")


def _thin_border():
    side = Side(style="thin", color="B4C6E7")
    return Border(left=side, right=side, top=side, bottom=side)


def _brand_banner(ws, ncols, subtitle):
    """Draws the two-row coloured branding banner used on every sheet."""
    last_col = get_column_letter(ncols)
    ws.merge_cells(f"A1:{last_col}1")
    ws.merge_cells(f"A2:{last_col}2")

    title_cell = ws["A1"]
    title_cell.value = BRAND_TITLE.upper()
    title_cell.font = Font(bold=True, size=18, name="Arial", color=CLR_WHITE)
    title_cell.fill = PatternFill(start_color=CLR_PRIMARY, end_color=CLR_PRIMARY, fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 34

    sub_cell = ws["A2"]
    sub_cell.value = subtitle
    sub_cell.font = Font(bold=True, italic=True, size=11, name="Arial", color=CLR_PRIMARY)
    sub_cell.fill = PatternFill(start_color=CLR_GOLD, end_color=CLR_GOLD, fill_type="solid")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20


def _kpi_card(ws, row, col, label, value, number_format, fill_color):
    """Draws a 2-row-tall, 2-col-wide coloured KPI card starting at (row, col)."""
    c1 = get_column_letter(col)
    c2 = get_column_letter(col + 1)
    ws.merge_cells(f"{c1}{row}:{c2}{row}")
    ws.merge_cells(f"{c1}{row + 1}:{c2}{row + 1}")

    label_cell = ws[f"{c1}{row}"]
    label_cell.value = label
    label_cell.font = Font(bold=True, size=10, name="Arial", color=CLR_WHITE)
    label_cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
    label_cell.alignment = Alignment(horizontal="center", vertical="center")

    value_cell = ws[f"{c1}{row + 1}"]
    value_cell.value = value
    value_cell.number_format = number_format
    value_cell.font = Font(bold=True, size=16, name="Arial", color=CLR_PRIMARY)
    value_cell.fill = PatternFill(start_color=CLR_WHITE, end_color=CLR_WHITE, fill_type="solid")
    value_cell.alignment = Alignment(horizontal="center", vertical="center")
    value_cell.border = _thin_border()
    ws.row_dimensions[row].height = 16
    ws.row_dimensions[row + 1].height = 26


def write_excel(records, out_path):
    records = sorted(
        records,
        key=lambda r: (r.get("wage_year") or 0, r.get("wage_month_num") or 0),
    )

    headers = [
        "Wage Month", "Establishment Code", "Establishment Name",
        "TRRN", "ECR Id", "LIN",
        "EPF Subscribers", "EPF Wages",
        "Administration Charges", "Employer's Share Total",
        "Employee's Share Total", "Grand Total",
        "Challan Generated On", "Statutory Due Date",
        "Days Late (+) / Early (-)", "Status",
        "Source File", "Page",
    ]
    ncols = len(headers)

    TITLE_ROW, SUBTITLE_ROW, HEADER_ROW, DATA_START_ROW = 1, 2, 4, 5

    wb = Workbook()
    ws = wb.active
    ws.title = "EPF Challan Summary"

    _brand_banner(
        ws, ncols,
        f"Prepared by {AUTHOR_NAME}   |   {AUTHOR_EMAIL}   |   "
        f"Generated {datetime.now().strftime('%d-%b-%Y')}",
    )

    header_font = Font(bold=True, name="Arial", color=CLR_WHITE, size=11)
    header_fill = PatternFill(start_color=CLR_ACCENT, end_color=CLR_ACCENT, fill_type="solid")
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _thin_border()
    ws.row_dimensions[HEADER_ROW].height = 30
    ws.freeze_panes = f"A{DATA_START_ROW}"

    allowed_fill = PatternFill(start_color=CLR_GREEN, end_color=CLR_GREEN, fill_type="solid")
    disallowed_fill = PatternFill(start_color=CLR_RED, end_color=CLR_RED, fill_type="solid")
    band_fill = PatternFill(start_color=CLR_BAND, end_color=CLR_BAND, fill_type="solid")
    normal_font = Font(name="Arial", size=10)
    border = _thin_border()

    row_idx = DATA_START_ROW
    for i, r in enumerate(records):
        days_diff = None
        if r["generated_on"] and r["due_date"]:
            days_diff = (r["generated_on"].date() - r["due_date"]).days

        row = [
            r.get("wage_month"),
            r.get("establishment_code"),
            r.get("establishment_name"),
            r.get("trrn"),
            r.get("ecr_id"),
            r.get("lin"),
            r.get("subscribers_epf"),
            r.get("wages_epf"),
            r.get("admin_charges_total"),
            r.get("employer_share_total"),
            r.get("employee_share_total"),
            r.get("grand_total"),
            r["generated_on"].strftime("%d-%b-%Y %H:%M") if r.get("generated_on") else None,
            r["due_date"].strftime("%d-%b-%Y") if r.get("due_date") else None,
            days_diff,
            r.get("status"),
            r.get("source_file"),
            r.get("page"),
        ]
        for col_idx, val in enumerate(row, start=1):
            c = ws.cell(row=row_idx, column=col_idx, value=val)
            c.font = normal_font
            c.border = border
            c.alignment = Alignment(horizontal="center", vertical="center")
            if i % 2 == 1:
                c.fill = band_fill

        status_cell = ws.cell(row=row_idx, column=headers.index("Status") + 1)
        status_cell.font = Font(name="Arial", size=10, bold=True,
                                 color=CLR_GREEN_TXT if r.get("status") == "Allowed" else CLR_RED_TXT)
        if r.get("status") == "Allowed":
            status_cell.fill = allowed_fill
        elif r.get("status") == "Disallowed":
            status_cell.fill = disallowed_fill

        for col_name in ("Administration Charges", "Employer's Share Total",
                          "Employee's Share Total", "Grand Total", "EPF Wages"):
            c = ws.cell(row=row_idx, column=headers.index(col_name) + 1)
            c.number_format = "#,##0.00"

        row_idx += 1

    last_data_row = row_idx - 1

    # Totals row
    total_row = row_idx
    total_fill = PatternFill(start_color=CLR_ACCENT2, end_color=CLR_ACCENT2, fill_type="solid")
    tot_label = ws.cell(row=total_row, column=1, value="TOTAL")
    tot_label.font = Font(bold=True, name="Arial", color=CLR_PRIMARY)
    tot_label.fill = total_fill
    for col_idx in range(1, ncols + 1):
        ws.cell(row=total_row, column=col_idx).fill = total_fill
        ws.cell(row=total_row, column=col_idx).border = border
    for col_name in ("Administration Charges", "Employer's Share Total",
                      "Employee's Share Total", "Grand Total"):
        col_letter = get_column_letter(headers.index(col_name) + 1)
        cell = ws.cell(row=total_row, column=headers.index(col_name) + 1)
        cell.value = f"=SUM({col_letter}{DATA_START_ROW}:{col_letter}{last_data_row})"
        cell.font = Font(bold=True, name="Arial", color=CLR_PRIMARY)
        cell.number_format = "#,##0.00"

    # Column widths
    widths = [14, 16, 26, 12, 12, 12, 10, 12, 16, 18, 18, 14, 18, 14, 16, 12, 30, 6]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"

    # ------------------------------------------------------------------
    # Dashboard sheet - KPIs + charts
    # ------------------------------------------------------------------
    dash = wb.create_sheet("Dashboard")
    dash.sheet_view.showGridLines = False
    dash.page_setup.orientation = "landscape"
    dash.page_setup.fitToWidth = 1
    dash.page_setup.fitToHeight = 0
    dash.sheet_properties.pageSetUpPr.fitToPage = True
    dash_ncols = 14
    _brand_banner(
        dash, dash_ncols,
        f"Prepared by {AUTHOR_NAME}   |   {AUTHOR_EMAIL}",
    )

    n = len(records)
    total_grand = sum(r.get("grand_total") or 0 for r in records)
    total_admin = sum(r.get("admin_charges_total") or 0 for r in records)
    total_employer = sum(r.get("employer_share_total") or 0 for r in records)
    total_employee = sum(r.get("employee_share_total") or 0 for r in records)
    allowed_count = sum(1 for r in records if r.get("status") == "Allowed")
    disallowed_count = sum(1 for r in records if r.get("status") == "Disallowed")
    compliance_pct = (allowed_count / n) if n else 0

    dash["A4"] = "Key Highlights"
    dash["A4"].font = Font(bold=True, size=13, name="Arial", color=CLR_PRIMARY)
    dash.merge_cells("A4:F4")

    kpi_row = 5
    _kpi_card(dash, kpi_row, 1, "MONTHS COVERED", n, "0", CLR_PRIMARY)
    _kpi_card(dash, kpi_row, 3, "TOTAL REMITTANCE (\u20b9)", total_grand, "#,##0", CLR_ACCENT)
    _kpi_card(dash, kpi_row, 5, "EMPLOYER'S SHARE (\u20b9)", total_employer, "#,##0", "2E7D32")
    _kpi_card(dash, kpi_row, 7, "EMPLOYEE'S SHARE (\u20b9)", total_employee, "#,##0", "C55A11")
    _kpi_card(dash, kpi_row, 9, "ADMIN CHARGES (\u20b9)", total_admin, "#,##0", "7030A0")
    _kpi_card(dash, kpi_row, 11, "ON-TIME COMPLIANCE", compliance_pct, "0.0%",
              "006100" if compliance_pct >= 0.9 else CLR_RED_TXT)

    for col_idx, w in enumerate([2] * dash_ncols, start=1):
        pass  # widths set below after chart placement

    # Hidden helper table for pie chart (contribution mix) and status counts
    helper_row0 = 40
    dash.cell(row=helper_row0, column=1, value="Component").font = Font(bold=True, name="Arial")
    dash.cell(row=helper_row0, column=2, value="Amount").font = Font(bold=True, name="Arial")
    mix = [
        ("Administration Charges", total_admin),
        ("Employer's Share", total_employer),
        ("Employee's Share", total_employee),
    ]
    for i, (label, val) in enumerate(mix, start=1):
        dash.cell(row=helper_row0 + i, column=1, value=label)
        dash.cell(row=helper_row0 + i, column=2, value=val)

    status_row0 = helper_row0 + 6
    dash.cell(row=status_row0, column=1, value="Status").font = Font(bold=True, name="Arial")
    dash.cell(row=status_row0, column=2, value="Count").font = Font(bold=True, name="Arial")
    dash.cell(row=status_row0 + 1, column=1, value="Allowed")
    dash.cell(row=status_row0 + 1, column=2, value=allowed_count)
    dash.cell(row=status_row0 + 2, column=1, value="Disallowed")
    dash.cell(row=status_row0 + 2, column=2, value=disallowed_count)

    # References back into the data sheet
    data_sheet = "EPF Challan Summary"
    cat_ref = Reference(ws, min_col=1, min_row=DATA_START_ROW, max_row=last_data_row)
    month_col = headers.index("Wage Month") + 1
    admin_col = headers.index("Administration Charges") + 1
    employer_col = headers.index("Employer's Share Total") + 1
    employee_col = headers.index("Employee's Share Total") + 1
    grand_col = headers.index("Grand Total") + 1
    subs_col = headers.index("EPF Subscribers") + 1
    cats = Reference(ws, min_col=month_col, min_row=DATA_START_ROW, max_row=last_data_row)

    # Chart 1: Grand Total trend (line)
    line = LineChart()
    line.title = "Grand Total Remittance Trend (\u20b9)"
    line.style = 12
    line.y_axis.title = "Amount (\u20b9)"
    line.x_axis.title = "Wage Month"
    line.height, line.width = 9, 18
    data = Reference(ws, min_col=grand_col, min_row=HEADER_ROW, max_row=last_data_row)
    line.add_data(data, titles_from_data=True)
    line.set_categories(cats)
    for s in line.series:
        s.smooth = False
        s.marker.symbol = "circle"
        s.graphicalProperties.line.width = 25000
        s.graphicalProperties.line.solidFill = CLR_ACCENT
    dash.add_chart(line, "A9")

    # Chart 2: Employer vs Employee vs Admin (clustered bar)
    bar = BarChart()
    bar.type = "col"
    bar.grouping = "clustered"
    bar.title = "Employer vs Employee Contribution vs Admin Charges by Month"
    bar.style = 10
    bar.y_axis.title = "Amount (\u20b9)"
    bar.x_axis.title = "Wage Month"
    bar.height, bar.width = 9, 18
    for col, name, color in (
        (admin_col, "Administration Charges", "7030A0"),
        (employer_col, "Employer's Share", "2E7D32"),
        (employee_col, "Employee's Share", "C55A11"),
    ):
        d = Reference(ws, min_col=col, min_row=HEADER_ROW, max_row=last_data_row)
        bar.add_data(d, titles_from_data=True)
    bar.set_categories(cats)
    for s, color in zip(bar.series, ("7030A0", "2E7D32", "C55A11")):
        s.graphicalProperties.solidFill = color
    dash.add_chart(bar, "A28")

    # Chart 3: Contribution mix (pie)
    pie = PieChart()
    pie.title = "Overall Contribution Mix"
    pie.height, pie.width = 9, 10
    pie_data = Reference(dash, min_col=2, min_row=helper_row0, max_row=helper_row0 + 3)
    pie_cats = Reference(dash, min_col=1, min_row=helper_row0 + 1, max_row=helper_row0 + 3)
    pie.add_data(pie_data, titles_from_data=True)
    pie.set_categories(pie_cats)
    pie.dataLabels = DataLabelList()
    pie.dataLabels.showPercent = True
    dash.add_chart(pie, "N9")

    # Chart 4: Subscriber growth (bar)
    subs_bar = BarChart()
    subs_bar.type = "col"
    subs_bar.title = "EPF Subscriber Count by Month"
    subs_bar.style = 11
    subs_bar.y_axis.title = "Subscribers"
    subs_bar.x_axis.title = "Wage Month"
    subs_bar.height, subs_bar.width = 9, 10
    subs_data = Reference(ws, min_col=subs_col, min_row=HEADER_ROW, max_row=last_data_row)
    subs_bar.add_data(subs_data, titles_from_data=True)
    subs_bar.set_categories(cats)
    for s in subs_bar.series:
        s.graphicalProperties.solidFill = CLR_GOLD
    dash.add_chart(subs_bar, "N28")

    # Chart 5: Compliance status (bar)
    comp_bar = BarChart()
    comp_bar.type = "col"
    comp_bar.title = "Deposit Compliance: Allowed vs Disallowed"
    comp_bar.style = 10
    comp_bar.y_axis.title = "No. of Months"
    comp_bar.height, comp_bar.width = 9, 10
    comp_data = Reference(dash, min_col=2, min_row=status_row0, max_row=status_row0 + 2)
    comp_cats = Reference(dash, min_col=1, min_row=status_row0 + 1, max_row=status_row0 + 2)
    comp_bar.add_data(comp_data, titles_from_data=True)
    comp_bar.set_categories(comp_cats)
    dash.add_chart(comp_bar, "V9")

    for col_idx in range(1, dash_ncols + 1):
        dash.column_dimensions[get_column_letter(col_idx)].width = 11

    # ------------------------------------------------------------------
    # Notes sheet
    # ------------------------------------------------------------------
    notes = wb.create_sheet("Notes")
    notes.sheet_view.showGridLines = False
    notes.page_setup.orientation = "landscape"
    notes.page_setup.fitToWidth = 1
    notes.page_setup.fitToHeight = 0
    notes.sheet_properties.pageSetUpPr.fitToPage = True
    _brand_banner(notes, 6, f"Prepared by {AUTHOR_NAME}   |   {AUTHOR_EMAIL}")
    notes["A4"] = "Methodology & Notes"
    notes["A4"].font = Font(bold=True, size=13, name="Arial", color=CLR_PRIMARY)
    notes_text = [
        "",
        "1. 'Challan Generated On' is the date EPFO's system generated the challan from the"
        " employer's uploaded ECR - it is NOT proof of actual bank payment/remittance date.",
        "2. 'Statutory Due Date' = 15 days from the end of the wage month"
        " (EPF Scheme 1952, Para 38).",
        "3. 'Status' (Allowed/Disallowed) compares the challan-generation date to the due date,"
        " as a proxy for timeliness of deposit. This is relevant to the disallowance of"
        " employees' PF contribution under Section 36(1)(va) read with Section 2(24)(x) of the"
        " Income-tax Act, 1961, where the employees' share must be deposited by the due date"
        " under the relevant Act to be allowed as a deduction.",
        "4. Before relying on this for a tax audit / Form 3CD report, please verify the actual"
        " date of remittance (bank UTR / payment date) - it can differ from the challan"
        " generation date shown here.",
        "",
        f"Report prepared by: {AUTHOR_NAME}  ({AUTHOR_EMAIL})",
    ]
    for i, line_txt in enumerate(notes_text, start=6):
        cell = notes.cell(row=i, column=1, value=line_txt)
        cell.font = Font(name="Arial", bold=line_txt.startswith("Report prepared"))
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    notes.column_dimensions["A"].width = 130

    wb.save(out_path)


def main():
    parser = argparse.ArgumentParser(description="Extract EPF combined challan data to Excel.")
    parser.add_argument("input_path", help="A PDF file, or a folder containing PDF files.")
    parser.add_argument(
        "-o", "--output", default="epf_challan_summary.xlsx",
        help="Output .xlsx path (default: epf_challan_summary.xlsx)",
    )
    args = parser.parse_args()

    pdf_files = gather_pdfs(args.input_path)
    if not pdf_files:
        sys.exit("No PDF files found.")

    all_records = []
    for pdf_path in pdf_files:
        recs = extract_from_pdf(pdf_path)
        if not recs:
            print(f"  [warning] no challans found in {pdf_path}", file=sys.stderr)
        all_records.extend(recs)

    if not all_records:
        sys.exit("No challan data could be extracted from the given file(s).")

    write_excel(all_records, args.output)
    print(f"Done. Extracted {len(all_records)} challan(s) from {len(pdf_files)} PDF(s).")
    print(f"Output written to: {args.output}")


if __name__ == "__main__":
    main()
