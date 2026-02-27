import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO
from openpyxl.styles import Font, Alignment, PatternFill
from datetime import datetime
import plotly.express as px
from fpdf import FPDF

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="PF AI Command Center", layout="wide", page_icon="📊")

# ---------------- ULTRA PREMIUM UI (GLASSMORPHISM + ANIMATIONS + LUXURY) ----------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&family=Playfair+Display:wght@700;900&display=swap');

:root {
    --bg-deep: #0b1120;
    --bg-gradient-1: #1a1f35;
    --bg-gradient-2: #2d1b3a;
    --accent-primary: #9f7aea;
    --accent-secondary: #f687b3;
    --accent-glow: rgba(159, 122, 234, 0.6);
    --text-light: #f7fafc;
    --text-muted: #cbd5e0;
    --card-bg: rgba(20, 30, 50, 0.6);
    --card-border: rgba(255, 255, 255, 0.1);
    --glass-blur: 20px;
}

/* Animated deep gradient background */
.stApp {
    background: linear-gradient(135deg, var(--bg-deep), var(--bg-gradient-1), var(--bg-gradient-2));
    background-size: 400% 400%;
    animation: gradientFlow 18s ease infinite;
    position: relative;
    overflow-x: hidden;
}

.stApp::before {
    content: '';
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: radial-gradient(circle at 20% 30%, rgba(159, 122, 234, 0.2) 0%, transparent 35%),
                radial-gradient(circle at 80% 70%, rgba(246, 135, 179, 0.15) 0%, transparent 40%);
    pointer-events: none;
    z-index: 0;
}

@keyframes gradientFlow {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* Base typography */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    scroll-behavior: smooth;
}

/* Premium glass card */
.glass-card {
    background: var(--card-bg);
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
    border-radius: 40px;
    border: 1px solid var(--card-border);
    padding: 2.5rem;
    margin-bottom: 2rem;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5),
                inset 0 1px 2px rgba(255, 255, 255, 0.1);
    transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275),
                box-shadow 0.4s ease,
                border-color 0.3s ease;
    position: relative;
    z-index: 1;
}

.glass-card:hover {
    transform: translateY(-8px) scale(1.01);
    box-shadow: 0 35px 70px -15px rgba(159, 122, 234, 0.5),
                inset 0 1px 3px rgba(255, 255, 255, 0.2);
    border-color: rgba(159, 122, 234, 0.4);
}

.glass-card::after {
    content: '';
    position: absolute;
    top: -1px;
    left: -1px;
    right: -1px;
    bottom: -1px;
    background: linear-gradient(135deg, rgba(159,122,234,0.3), rgba(246,135,179,0.3));
    border-radius: 41px;
    opacity: 0;
    transition: opacity 0.4s ease;
    pointer-events: none;
    z-index: -1;
}

.glass-card:hover::after {
    opacity: 0.2;
}

/* Header card – extra luxurious */
.header-card {
    text-align: center;
    padding: 3rem 2rem;
    background: rgba(10, 20, 40, 0.5);
    backdrop-filter: blur(25px);
    border-radius: 60px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    box-shadow: 0 30px 60px -15px rgba(0, 0, 0, 0.6),
                inset 0 0 30px rgba(159, 122, 234, 0.3);
    margin-bottom: 2.5rem;
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
    background: radial-gradient(circle, rgba(159, 122, 234, 0.2) 0%, transparent 60%);
    animation: rotate 30s linear infinite;
    z-index: -1;
}

