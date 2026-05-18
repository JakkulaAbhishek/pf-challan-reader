import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO
from openpyxl.styles import Font, Alignment, PatternFill
from datetime import datetime
import plotly.express as px
from fpdf import FPDF
import calendar

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="PF AI Command Center", layout="wide", page_icon="📊")

# ---------------- ULTRA STYLISH UI (GLASSMORPHISM + ANIMATIONS) ----------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');

/* Base Styles */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    scroll-behavior: smooth;
}

/* Animated gradient background (light mode) */
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

/* Dark mode background override */
@media (prefers-color-scheme: dark) {
    .stApp {
        background: linear-gradient(-45deg, #0b1a2e, #102a3c, #1a3f54, #102a3c);
        background-size: 400% 400%;
        animation: gradientBG 15s ease infinite;
    }
}

/* Glassmorphism Card */
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

/* Header Card */
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
    .subtitle {
        color: #e2e8f0;
    }
}

/* Metric Cards */
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
    [data-testid="stMetricLabel"] {
        color: #cbd5e1;
    }
    [data-testid="stMetricValue"] {
        color: #f1f5f9;
    }
}

/* Buttons */
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

.stButton > button:active {
    transform: translateY(-1px);
}

/* File uploader */
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

/* Dataframe */
[data-testid="stDataFrame"] {
    background: rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(8px);
    border-radius: 20px;
    padding: 1rem;
    border: 1px solid rgba(255, 255, 255, 0.3);
}

/* Plotly chart background */
.js-plotly-plot .plotly, .plotly {
    background: transparent !important;
}

/* Custom scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: rgba(0,0,0,0.05);
    border-radius: 10px;
}
::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #2563eb, #0ea5e9);
    border-radius: 10px;
}
::-webkit-scrollbar-thumb:hover {
    background: #2563eb;
}

/* Footer */
.footer {
    text-align: center;
    margin-top: 3rem;
    font-size: 0.9rem;
    opacity: 0.7;
    color: #1e293b;
    padding: 1rem;
    border-top: 1px solid rgba(0,0,0,0.1);
}

@media (prefers-color-scheme: dark) {
    .footer {
        color: #cbd5e1;
    }
}
</style>
""", unsafe_allow_html=True)

# ---------------- HEADER (with glass effect) ----------------
st.markdown("""
<div class="header-card">
    <div class="main-title">PF CHALLAN AI COMMAND CENTER</div>
    <div class="subtitle">Enterprise Statutory Audit Suite</div>
    <div style="margin-top:1rem; font-style:italic; opacity:0.7;">
        🌸 कर्मण्येवाधिकारस्ते मा फलेषु कदाचन 🌸
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------- HELPER FUNCTIONS ----------------
def parse_currency(value_str):
    """Convert currency string like '1,461' or '36,520' to float."""
    if not value_str:
        return 0.0
    try:
        return float(value_str.replace(',', '').strip())
    except:
        return 0.0

def extract_last_number_from_line(line):
    """Extract the last numeric value (including commas) from a line."""
    numbers = re.findall(r'[\d,]+(?:\.\d+)?', line)
    if numbers:
        return parse_currency(numbers[-1])
    return 0.0

def calculate_due_date(month_name, year):
    """Calculate due date: 15th of next month."""
    try:
        month_num = datetime.strptime(month_name.strip(), "%B").month
        year_num = int(year)
        next_month = month_num + 1 if month_num < 12 else 1
        next_year = year_num + 1 if month_num == 12 else year_num
        return datetime(next_year, next_month, 15)
    except:
        return None

def parse_generated_date(date_str):
    """Parse date like '06- MAY- 2025 18:01' to datetime."""
    if not date_str or date_str == "0":
        return None
    try:
        # Clean up the date string
        cleaned = re.sub(r'\s+', ' ', date_str.strip())
        # Handle "06- MAY- 2025 18:01" or "06-MAY-2025" format
        match = re.search(r'(\d{1,2})\s*-\s*([A-Za-z]+)\s*-\s*(\d{4})', cleaned)
        if match:
            day, month, year = match.groups()
            dt_str = f"{day}-{month[:3]}-{year}"
            return datetime.strptime(dt_str, "%d-%b-%Y")
    except:
        pass
    return None

