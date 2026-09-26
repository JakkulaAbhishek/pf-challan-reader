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
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("Missing dependency. Install with:  pip install openpyxl")


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


def write_excel(records, out_path):
    records = sorted(
        records,
        key=lambda r: (r.get("wage_year") or 0, r.get("wage_month_num") or 0),
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "EPF Challan Summary"

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
    ws.append(headers)

    header_font = Font(bold=True, name="Arial", color="FFFFFF")
    header_fill = PatternFill(start_color="305496", end_color="305496", fill_type="solid")
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

    allowed_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    disallowed_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    normal_font = Font(name="Arial")

    row_idx = 2
    for r in records:
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
        ws.append(row)

        status_cell = ws.cell(row=row_idx, column=headers.index("Status") + 1)
        if r.get("status") == "Allowed":
            status_cell.fill = allowed_fill
        elif r.get("status") == "Disallowed":
            status_cell.fill = disallowed_fill

        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=row_idx, column=col_idx).font = normal_font

        for col_name in ("Administration Charges", "Employer's Share Total",
                          "Employee's Share Total", "Grand Total", "EPF Wages"):
            c = ws.cell(row=row_idx, column=headers.index(col_name) + 1)
            c.number_format = "#,##0.00"

        row_idx += 1

    # Totals row
    total_row = row_idx
    ws.cell(row=total_row, column=1, value="TOTAL").font = Font(bold=True, name="Arial")
    for col_name in ("Administration Charges", "Employer's Share Total",
                      "Employee's Share Total", "Grand Total"):
        col_letter = get_column_letter(headers.index(col_name) + 1)
        cell = ws.cell(row=total_row, column=headers.index(col_name) + 1)
        cell.value = f"=SUM({col_letter}2:{col_letter}{row_idx - 1})"
        cell.font = Font(bold=True, name="Arial")
        cell.number_format = "#,##0.00"

    # Column widths
    widths = [14, 16, 26, 12, 12, 12, 10, 12, 14, 16, 16, 12, 18, 14, 14, 12, 30, 6]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    # Notes sheet
    notes = wb.create_sheet("Notes")
    notes["A1"] = "Notes"
    notes["A1"].font = Font(bold=True, size=14, name="Arial")
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
    ]
    for i, line in enumerate(notes_text, start=2):
        notes.cell(row=i, column=1, value=line).font = Font(name="Arial")
    notes.column_dimensions["A"].width = 120

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