@keyframes rotate {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.main-title {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 4rem;
    background: linear-gradient(135deg, #f6e05e, #fbbf24, #f59e0b, #9f7aea);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-shadow: 0 0 30px rgba(246, 135, 179, 0.5);
    animation: shimmer 5s infinite;
    background-size: 200% auto;
    margin-bottom: 0.5rem;
    line-height: 1.2;
}

@keyframes shimmer {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

.subtitle {
    font-size: 1.5rem;
    font-weight: 600;
    background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    opacity: 0.9;
    letter-spacing: 2px;
    margin-bottom: 1rem;
}

.sanskrit {
    font-style: italic;
    font-size: 1.2rem;
    color: var(--text-muted);
    border-top: 1px solid rgba(255,255,255,0.1);
    padding-top: 1rem;
    display: inline-block;
}

/* Premium metric cards */
[data-testid="stMetric"] {
    background: rgba(20, 30, 50, 0.4);
    backdrop-filter: blur(15px);
    border-radius: 35px;
    padding: 1.8rem 1rem;
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 0 15px 35px -10px rgba(0, 0, 0, 0.5),
                inset 0 1px 1px rgba(255, 255, 255, 0.1);
    transition: all 0.4s ease;
}

[data-testid="stMetric"]:hover {
    transform: scale(1.02) translateY(-5px);
    border-color: rgba(159, 122, 234, 0.4);
    box-shadow: 0 25px 45px -10px rgba(159, 122, 234, 0.4);
}

[data-testid="stMetricLabel"] {
    font-weight: 600;
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #cbd5e1;
}

[data-testid="stMetricValue"] {
    font-weight: 800;
    font-size: 2.5rem;
    color: #f7fafc;
    text-shadow: 0 0 10px rgba(159, 122, 234, 0.5);
}

/* Buttons – with shine effect */
.stButton > button {
    background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
    color: white;
    border: none;
    border-radius: 60px;
    padding: 1rem 2.5rem;
    font-weight: 700;
    font-size: 1.2rem;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    box-shadow: 0 10px 30px -5px rgba(159, 122, 234, 0.5);
    transition: all 0.4s ease;
    position: relative;
    overflow: hidden;
    width: 100%;
    border: 1px solid rgba(255, 255, 255, 0.2);
}

.stButton > button::after {
    content: '';
    position: absolute;
    top: -50%;
    left: -60%;
    width: 200%;
    height: 200%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
    transform: rotate(30deg);
    transition: left 0.5s ease;
}

.stButton > button:hover::after {
    left: 100%;
}

.stButton > button:hover {
    transform: translateY(-5px) scale(1.02);
    box-shadow: 0 20px 40px -5px rgba(159, 122, 234, 0.7);
    background: linear-gradient(135deg, var(--accent-secondary), var(--accent-primary));
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: rgba(20, 30, 50, 0.4) !important;
    backdrop-filter: blur(15px);
    border-radius: 35px !important;
    border: 2px dashed rgba(159, 122, 234, 0.5) !important;
    padding: 2.5rem !important;
    transition: all 0.3s ease;
}

[data-testid="stFileUploader"]:hover {
    border-color: var(--accent-secondary) !important;
    background: rgba(20, 30, 50, 0.6) !important;
    box-shadow: 0 0 30px rgba(159, 122, 234, 0.3);
}

/* Dataframe */
[data-testid="stDataFrame"] {
    background: rgba(20, 30, 50, 0.3);
    backdrop-filter: blur(15px);
    border-radius: 30px;
    padding: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 0 15px 30px -10px rgba(0,0,0,0.3);
}

[data-testid="stDataFrame"] table {
    border-collapse: separate;
    border-spacing: 0 5px;
}

[data-testid="stDataFrame"] th {
    background: linear-gradient(135deg, #4c1d95, #6b21a5) !important;
    color: white !important;
    font-weight: 700;
    font-size: 1rem;
    padding: 1rem !important;
    border-radius: 20px 20px 0 0;
}

[data-testid="stDataFrame"] td {
    background: rgba(255, 255, 255, 0.05);
    color: #f7fafc;
    padding: 0.8rem 1rem !important;
    border-bottom: 1px solid rgba(255,255,255,0.1);
}

[data-testid="stDataFrame"] tr:hover td {
    background: rgba(159, 122, 234, 0.1);
}

/* Plotly chart */
.js-plotly-plot .plotly, .plotly {
    background: transparent !important;
}

/* Custom scrollbar */
::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}
::-webkit-scrollbar-track {
    background: rgba(0,0,0,0.2);
    border-radius: 10px;
}
::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
    border-radius: 10px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--accent-secondary);
}

/* Footer */
.footer {
    text-align: center;
    margin-top: 3rem;
    font-size: 1rem;
    color: var(--text-muted);
    padding: 1.5rem;
    border-top: 1px solid rgba(255,255,255,0.1);
    background: rgba(10, 15, 30, 0.3);
    backdrop-filter: blur(10px);
    border-radius: 60px;
}

.footer span {
    background: linear-gradient(135deg, #9f7aea, #f687b3);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 700;
}

/* Hide default Streamlit footer */
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ---------------- WRAP MAIN CONTENT IN GLASS CARD ----------------
st.markdown('<div class="glass-card">', unsafe_allow_html=True)

# ---------------- HEADER (with enhanced glass effect) ----------------
st.markdown("""
<div class="header-card">
    <div class="main-title">PF CHALLAN AI COMMAND CENTER</div>
    <div class="subtitle">Enterprise Statutory Audit Suite</div>
    <div class="sanskrit">🌸 कर्मण्येवाधिकारस्ते मा फलेषु कदाचन 🌸</div>
</div>
""", unsafe_allow_html=True)

# ---------------- HELPERS (unchanged) ----------------
def safe_extract(pattern, text):
    m = re.search(pattern, text, re.I | re.M)
    if m:
        val = m.group(1).replace(",", "").strip()
        return val if val else "0"
    return "0"

def calculate_due_date(wage_month_str):
    try:
        parts = wage_month_str.split()
        month_dt = datetime.strptime(parts[0], "%B")
        year = int(parts[1])
        next_m = month_dt.month % 12 + 1
        next_y = year + (1 if month_dt.month == 12 else 0)
        return datetime(next_y, next_m, 15)
    except: return None

# ---------------- EXPORT ENGINES (unchanged) ----------------
def to_excel_pro(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='PF_Audit')
        ws = writer.sheets['PF_Audit']
        h_fill, h_font = PatternFill(start_color="1e293b", end_color="1e293b", fill_type="solid"), Font(bold=True, color="FFFFFF")
        for cell in ws[1]:
            cell.font, cell.fill, cell.alignment = h_font, h_fill, Alignment(horizontal="center")
        for col in ws.columns:
            max_len = max([len(str(cell.value)) for cell in col])
            ws.column_dimensions[col[0].column_letter].width = max_len + 3
    return output.getvalue()

def generate_pdf_summary(df, total_pf, emp_dis):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "STATUTORY PF COMPLIANCE AUDIT CERTIFICATE", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Generated For Audit Purpose | {datetime.now().strftime('%d-%m-%Y')}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, f"Total Audited: INR {total_pf:,.2f}", ln=True)
    pdf.cell(0, 8, f"Total Employee Share Disallowance: INR {emp_dis:,.2f}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(30, 41, 59); pdf.set_text_color(255, 255, 255)
    w = [35, 25, 25, 15, 25, 30, 30, 30, 35, 20] 
    headers = ["Wage Month", "Due Date", "Paid Date", "Diff", "Admin", "Employer", "Employee", "Total", "Emp Disallowance", "Status"]
    for i in range(len(headers)): pdf.cell(w[i], 10, headers[i], 1, 0, 'C', True)
    pdf.ln()

    pdf.set_font("Arial", '', 7); pdf.set_text_color(0, 0, 0)
    for _, row in df.iterrows():
        pdf.cell(w[0], 8, str(row['Wage Month']), 1)
        pdf.cell(w[1], 8, str(row['Due Date']), 1, 0, 'C')
        pdf.cell(w[2], 8, str(row['Generated Date']), 1, 0, 'C')
        pdf.cell(w[3], 8, str(row['Late Days']), 1, 0, 'C')
        pdf.cell(w[4], 8, f"{row['Admin Charges']:,.2f}", 1, 0, 'R')
        pdf.cell(w[5], 8, f"{row['Employer Share']:,.2f}", 1, 0, 'R')
        pdf.cell(w[6], 8, f"{row['Employee Share']:,.2f}", 1, 0, 'R')
        pdf.cell(w[7], 8, f"{row['Grand Total']:,.2f}", 1, 0, 'R')
        pdf.cell(w[8], 8, f"{row['Employee Disallowance']:,.2f}", 1, 0, 'R')
        pdf.cell(w[9], 8, "LATE" if row['Late Days'] > 0 else "OK", 1, 1, 'C')
    
    return pdf.output(dest='S').encode('latin-1', 'replace')

# ---------------- MAIN APP ----------------
files = st.file_uploader("📂 Upload PF Challan PDFs", type="pdf", accept_multiple_files=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    run = st.button("🚀 INITIATE SYSTEM AUDIT")

if files and run:
    with st.spinner("🔮 Analyzing challans with AI precision..."):
        all_data = []
        for f in files:
            with pdfplumber.open(f) as pdf:
                text = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
                blocks = re.split(r"(Dues for the wage month of\s*[A-Za-z]+\s*[0-9]{4})", text, flags=re.I)
                
                for i in range(1, len(blocks), 2):
                    content = blocks[i] + blocks[i+1]
                    m_match = re.search(r"wage month of\s*([A-Za-z]+)\s*([0-9]{4})", content, re.I)
                    wage_month = f"{m_match.group(1).title()} {m_match.group(2)}" if m_match else "Unknown"
                    
                    gen_date_str = safe_extract(r"system generated challan on\s*.*?(\d{2}-[A-Z]{3}-\d{4})", content).upper()
                    due_dt = calculate_due_date(wage_month)
                    
                    # Financial Data from TOTAL Column on far right ($ anchor)
                    admin = float(safe_extract(r"Administration Charges\s+.*?\s+(\d[\d,.]*)$", content))
                    employer = float(safe_extract(r"Employer'?s Share Of\s+.*?\s+(\d[\d,.]*)$", content))
                    employee = float(safe_extract(r"Employee'?s Share Of\s+.*?\s+(\d[\d,.]*)$", content))
                    total_val = float(safe_extract(r"Grand Total\s*:\s*.*?\s+(\d[\d,.]*)$", content))
                    
                    # Late Days: Negative is Early, Positive is Late
                    diff = 0
                    if due_dt and gen_date_str != "0":
                        try:
                            gen_dt = datetime.strptime(gen_date_str, "%d-%b-%Y")
                            diff = (gen_dt - due_dt).days
                        except: pass
                    
                    all_data.append({
                        "Wage Month": wage_month, "Due Date": due_dt.strftime("%d-%b-%Y") if due_dt else "N/A",
                        "Generated Date": gen_date_str, "Late Days": diff,
                        "Admin Charges": admin, "Employer Share": employer, "Employee Share": employee,
                        "Grand Total": total_val, 
                        "Employee Disallowance": employee if diff > 0 else 0.0
                    })

        if all_data:
            df = pd.DataFrame(all_data)
            st.markdown("### 📊 AUDIT DASHBOARD")
            
            # Metrics with emojis
            m1, m2, m3 = st.columns(3)
            total_pf = df['Grand Total'].sum()
            emp_dis = df['Employee Disallowance'].sum()
            m1.metric("💰 TOTAL PF PAID", f"INR {total_pf:,.2f}")
            m2.metric("⚠️ TAX DISALLOWANCE", f"INR {emp_dis:,.2f}", delta_color="inverse")
            m3.metric("⏰ LATE FILINGS", len(df[df['Late Days'] > 0]))

            st.markdown("---")
            
            # Chart
            fig = px.bar(df, x='Wage Month', y='Grand Total', color='Late Days', 
                         title="PF Payment Performance (Negative = Early)")
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#f7fafc", family="Inter"),
                hovermode="x",
                title_font=dict(size=20, color="#f7fafc")
            )
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

            # Download buttons
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "🚀 DOWNLOAD EXCEL AUDIT", 
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

            # Dataframe
            st.dataframe(
                df.style.format({
                    "Grand Total": "{:,.2f}", 
                    "Employee Disallowance": "{:,.2f}", 
                    "Employer Share": "{:,.2f}",
                    "Admin Charges": "{:,.2f}",
                    "Employee Share": "{:,.2f}"
                }),
                use_container_width=True,
                height=400
            )

# Close the main glass card
st.markdown('</div>', unsafe_allow_html=True)

# ---------------- FOOTER ----------------
st.markdown("""
<div class="footer">
    © 2026 | <span>Developed by Abhishek Jakkula</span> | ⚡ AI-Powered Statutory Audit
</div>
""", unsafe_allow_html=True)