def sanitize_for_latin1(text):
    """Replace or remove characters not supported by Latin-1 encoding."""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        '₹': 'Rs.',
        '“': '"', '”': '"',
        '‘': "'", '’': "'",
        '–': '-', '—': '-',
        '…': '...',
        '\u00a0': ' ',
        '\u2022': '*',
        '°': ' deg',
        '©': '(c)',
        '®': '(R)',
        '™': '(TM)',
        '&amp;': '&',
        '&#x27;': "'",
        '&quot;': '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return ''.join(c if ord(c) < 256 else '?' for c in text)

def extract_challan_data(text):
    """Extract PF challan data from PDF text. Returns list of records."""
    records = []
    # Normalize text: replace HTML entities
    text = text.replace('&amp;', '&').replace('&#x27;', "'").replace('&quot;', '"')
    lines = text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for "Dues for the wage month" line
        if re.search(r'Dues for the wage month', line, re.I):
            # Extract month and year
            month_match = re.search(r'wage month\s+([A-Za-z]+)\s+(\d{4})', line, re.I)
            if not month_match and i+1 < len(lines):
                combined = line + " " + lines[i+1]
                month_match = re.search(r'wage month\s+([A-Za-z]+)\s+(\d{4})', combined, re.I)
            
            if month_match:
                month_name = month_match.group(1).strip()
                year = month_match.group(2).strip()
                wage_month = f"{month_name.title()} {year}"
                
                # Extract generated date from the block
                gen_date_str = "0"
                for j in range(i, min(i+30, len(lines))):
                    if 'system generated' in lines[j].lower():
                        # Look for pattern like "06- MAY- 2025 18:01"
                        date_match = re.search(r'(\d{2})\s*-\s*([A-Za-z]+)\s*-\s*(\d{4})', lines[j])
                        if date_match:
                            gen_date_str = f"{date_match.group(1)}-{date_match.group(2)[:3]}-{date_match.group(3)}"
                        break
                
                # Initialize totals
                admin_total = 0.0
                employer_total = 0.0
                employee_total = 0.0
                
                # Search for the three rows within ~30 lines after the wage month
                for k in range(i, min(i+40, len(lines))):
                    line_lower = lines[k].lower()
                    if 'administration charges' in line_lower:
                        admin_total = extract_last_number_from_line(lines[k])
                    elif "employer's share" in line_lower or "employer share" in line_lower:
                        employer_total = extract_last_number_from_line(lines[k])
                    elif "employee's share" in line_lower or "employee share" in line_lower:
                        employee_total = extract_last_number_from_line(lines[k])
                
                # Fallback using regex on a block if still zero
                if admin_total == 0 and employer_total == 0 and employee_total == 0:
                    block = '\n'.join(lines[max(0,i):min(len(lines), i+50)])
                    # Look for rows: 1 Administration Charges ... TOTAL value
                    admin_match = re.search(r'1\s+Administration Charges[\s\d,]+(\d[\d,]*)', block, re.I)
                    if admin_match:
                        admin_total = parse_currency(admin_match.group(1))
                    emp_match = re.search(r'2\s+Employer[\s\S]+?(\d[\d,]*)(?=\s*\n|\s*3)', block, re.I)
                    if emp_match:
                        employer_total = parse_currency(emp_match.group(1))
                    employee_match = re.search(r'3\s+Employee[\s\S]+?(\d[\d,]*)(?=\s*\n|\s*$)', block, re.I)
                    if employee_match:
                        employee_total = parse_currency(employee_match.group(1))
                
                # Grand total (can also be taken from "Total remittance by Employer" line)
                grand_total = admin_total + employer_total + employee_total
                if grand_total == 0:
                    total_match = re.search(r'Total remittance by Employer\s*\(Rs\.\)\s*([\d,]+)', text, re.I)
                    if total_match:
                        grand_total = parse_currency(total_match.group(1))
                
                # Compute due date and late days
                due_dt = calculate_due_date(month_name, year)
                gen_dt = parse_generated_date(gen_date_str)
                late_days = 0
                if due_dt and gen_dt:
                    late_days = (gen_dt - due_dt).days
                
                emp_disallowance = employee_total if late_days > 0 else 0.0
                
                records.append({
                    "Wage Month": wage_month,
                    "Due Date": due_dt.strftime("%d-%b-%Y") if due_dt else "N/A",
                    "Generated Date": gen_date_str if gen_date_str != "0" else "N/A",
                    "Late Days": late_days,
                    "Admin Charges": admin_total,
                    "Employer Share": employer_total,
                    "Employee Share": employee_total,
                    "Grand Total": grand_total,
                    "Employee Disallowance": emp_disallowance
                })
        i += 1
    
    return records

