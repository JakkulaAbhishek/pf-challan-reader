import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
import plotly.express as px
from fpdf import FPDF
import logging
from typing import Optional, Dict, List, Tuple
import traceback
import warnings

# Suppress pandas deprecation warnings
warnings.filterwarnings('ignore', category=FutureWarning)

# ---------------- LOGGING CONFIG ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="PF AI Command Center", layout="wide", page_icon="📊")

# ---------------- ULTRA STYLISH UI (GLASSMORPHISM + ANIMATIONS) ----------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    scroll-behavior: smooth;
}

.stApp {
    background: linear-gradient(-45deg, #f0f9ff, #e6f0fa, #d9e9f5, #e6f0fa);
    background-size: 400% 400%;
    animation: gradientBG 15s ease infinite;
}

@keyframes gradientBG {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

@media (prefers-color-scheme: dark) {
    .stApp {
        background: linear-gradient(-45deg, #0b1a2e, #102a3c, #1a3f54, #102a3c);
        background-size: 400% 400%;
        animation: gradientBG 15s ease infinite;
    }
}

.glass-card {
    backdrop-filter: blur(10px);
    background: rgba(255, 255, 255, 0.25);
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.4);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
    padding: 2rem;
    margin-bottom: 2rem;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.glass-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
}

@media (prefers-color-scheme: dark) {
    .glass-card {
        background: rgba(20, 40, 60, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
}

.header-card {
    text-align: center;
    padding: 2.5rem 2rem;
    background: rgba(255, 255, 255, 0.3);
    backdrop-filter: blur(12px);
    border-radius: 30px;
    border: 1px solid rgba(255, 255, 255, 0.5);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}

.header-card::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(37, 99, 235, 0.1) 0%, transparent 70%);
    animation: rotate 20s linear infinite;
}

@keyframes rotate {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.main-title {
    font-weight: 800;
    font-size: 3rem;
    background: linear-gradient(135deg, #2563eb, #0ea5e9, #7c3aed);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shimmer 3s infinite;
    background-size: 200% auto;
}

@keyframes shimmer {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

.subtitle {
    font-size: 1.2rem;
    font-weight: 600;
    color: #1e293b;
    opacity: 0.8;
    letter-spacing: 1px;
}

@media (prefers-color-scheme: dark) {
    .subtitle { color: #e2e8f0; }
}

[data-testid="stMetric"] {
    background: rgba(255, 255, 255, 0.25);
    backdrop-filter: blur(8px);
    border-radius: 20px;
    padding: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.3);
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
    transition: all 0.3s ease;
}

[data-testid="stMetric"]:hover {
    transform: scale(1.02);
    background: rgba(255, 255, 255, 0.35);
    border-color: rgba(37, 99, 235, 0.5);
}

[data-testid="stMetricLabel"] {
    font-weight: 600;
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #1e293b;
}

[data-testid="stMetricValue"] {
    font-weight: 800;
    font-size: 2.2rem;
    color: #0f172a;
}

@media (prefers-color-scheme: dark) {
    [data-testid="stMetricLabel"] { color: #cbd5e1; }
    [data-testid="stMetricValue"] { color: #f1f5f9; }
}

.stButton > button {
    background: linear-gradient(135deg, #2563eb, #0ea5e9, #7c3aed);
    background-size: 200% auto;
    color: white;
    border: none;
    border-radius: 40px;
    padding: 0.75rem 2rem;
    font-weight: 700;
    font-size: 1rem;
    letter-spacing: 0.5px;
    box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3);
    transition: all 0.4s ease;
    border: 1px solid rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(4px);
    width: 100%;
}

.stButton > button:hover {
    transform: translateY(-3px) scale(1.02);
    box-shadow: 0 8px 25px rgba(37, 99, 235, 0.5);
    background-position: right center;
}

[data-testid="stFileUploader"] {
    background: rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(8px);
    border-radius: 20px;
    padding: 1.5rem;
    border: 2px dashed rgba(37, 99, 235, 0.5);
    transition: all 0.3s ease;
}

[data-testid="stFileUploader"]:hover {
    border-color: #2563eb;
    background: rgba(255, 255, 255, 0.3);
}

[data-testid="stDataFrame"] {
    background: rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(8px);
    border-radius: 20px;
    padding: 1rem;
    border: 1px solid rgba(255, 255, 255, 0.3);
}

.js-plotly-plot .plotly, .plotly {
    background: transparent !important;
}

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: rgba(0,0,0,0.05); border-radius: 10px; }
::-webkit-scrollbar-thumb { background: linear-gradient(135deg, #2563eb, #0ea5e9); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: #2563eb; }

.footer {
    text-align: center;
    margin-top: 3rem;
    font-size: 0.9rem;
    opacity: 0.7;
    color: #1e293b;
    padding: 1rem;
    border-top: 1px solid rgba(0,0,0,0.1);
}

@media (prefers-color-scheme: dark) { .footer { color: #cbd5e1; } }

.success-box {
    background: linear-gradient(135deg, #10b981, #059669);
    color: white;
    padding: 1rem;
    border-radius: 12px;
    margin: 1rem 0;
    border-left: 4px solid #047857;
}

.error-box {
    background: linear-gradient(135deg, #ef4444, #dc2626);
    color: white;
    padding: 1rem;
    border-radius: 12px;
    margin: 1rem 0;
    border-left: 4px solid #b91c1c;
}

.warning-box {
    background: linear-gradient(135deg, #f59e0b, #d97706);
    color: white;
    padding: 1rem;
    border-radius: 12px;
    margin: 1rem 0;
    border-left: 4px solid #b45309;
}
</style>
""", unsafe_allow_html=True)

# ---------------- HEADER ----------------
st.markdown("""
<div class="header-card">
    <div class="main-title">🏢 PF CHALLAN AI COMMAND CENTER</div>
    <div class="subtitle">Enterprise Statutory Audit Suite • Dual PDF Format Support</div>
    <div style="margin-top:1rem; font-style:italic; opacity:0.7;">
        🌸 कर्मण्येवाधिकारस्ते मा फलेषु कदाचन 🌸
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------- HELPER FUNCTIONS ----------------

def parse_indian_number(value) -> float:
    """Parse Indian number format with commas"""
    if value is None:
        return 0.0
    value_str = str(value).strip()
    if not value_str or value_str.lower() in ["na", "n/a", "-", ""]:
        return 0.0
    try:
        cleaned = re.sub(r'[,\s]', '', value_str)
        if not cleaned:
            return 0.0
        return float(cleaned)
    except (ValueError, AttributeError, TypeError):
        logger.warning(f"Failed to parse number: '{value}'")
        return 0.0


def extract_wage_month(text: str) -> str:
    """Extract wage month supporting both PDF formats"""
    patterns = [
        r"wage month\s+of\s+([A-Za-z]+)\s+(\d{4})",
        r"wage month:\s*([A-Za-z]+)\s+(\d{4})",
        r"FOR WAGE MONTH:\s*([A-Za-z]+)\s+(\d{4})",
        r"for the wage month\s+([A-Za-z]+)\s+(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            month = match.group(1).strip().title()
            year = match.group(2).strip()
            return f"{month} {year}"
    
    # Fallback pattern
    fallback = re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b', text, re.I)
    if fallback:
        month = fallback.group(1).strip().title()
        year = fallback.group(2).strip()
        return f"{month} {year}"
    return "Unknown"


def calculate_due_date(wage_month_str: str) -> Optional[datetime]:
    """Calculate statutory due date (15th of next month)"""
    try:
        parts = wage_month_str.split()
        if len(parts) < 2:
            return None
        month_name = parts[0]
        year = int(parts[1])
        
        month_map = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
            'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12,
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'Jun': 6, 'Jul': 7, 'Aug': 8, 
            'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        month_num = month_map.get(month_name)
        if not month_num:
            return None
        next_month = month_num % 12 + 1
        next_year = year + (1 if month_num == 12 else 0)
        return datetime(next_year, next_month, 15)
    except Exception as e:
        logger.warning(f"Due date calculation failed: {e}")
        return None


def extract_generation_date(text: str) -> Tuple[Optional[datetime], str]:
    """
    Extract generation date supporting both formats:
    - PDF1: "system generated challan on 06-MAY-2025 18:01"
    - PDF2: "Generated On: 05-Feb-2026 12:44:31" or "Generated On : 09-Mar-2026"
    """
    patterns = [
        r'system generated challan on\s+(\d{2}-[A-Z]{3}-\d{4}\s*\d{0,2}:?\d{0,2}:?\d{0,2})',
        r'Generated On\s*:\s*(\d{2}-[A-Za-z]{3}-\d{4}\s*\d{0,2}:?\d{0,2}:?\d{0,2})',
        r'Generated On\s*:\s*(\d{2}-[A-Za-z]{3}-\d{4})',
        r'on\s+(\d{2}-[A-Z]{3}-\d{4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            date_str = match.group(1).strip()
            # Clean up the date string
            date_str = re.sub(r'\s+', ' ', date_str).strip()
            try:
                for fmt in ["%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"]:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        return dt, dt.strftime("%d-%b-%Y %H:%M:%S")
                    except ValueError:
                        continue
            except Exception as e:
                logger.warning(f"Date parsing failed: {e}")
            return None, date_str
    return None, "N/A"


def extract_table_values_combined_challan(text: str) -> Dict[str, float]:
    """Extract values from Combined Challan (PDF Type 1)"""
    results = {'admin_charges': 0.0, 'employer_share': 0.0, 'employee_share': 0.0, 'grand_total': 0.0}
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.search(r'Administration\s+Charges', line, re.I):
            numbers = re.findall(r'(\d[\d,.]*)', line)
            if numbers:
                results['admin_charges'] = parse_indian_number(numbers[-1])
        elif re.search(r"Employer'?s\s+Share\s+Of\s+(?!Contribution)", line, re.I):
            numbers = re.findall(r'(\d[\d,.]*)', line)
            if numbers:
                results['employer_share'] = parse_indian_number(numbers[-1])
        elif re.search(r"Employee'?s\s+Share\s+Of\s+(?!Contribution)", line, re.I):
            numbers = re.findall(r'(\d[\d,.]*)', line)
            if numbers:
                results['employee_share'] = parse_indian_number(numbers[-1])
    
    # Extract Grand Total
    for pattern in [r'Grand\s*Total\s*:\s*(\d[\d,.]*)', r'Grand Total:\s*(\d[\d,.]*)']:
        match = re.search(pattern, text, re.I)
        if match:
            results['grand_total'] = parse_indian_number(match.group(1))
            break
    return results


def extract_table_values_provisional_challan(text: str) -> Dict[str, float]:
    """Extract values from Provisional Challan (PDF Type 2)"""
    results = {'admin_charges': 0.0, 'employer_share': 0.0, 'employee_share': 0.0, 'grand_total': 0.0}
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.search(r'Admin[/\s]*Insp\.?\s*Charges', line, re.I):
            numbers = re.findall(r'(\d[\d,.]*)', line)
            if numbers:
                results['admin_charges'] = parse_indian_number(numbers[-1])
        elif re.search(r"Employer'?s\s+Share\s+Of\s+Contribution", line, re.I):
            numbers = re.findall(r'(\d[\d,.]*)', line)
            if numbers:
                results['employer_share'] = parse_indian_number(numbers[-1])
        elif re.search(r"Employee'?s\s+Share\s+Of\s+Contribution", line, re.I):
            numbers = re.findall(r'(\d[\d,.]*)', line)
            if numbers:
                results['employee_share'] = parse_indian_number(numbers[-1])
    
    match = re.search(r'Grand Total:\s*(\d[\d,.]*)', text, re.I)
    if match:
        results['grand_total'] = parse_indian_number(match.group(1))
    return results


def detect_pdf_type(text: str) -> str:
    """Auto-detect PDF format type"""
    text_lower = text.lower()
    if any(marker in text_lower for marker in ['combined challan', 'a/c no. 01, 02, 10, 21', 'administration charges', 'system generated challan']):
        return 'combined'
    if any(marker in text_lower for marker in ['provisional challan', 'admin/ insp. charges', 'share of contribution', 'generated on']):
        return 'provisional'
    return 'unknown'


def parse_pdf_challan(file) -> Optional[Dict]:
    """Main parser function for both PDF formats"""
    try:
        with pdfplumber.open(file) as pdf:
            full_text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
            
            if not full_text.strip():
                logger.error(f"No text extracted from {file.name}")
                return None
            
            pdf_type = detect_pdf_type(full_text)
            logger.info(f"Detected PDF type: {pdf_type} for file: {file.name}")
            
            wage_month = extract_wage_month(full_text)
            gen_datetime, gen_date_str = extract_generation_date(full_text)
            due_date = calculate_due_date(wage_month)
            due_date_str = due_date.strftime("%d-%b-%Y") if due_date else "N/A"
            
            if pdf_type == 'combined':
                values = extract_table_values_combined_challan(full_text)
            elif pdf_type == 'provisional':
                values = extract_table_values_provisional_challan(full_text)
            else:
                combined_vals = extract_table_values_combined_challan(full_text)
                provisional_vals = extract_table_values_provisional_challan(full_text)
                values = combined_vals if combined_vals['grand_total'] > 0 else provisional_vals
                pdf_type = 'combined' if combined_vals['grand_total'] > 0 else 'provisional'
            
            late_days = 0
            if gen_datetime and due_date:
                late_days = (gen_datetime.date() - due_date.date()).days
            
            employee_disallowance = values['employee_share'] if late_days > 0 else 0.0
            
            return {
                'File Name': file.name,
                'PDF Type': pdf_type.title(),
                'Wage Month': wage_month,
                'Due Date': due_date_str,
                'Generated Date': gen_date_str,
                'Late Days': late_days,
                'Admin Charges': values['admin_charges'],
                'Employer Share': values['employer_share'],
                'Employee Share': values['employee_share'],
                'Grand Total': values['grand_total'],
                'Employee Disallowance': employee_disallowance,
                'Status': '⚠️ LATE' if late_days > 0 else ('✅ EARLY' if late_days < 0 else '✓ ON TIME')
            }
    except Exception as e:
        logger.error(f"Error parsing {file.name}: {str(e)}\n{traceback.format_exc()}")
        return None


# ---------------- EXPORT ENGINES ----------------

def to_excel_pro(df: pd.DataFrame) -> bytes:
    """Generate professional Excel report"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='PF_Audit_Report')
        ws = writer.sheets['PF_Audit_Report']
        
        header_fill = PatternFill(start_color="1e3a5f", end_color="1e3a5f", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border
        
        column_widths = {}
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass
            column_widths[column] = max_length + 3
        for col_letter, width in column_widths.items():
            ws.column_dimensions[col_letter].width = min(width, 25)
        
        financial_cols = ['Admin Charges', 'Employer Share', 'Employee Share', 'Grand Total', 'Employee Disallowance']
        for row in range(2, len(df) + 2):
            for col in range(1, len(ws[1]) + 1):
                cell = ws.cell(row=row, column=col)
                cell.border = thin_border
                if ws.cell(row=1, column=col).value in financial_cols:
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = '₹#,##0.00'
                        cell.alignment = Alignment(horizontal='right')
        
        status_col = None
        for idx, col in enumerate(ws[1], 1):
            if col.value == 'Status':
                status_col = get_column_letter(idx)
                break
        if status_col:
            for row in range(2, len(df) + 2):
                cell = ws[f"{status_col}{row}"]
                if 'LATE' in str(cell.value):
                    cell.fill = PatternFill(start_color="ffcdd2", end_color="ffcdd2", fill_type="solid")
                    cell.font = Font(color="c62828", bold=True)
                elif 'EARLY' in str(cell.value):
                    cell.fill = PatternFill(start_color="c8e6c9", end_color="c8e6c9", fill_type="solid")
                    cell.font = Font(color="2e7d32", bold=True)
                elif 'ON TIME' in str(cell.value):
                    cell.fill = PatternFill(start_color="fff9c4", end_color="fff9c4", fill_type="solid")
                    cell.font = Font(color="f9a825", bold=True)
        
        summary_ws = writer.book.create_sheet('Summary')
        summary_ws['A1'] = 'PF AUDIT SUMMARY REPORT'
        summary_ws['A1'].font = Font(bold=True, size=16, color="1e3a5f")
        summary_ws['A3'] = f'Generated: {datetime.now().strftime("%d-%b-%Y %H:%M:%S")}'
        summary_ws['A4'] = f'Total Files Processed: {len(df)}'
        summary_ws['A5'] = f'Total PF Amount: ₹{df["Grand Total"].sum():,.2f}'
        summary_ws['A6'] = f'Total Employee Disallowance: ₹{df["Employee Disallowance"].sum():,.2f}'
        summary_ws['A7'] = f'Late Filings: {len(df[df["Late Days"] > 0])}'
        summary_ws['A8'] = f'On-Time Filings: {len(df[df["Late Days"] == 0])}'
        summary_ws['A9'] = f'Early Filings: {len(df[df["Late Days"] < 0])}'
        for cell in summary_ws['A1:A9']:
            cell[0].font = Font(size=10)
            if cell[0].row == 1:
                cell[0].font = Font(bold=True, size=16, color="1e3a5f")
        summary_ws.column_dimensions['A'].width = 50
    return output.getvalue()


def generate_pdf_summary(df: pd.DataFrame, total_pf: float, emp_dis: float) -> bytes:
    """Generate PDF audit summary"""
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "STATUTORY PF COMPLIANCE AUDIT CERTIFICATE", ln=True, align='C')
    pdf.set_font("Arial", '', 9)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}", ln=True, align='C')
    pdf.cell(0, 6, f"Total Records Audited: {len(df)}", ln=True, align='C')
    pdf.ln(8)
    
    pdf.set_fill_color(30, 58, 95)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(70, 10, f"Total PF Paid", 1, 0, 'C', True)
    pdf.cell(70, 10, f"Employee Disallowance", 1, 0, 'C', True)
    pdf.cell(70, 10, f"Compliance Rate", 1, 1, 'C', True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 12)
    compliance_rate = ((len(df) - len(df[df['Late Days'] > 0])) / len(df) * 100) if len(df) > 0 else 0
    pdf.cell(70, 12, f"INR {total_pf:,.2f}", 1, 0, 'C')
    pdf.cell(70, 12, f"INR {emp_dis:,.2f}", 1, 0, 'C')
    pdf.cell(70, 12, f"{compliance_rate:.1f}%", 1, 1, 'C')
    pdf.ln(8)
    
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    col_widths = [28, 22, 22, 12, 18, 22, 22, 22, 22, 18]
    headers = ["Wage Month", "Due Date", "Gen Date", "Late", "Admin", "Employer", "Employee", "Total", "Disallow", "Status"]
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font("Arial", '', 7)
    pdf.set_text_color(0, 0, 0)
    for _, row in df.iterrows():
        pdf.cell(col_widths[0], 7, str(row['Wage Month'])[:25], 1)
        pdf.cell(col_widths[1], 7, str(row['Due Date']), 1, 0, 'C')
        pdf.cell(col_widths[2], 7, str(row['Generated Date'])[:19], 1, 0, 'C')
        pdf.cell(col_widths[3], 7, str(row['Late Days']), 1, 0, 'C')
        pdf.cell(col_widths[4], 7, f"{row['Admin Charges']:,.0f}", 1, 0, 'R')
        pdf.cell(col_widths[5], 7, f"{row['Employer Share']:,.0f}", 1, 0, 'R')
        pdf.cell(col_widths[6], 7, f"{row['Employee Share']:,.0f}", 1, 0, 'R')
        pdf.cell(col_widths[7], 7, f"{row['Grand Total']:,.0f}", 1, 0, 'R')
        pdf.cell(col_widths[8], 7, f"{row['Employee Disallowance']:,.0f}", 1, 0, 'R')
        status = "LATE" if row['Late Days'] > 0 else ("EARLY" if row['Late Days'] < 0 else "OK")
        if status == "LATE":
            pdf.set_text_color(185, 28, 28)
        elif status == "EARLY":
            pdf.set_text_color(46, 125, 50)
        else:
            pdf.set_text_color(245, 158, 11)
        pdf.cell(col_widths[9], 7, status, 1, 1, 'C')
        pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    pdf.set_font("Arial", 'I', 7)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "System-generated audit report. Verify at www.epfindia.gov.in", ln=True, align='C')
    return pdf.output(dest='S').encode('latin-1', 'replace')


# ---------------- MAIN APP ----------------

st.markdown('<div class="glass-card">', unsafe_allow_html=True)
st.subheader("📂 Upload PF Challan PDFs")
st.markdown("""
<small style="opacity:0.8;">
✅ Supports both <strong>Combined Challan</strong> (A/C 01,02,10,21,22) and <strong>Provisional Challan</strong> formats<br>
✅ Auto-detects PDF type and extracts: Wage Month, Generated Date, Admin/Employer/Employee Shares, Grand Total<br>
✅ Calculates statutory due dates and identifies late/early filings
</small>
""", unsafe_allow_html=True)

files = st.file_uploader("Drop your PF challan PDFs here or click to browse", type="pdf", accept_multiple_files=True, label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    run = st.button("🚀 INITIATE AI AUDIT ENGINE", type="primary", use_container_width=True)

if files and run:
    with st.spinner("🔮 AI Engine analyzing challans with multi-format parsing..."):
        results = []
        errors = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, f in enumerate(files):
            status_text.text(f"Processing {idx+1}/{len(files)}: {f.name}")
            result = parse_pdf_challan(f)
            if result:
                results.append(result)
                logger.info(f"✓ Successfully parsed: {f.name}")
            else:
                errors.append(f.name)
                logger.error(f"✗ Failed to parse: {f.name}")
            progress_bar.progress((idx + 1) / len(files))
        
        progress_bar.empty()
        status_text.empty()
        
        if results:
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.success(f"✅ Successfully processed {len(results)} of {len(files)} files")
            st.markdown('</div>', unsafe_allow_html=True)
            if errors:
                st.markdown('<div class="warning-box">', unsafe_allow_html=True)
                st.warning(f"⚠️ {len(errors)} file(s) could not be parsed: {', '.join(errors)}")
                st.markdown('</div>', unsafe_allow_html=True)
            
            df = pd.DataFrame(results)
            st.markdown("### 📊 REAL-TIME AUDIT DASHBOARD")
            
            m1, m2, m3, m4 = st.columns(4)
            total_pf = df['Grand Total'].sum()
            emp_dis = df['Employee Disallowance'].sum()
            late_count = len(df[df['Late Days'] > 0])
            compliance = ((len(df) - late_count) / len(df) * 100) if len(df) > 0 else 100
            
            m1.metric("💰 TOTAL PF AUDITED", f"₹{total_pf:,.2f}")
            m2.metric("⚠️ TAX DISALLOWANCE", f"₹{emp_dis:,.2f}", delta=f"{late_count} late", delta_color="inverse")
            m3.metric("📋 RECORDS PROCESSED", f"{len(df)}")
            m4.metric("✅ COMPLIANCE RATE", f"{compliance:.1f}%", delta_color="normal")
            
            st.markdown("---")
            st.subheader("📈 Payment Performance Timeline")
            df['Status_Code'] = df['Late Days'].apply(lambda x: 'Late' if x > 0 else ('Early' if x < 0 else 'On Time'))
            
            fig = px.bar(df, x='Wage Month', y='Grand Total', color='Status_Code',
                        color_discrete_map={'Late': '#ef4444', 'On Time': '#f59e0b', 'Early': '#10b981'},
                        title="PF Payment Analysis by Wage Month",
                        hover_data=['Due Date', 'Generated Date', 'Late Days', 'Admin Charges', 'Employer Share', 'Employee Share'])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="Inter", size=11), hovermode="x unified",
                            xaxis_title="Wage Month", yaxis_title="Amount (INR)", legend_title="Filing Status")
            fig.update_traces(marker_line_width=0, hovertemplate='<b>%{x}</b><br>Amount: ₹%{y:,.0f}<br>%{hovertext}<extra></extra>')
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("### 📥 Export Audit Reports")
            c1, c2, c3 = st.columns(3)
            with c1:
                excel_data = to_excel_pro(df)
                st.download_button("🚀 Download Excel Report", excel_data, f"PF_Audit_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", help="Professional Excel with formatting", use_container_width=True)
            with c2:
                pdf_data = generate_pdf_summary(df, total_pf, emp_dis)
                st.download_button("📜 Download PDF Certificate", pdf_data, f"PF_Audit_Certificate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", "application/pdf", help="Formal audit certificate", use_container_width=True)
            with c3:
                csv_data = df.to_csv(index=False).encode('utf-8')
                st.download_button("📄 Download CSV Data", csv_data, f"PF_Audit_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", help="Raw CSV data", use_container_width=True)
            
            st.markdown("### 🔍 Detailed Audit Records")
            display_df = df.copy()
            numeric_cols = ['Admin Charges', 'Employer Share', 'Employee Share', 'Grand Total', 'Employee Disallowance']
            for col in numeric_cols:
                display_df[col] = display_df[col].apply(lambda x: f"₹{x:,.2f}")
            
            # ✅ FIXED: Use pandas-compatible styling (map instead of applymap for pandas >= 2.1)
            def style_status(val):
                if 'LATE' in str(val):
                    return 'background-color: #ffcdd2; color: #c62828; font-weight: bold'
                elif 'EARLY' in str(val):
                    return 'background-color: #c8e6c9; color: #2e7d32; font-weight: bold'
                return ''
            
            styled_df = display_df.style.map(style_status, subset=['Status'])
            
            st.dataframe(styled_df, use_container_width=True, height=400,
                        column_config={"Grand Total": st.column_config.NumberColumn("Grand Total", format="₹%.2f"),
                                     "Employee Disallowance": st.column_config.NumberColumn("Disallowance", format="₹%.2f")})
            
            with st.expander("🔧 Raw Extraction Data (Debug View)"):
                st.json(results)
        else:
            st.markdown('<div class="error-box">', unsafe_allow_html=True)
            st.error("❌ No valid challan data could be extracted from uploaded files.")
            st.markdown("**Troubleshooting:** Ensure PDFs are text-based EPFO challans, not scanned images.")
            st.markdown('</div>', unsafe_allow_html=True)

elif files and not run:
    st.info("👆 Click 'INITIATE AI AUDIT ENGINE' to begin processing your uploaded PDFs")
elif not files:
    st.markdown("""
    <div style="text-align: center; padding: 3rem; opacity: 0.7;">
        <div style="font-size: 4rem; margin-bottom: 1rem;">📋</div>
        <h3>Upload PF Challan PDFs to Begin</h3>
        <p>Supports both Combined Challan (A/C 01,02,10,21,22) and Provisional Challan formats</p>
    </div>
    """, unsafe_allow_html=True)

# ---------------- FOOTER ----------------
st.markdown("""
<div class="footer">
    © 2026 | PF AI Command Center | <span style="color: #2563eb;">⚡ Dual-Format PDF Parser • Statutory Compliance Engine</span><br>
    <small>Disclaimer: This tool assists in audit preparation. Always verify with official EPFO portal at www.epfindia.gov.in</small>
</div>
""", unsafe_allow_html=True)

# ---------------- SIDEBAR: QUICK REFERENCE ----------------
with st.sidebar:
    st.markdown("### 📚 Format Reference")
    st.markdown("**🔹 Combined Challan (Type 1)**")
    st.markdown("<small>• Header: 'Combined Challan of A/C NO. 01, 02, 10, 21 & 22'<br>• Date: 'system generated challan on DD-MMM-YYYY'<br>• Wage Month: 'Dues for the wage month April 2025'<br>• Fields: Administration Charges, Employer's Share Of, Employee's Share Of</small>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**🔹 Provisional Challan (Type 2)**")
    st.markdown("<small>• Header: 'PROVISIONAL CHALLAN FOR WAGE MONTH'<br>• Date: 'Generated On: DD-MMM-YYYY HH:MM:SS'<br>• Wage Month: 'JAN 2026'<br>• Fields: Admin/ Insp. Charges, Employer's Share Of Contribution, Employee's Share Of Contribution</small>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### ⚙️ Processing Logic")
    st.markdown("<small>1️⃣ Auto-detect PDF format<br>2️⃣ Extract wage month & calculate due date (15th next month)<br>3️⃣ Parse financial values from TOTAL column<br>4️⃣ Compare generated date vs due date<br>5️⃣ Flag late filings for tax disallowance<br>6️⃣ Generate multi-format reports</small>", unsafe_allow_html=True)