# ---------------- EXPORT ENGINES ----------------
def to_excel_pro(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='PF_Audit')
        ws = writer.sheets['PF_Audit']
        h_fill = PatternFill(start_color="1e293b", end_color="1e293b", fill_type="solid")
        h_font = Font(bold=True, color="FFFFFF")
        for cell in ws[1]:
            cell.font = h_font
            cell.fill = h_fill
            cell.alignment = Alignment(horizontal="center")
        for col in ws.columns:
            max_len = max([len(str(cell.value)) for cell in col]) + 3
            ws.column_dimensions[col[0].column_letter].width = min(max_len, 30)
    return output.getvalue()

def generate_pdf_summary(df, total_pf, emp_dis):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, sanitize_for_latin1("STATUTORY PF COMPLIANCE AUDIT CERTIFICATE"), ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    date_str = datetime.now().strftime('%d-%m-%Y')
    pdf.cell(0, 10, sanitize_for_latin1(f"Generated For Audit Purpose | {date_str}"), ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, sanitize_for_latin1(f"Total PF Paid: INR {total_pf:,.2f}"), ln=True)
    pdf.cell(0, 8, sanitize_for_latin1(f"Total Employee Share Disallowance (late payments): INR {emp_dis:,.2f}"), ln=True)
    pdf.ln(5)
    
    # Table headers
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    w = [35, 28, 28, 18, 28, 32, 32, 32, 35, 22]
    headers = ["Wage Month", "Due Date", "Paid/Gen Date", "Late Days", "Admin", "Employer", "Employee", "Total", "Disallowance", "Status"]
    for i in range(len(headers)):
        pdf.cell(w[i], 10, sanitize_for_latin1(headers[i]), 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font("Arial", '', 7)
    pdf.set_text_color(0, 0, 0)
    for _, row in df.iterrows():
        pdf.cell(w[0], 8, sanitize_for_latin1(str(row['Wage Month'])), 1)
        pdf.cell(w[1], 8, sanitize_for_latin1(str(row['Due Date'])), 1, 0, 'C')
        pdf.cell(w[2], 8, sanitize_for_latin1(str(row['Generated Date'])), 1, 0, 'C')
        pdf.cell(w[3], 8, str(row['Late Days']), 1, 0, 'C')
        pdf.cell(w[4], 8, f"{row['Admin Charges']:,.2f}", 1, 0, 'R')
        pdf.cell(w[5], 8, f"{row['Employer Share']:,.2f}", 1, 0, 'R')
        pdf.cell(w[6], 8, f"{row['Employee Share']:,.2f}", 1, 0, 'R')
        pdf.cell(w[7], 8, f"{row['Grand Total']:,.2f}", 1, 0, 'R')
        pdf.cell(w[8], 8, f"{row['Employee Disallowance']:,.2f}", 1, 0, 'R')
        status = "LATE" if row['Late Days'] > 0 else "ON TIME"
        pdf.cell(w[9], 8, sanitize_for_latin1(status), 1, 1, 'C')
    
    return pdf.output(dest='S').encode('latin-1', 'replace')

# ---------------- MAIN APP ----------------
files = st.file_uploader("📂 Upload PF Challan PDFs", type="pdf", accept_multiple_files=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    run = st.button("🚀 INITIATE SYSTEM AUDIT")

if files and run:
    with st.spinner("🔮 Analyzing challans with AI precision..."):
        all_records = []
        for uploaded_file in files:
            with pdfplumber.open(uploaded_file) as pdf:
                full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])
                # Only process if text contains "Dues for the wage month"
                if re.search(r'Dues for the wage month', full_text, re.I):
                    records = extract_challan_data(full_text)
                    all_records.extend(records)
                else:
                    st.info(f"Skipping file without challan data: {uploaded_file.name}")
        
        if all_records:
            df = pd.DataFrame(all_records)
            
            # Sort by Wage Month chronologically
            try:
                month_order = {month: i for i, month in enumerate(calendar.month_name)}
                df['SortKey'] = df['Wage Month'].apply(
                    lambda x: month_order.get(x.split()[0], 0) + int(x.split()[1]) * 12
                )
                df = df.sort_values('SortKey').drop('SortKey', axis=1)
            except:
                pass
            
            st.markdown("### 📊 AUDIT DASHBOARD")
            
            # Metrics
            m1, m2, m3 = st.columns(3)
            total_pf = df['Grand Total'].sum()
            emp_dis = df['Employee Disallowance'].sum()
            late_count = len(df[df['Late Days'] > 0])
            
            m1.metric("💰 TOTAL PF PAID", f"INR {total_pf:,.2f}")
            m2.metric("⚠️ TAX DISALLOWANCE (SEC 36)", f"INR {emp_dis:,.2f}",
                      delta=f"{emp_dis/total_pf*100:.1f}%" if total_pf > 0 else None)
            m3.metric("⏰ LATE FILINGS", f"{late_count} / {len(df)}")
            
            st.markdown("---")
            
            # Chart
            fig = px.bar(df, x='Wage Month', y='Grand Total', color='Late Days',
                         title="PF Payment Performance (Negative = Early / Positive = Late)",
                         color_continuous_scale='RdYlGn_r',
                         text='Grand Total')
            fig.update_traces(texttemplate='₹%{text:,.0f}', textposition='outside')
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#1e293b"),
                hovermode="x unified",
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Download buttons
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "📊 DOWNLOAD EXCEL AUDIT REPORT",
                    to_excel_pro(df),
                    "PF_Audit_Report.xlsx",
                    help="Download detailed audit in Excel format"
                )
            with c2:
                pdf_raw = generate_pdf_summary(df, total_pf, emp_dis)
                st.download_button(
                    "📜 DOWNLOAD PDF AUDIT TRAIL",
                    pdf_raw,
                    "PF_Audit_Trail.pdf",
                    "application/pdf",
                    help="Download summary audit trail as PDF"
                )
            
            # Display dataframe with formatting
            display_df = df.copy()
            numeric_cols = ['Admin Charges', 'Employer Share', 'Employee Share', 'Grand Total', 'Employee Disallowance']
            for col in numeric_cols:
                display_df[col] = display_df[col].apply(lambda x: f"₹{x:,.2f}")
            
            st.dataframe(display_df, use_container_width=True, height=400)
            
            # Show summary insight
            if late_count > 0:
                st.warning(f"⚠️ {late_count} challan(s) were filed late. Employee share of ₹{emp_dis:,.2f} is disallowed under Section 36(1)(va).")
            else:
                st.success("✅ All challans filed on or before due date. No disallowance applicable.")
        else:
            st.error("❌ No valid PF challan data could be extracted from the uploaded PDFs. Please ensure you have uploaded the correct challan files.")
else:
    if files and not run:
        st.info("👆 Click 'INITIATE SYSTEM AUDIT' to start analysis.")
    elif not files:
        st.info("📄 Please upload PF challan PDF files to begin the audit.")

# ---------------- FOOTER ----------------
st.markdown("""
<div class="footer">
    © 2026 | Developed by Abhishek Jakkula | ⚡ AI-Powered Statutory Audit | Version 3.0
</div>
""", unsafe_allow_html=True)
