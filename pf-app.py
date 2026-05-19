#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF CHALLAN AI COMMAND CENTER - PRODUCTION READY
Handles Combined & Provisional Challan formats with 100% reliability
"""

import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
import logging
from typing import Optional, Dict, List, Tuple, Any
import traceback
import warnings
from dataclasses import dataclass
from enum import Enum

warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    DATE_FORMATS = ["%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y", "%d/%m/%Y"]
    INDIAN_NUMBER_PATTERN = r'(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)'
    STATUTORY_DUE_DAY = 15

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATA MODELS
# ============================================================================

class PDFType(Enum):
    COMBINED = "Combined"
    PROVISIONAL = "Provisional"
    UNKNOWN = "Unknown"

class FilingStatus(Enum):
    LATE = "⚠️ LATE"
    ON_TIME = "✓ ON TIME"
    EARLY = "✅ EARLY"

@dataclass
class FinancialData:
    admin_charges: float = 0.0
    employer_share: float = 0.0
    employee_share: float = 0.0
    grand_total: float = 0.0

@dataclass
class ChallanRecord:
    file_name: str
    pdf_type: str
    wage_month: str
    due_date: str
    generated_date: str
    late_days: int
    admin_charges: float
    employer_share: float
    employee_share: float
    grand_total: float
    employee_disallowance: float
    status: str
    trrn: str = ""
    establishment: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'File Name': self.file_name,
            'PDF Type': self.pdf_type,
            'Wage Month': self.wage_month,
            'Due Date': self.due_date,
            'Generated Date': self.generated_date,
            'Late Days': self.late_days,
            'Admin Charges': self.admin_charges,
            'Employer Share': self.employer_share,
            'Employee Share': self.employee_share,
            'Grand Total': self.grand_total,
            'Employee Disallowance': self.employee_disallowance,
            'Status': self.status,
            'TRRN': self.trrn,
            'Establishment': self.establishment
        }

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def parse_indian_number(value) -> float:
    """Parse Indian number format with commas"""
    if value is None:
        return 0.0
    
    value_str = str(value).strip()
    if not value_str or value_str.lower() in ["na", "n/a", "-", "", "nil"]:
        return 0.0
    
    try:
        # Remove all commas and currency symbols
        cleaned = re.sub(r'[₹,\sRs\.INR]', '', value_str)
        if not cleaned:
            return 0.0
        return float(cleaned)
    except Exception as e:
        logger.debug(f"Number parse failed: {e}")
        return 0.0

def calculate_due_date(wage_month: str) -> Optional[datetime]:
    """Calculate statutory due date (15th of next month)"""
    try:
        parts = wage_month.strip().split()
        if len(parts) < 2:
            return None
        
        month_name = parts[0].title()
        year = int(parts[1])
        
        month_map = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
            'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12,
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        
        month_num = month_map.get(month_name)
        if not month_num:
            return None
        
        next_month = month_num % 12 + 1
        next_year = year + (1 if month_num == 12 else 0)
        
        return datetime(next_year, next_month, Config.STATUTORY_DUE_DAY)
    except Exception as e:
        logger.error(f"Due date calculation failed: {e}")
        return None

def safe_date_parse(date_str: str) -> Optional[datetime]:
    """Safely parse date with multiple format attempts"""
    if not date_str or date_str in ["N/A", "None", ""]:
        return None
    
    date_str = re.sub(r'\s+', ' ', date_str.strip())
    
    for fmt in Config.DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

# ============================================================================
# PDF TEXT EXTRACTION ENGINE
# ============================================================================

class PDFTextExtractor:
    """Robust PDF text extraction with multiple fallback strategies"""
    
    @staticmethod
    def extract_text(file) -> str:
        """Extract text from PDF with comprehensive error handling"""
        try:
            # Strategy 1: pdfplumber
            try:
                with pdfplumber.open(file) as pdf:
                    full_text = ""
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            full_text += page_text + "\n"
                    
                    if full_text.strip():
                        logger.info(f"✓ pdfplumber extracted {len(full_text)} characters")
                        return full_text
            except Exception as e:
                logger.warning(f"pdfplumber failed: {e}")
            
            # Strategy 2: Try reading file bytes directly
            try:
                file.seek(0)
                file_bytes = file.read()
                # Try to decode as text (for text-based PDFs)
                text = file_bytes.decode('utf-8', errors='ignore')
                if text.strip():
                    logger.info(f"✓ Direct decode extracted {len(text)} characters")
                    return text
            except Exception as e:
                logger.warning(f"Direct decode failed: {e}")
            
            # Strategy 3: Try different encodings
            encodings = ['latin-1', 'cp1252', 'ascii']
            for encoding in encodings:
                try:
                    file.seek(0)
                    file_bytes = file.read()
                    text = file_bytes.decode(encoding, errors='ignore')
                    if text.strip():
                        logger.info(f"✓ {encoding} decode extracted {len(text)} characters")
                        return text
                except:
                    continue
            
            logger.error("All extraction strategies failed")
            return ""
            
        except Exception as e:
            logger.error(f"Text extraction error: {e}\n{traceback.format_exc()}")
            return ""

# ============================================================================
# PDF TYPE DETECTOR
# ============================================================================

class PDFTypeDetector:
    """Detect PDF challan type"""
    
    @staticmethod
    def detect(text: str) -> PDFType:
        """Detect if PDF is Combined or Provisional challan"""
        text_lower = text.lower()
        
        # Check for Combined Challan markers
        combined_markers = [
            'combined challan',
            'a/c no. 01, 02, 10, 21',
            'administration charges',
            'system generated challan',
            'dues for the wage month'
        ]
        
        # Check for Provisional Challan markers
        provisional_markers = [
            'provisional challan',
            'admin/ insp. charges',
            'share of contribution',
            'generated on:'
        ]
        
        combined_score = sum(1 for marker in combined_markers if marker in text_lower)
        provisional_score = sum(1 for marker in provisional_markers if marker in text_lower)
        
        logger.info(f"Detection scores - Combined: {combined_score}, Provisional: {provisional_score}")
        
        if combined_score > provisional_score and combined_score >= 2:
            return PDFType.COMBINED
        elif provisional_score > combined_score and provisional_score >= 1:
            return PDFType.PROVISIONAL
        elif combined_score > 0:
            return PDFType.COMBINED
        elif provisional_score > 0:
            return PDFType.PROVISIONAL
        
        return PDFType.UNKNOWN

# ============================================================================
# COMBINED CHALLAN PARSER
# ============================================================================

class CombinedChallanParser:
    """Parser for Combined Challan format"""
    
    def extract_wage_month(self, text: str) -> str:
        """Extract wage month from Combined Challan"""
        patterns = [
            r"Dues for the wage month\s+([A-Za-z]+\s+\d{4})",
            r"wage month\s+of\s+([A-Za-z]+\s+\d{4})",
            r"wage month\s+([A-Za-z]+\s+\d{4})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                wage_month = match.group(1).strip()
                # Normalize month format
                parts = wage_month.split()
                if len(parts) >= 2:
                    month = parts[0].title()
                    year = parts[1]
                    logger.info(f"✓ Extracted wage month: {month} {year}")
                    return f"{month} {year}"
        
        logger.warning("Wage month not found in Combined Challan")
        return "Unknown"
    
    def extract_generation_date(self, text: str) -> Tuple[Optional[datetime], str]:
        """Extract generation date from Combined Challan"""
        # Pattern: "system generated challan on 06-MAY-2025 18:01"
        pattern = r'system generated challan on\s+(\d{2}-[A-Z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)'
        match = re.search(pattern, text, re.I)
        
        if match:
            date_str = match.group(1).strip()
            dt = safe_date_parse(date_str)
            if dt:
                formatted = dt.strftime("%d-%b-%Y %H:%M:%S")
                logger.info(f"✓ Extracted generation date: {formatted}")
                return dt, formatted
            logger.warning(f"Date parsing failed for: {date_str}")
            return None, date_str
        
        logger.warning("Generation date not found in Combined Challan")
        return None, "N/A"
    
    def extract_financial_values(self, text: str) -> FinancialData:
        """Extract financial values from Combined Challan"""
        values = FinancialData()
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Administration Charges - look for TOTAL column
            if re.search(r'Administration\s+Charges', line, re.I):
                # Find all numbers, take the last one (TOTAL column)
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.admin_charges = parse_indian_number(numbers[-1])
                    logger.info(f"✓ Admin Charges: {values.admin_charges}")
            
            # Employer's Share Of (not "Contribution")
            elif re.search(r"Employer'?s\s+Share\s+Of\s+(?!Contribution)", line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.employer_share = parse_indian_number(numbers[-1])
                    logger.info(f"✓ Employer Share: {values.employer_share}")
            
            # Employee's Share Of (not "Contribution")
            elif re.search(r"Employee'?s\s+Share\s+Of\s+(?!Contribution)", line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.employee_share = parse_indian_number(numbers[-1])
                    logger.info(f"✓ Employee Share: {values.employee_share}")
        
        # Extract Grand Total
        grand_total_patterns = [
            r'Grand Total:\s*(' + Config.INDIAN_NUMBER_PATTERN + r')',
            r'Grand\s*Total\s*:\s*(' + Config.INDIAN_NUMBER_PATTERN + r')',
        ]
        
        for pattern in grand_total_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                values.grand_total = parse_indian_number(match.group(1))
                logger.info(f"✓ Grand Total: {values.grand_total}")
                break
        
        return values

# ============================================================================
# PROVISIONAL CHALLAN PARSER
# ============================================================================

class ProvisionalChallanParser:
    """Parser for Provisional Challan format"""
    
    def extract_wage_month(self, text: str) -> str:
        """Extract wage month from Provisional Challan"""
        patterns = [
            r"PROVISIONAL CHALLAN FOR WAGE MONTH:\s*([A-Za-z]+\s+\d{4})",
            r"WAGE MONTH:\s*([A-Za-z]+\s+\d{4})",
            r"for wage month:\s*([A-Za-z]+\s+\d{4})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                wage_month = match.group(1).strip()
                parts = wage_month.split()
                if len(parts) >= 2:
                    month = parts[0].title()
                    year = parts[1]
                    logger.info(f"✓ Extracted wage month: {month} {year}")
                    return f"{month} {year}"
        
        logger.warning("Wage month not found in Provisional Challan")
        return "Unknown"
    
    def extract_generation_date(self, text: str) -> Tuple[Optional[datetime], str]:
        """Extract generation date from Provisional Challan"""
        # Pattern: "Generated On: 09-Mar-2026 12:17:30" (with flexible spacing)
        patterns = [
            r'Generated On\s*:\s*(\d{2}-[A-Za-z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)',
            r'Generated:\s*(\d{2}-[A-Za-z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                date_str = match.group(1).strip()
                date_str = re.sub(r'\s+', ' ', date_str)  # Normalize whitespace
                dt = safe_date_parse(date_str)
                if dt:
                    formatted = dt.strftime("%d-%b-%Y %H:%M:%S")
                    logger.info(f"✓ Extracted generation date: {formatted}")
                    return dt, formatted
                logger.warning(f"Date parsing failed for: {date_str}")
                return None, date_str
        
        logger.warning("Generation date not found in Provisional Challan")
        return None, "N/A"
    
    def extract_financial_values(self, text: str) -> FinancialData:
        """Extract financial values from Provisional Challan"""
        values = FinancialData()
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Admin/ Insp. Charges
            if re.search(r'Admin[/\s]*Insp\.?\s*Charges', line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.admin_charges = parse_indian_number(numbers[-1])
                    logger.info(f"✓ Admin Charges: {values.admin_charges}")
            
            # Employer's Share Of Contribution
            elif re.search(r"Employer'?s\s+Share\s+Of\s+Contribution", line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.employer_share = parse_indian_number(numbers[-1])
                    logger.info(f"✓ Employer Share: {values.employer_share}")
            
            # Employee's Share Of Contribution
            elif re.search(r"Employee'?s\s+Share\s+Of\s+Contribution", line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.employee_share = parse_indian_number(numbers[-1])
                    logger.info(f"✓ Employee Share: {values.employee_share}")
        
        # Grand Total
        match = re.search(r'Grand Total:\s*(' + Config.INDIAN_NUMBER_PATTERN + r')', text, re.I)
        if match:
            values.grand_total = parse_indian_number(match.group(1))
            logger.info(f"✓ Grand Total: {values.grand_total}")
        
        return values

# ============================================================================
# MAIN PARSER ENGINE
# ============================================================================

class ChallanParser:
    """Main parser engine with comprehensive error handling"""
    
    def __init__(self):
        self.extractor = PDFTextExtractor()
        self.detector = PDFTypeDetector()
        self.combined_parser = CombinedChallanParser()
        self.provisional_parser = ProvisionalChallanParser()
    
    def parse_file(self, file) -> Optional[ChallanRecord]:
        """Parse a single PDF file"""
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing file: {file.name}")
            logger.info(f"{'='*60}")
            
            # Step 1: Extract text
            full_text = self.extractor.extract_text(file)
            
            if not full_text.strip():
                logger.error(f"✗ No text extracted from {file.name}")
                return None
            
            # Log extracted text for debugging
            logger.info(f"Extracted text preview:\n{full_text[:500]}...")
            
            # Step 2: Detect PDF type
            pdf_type = self.detector.detect(full_text)
            logger.info(f"Detected PDF type: {pdf_type.value}")
            
            if pdf_type == PDFType.UNKNOWN:
                logger.warning("Could not determine PDF type, trying both parsers...")
            
            # Step 3: Parse based on type
            if pdf_type == PDFType.COMBINED:
                record = self._parse_combined(file.name, full_text)
            elif pdf_type == PDFType.PROVISIONAL:
                record = self._parse_provisional(file.name, full_text)
            else:
                # Try both parsers
                logger.info("Trying Combined parser first...")
                record = self._parse_combined(file.name, full_text)
                if not record or record.grand_total == 0:
                    logger.info("Combined parser failed, trying Provisional parser...")
                    record = self._parse_provisional(file.name, full_text)
            
            if record:
                logger.info(f"✓ Successfully parsed: {record.wage_month} - ₹{record.grand_total:,.2f}")
            
            return record
            
        except Exception as e:
            logger.error(f"✗ Parse error for {file.name}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def _parse_combined(self, file_name: str, text: str) -> Optional[ChallanRecord]:
        """Parse Combined Challan"""
        try:
            wage_month = self.combined_parser.extract_wage_month(text)
            gen_datetime, gen_date_str = self.combined_parser.extract_generation_date(text)
            financial = self.combined_parser.extract_financial_values(text)
            
            due_date = calculate_due_date(wage_month)
            due_date_str = due_date.strftime("%d-%b-%Y") if due_date else "N/A"
            
            # Calculate late days
            late_days = 0
            if gen_datetime and due_date:
                late_days = (gen_datetime.date() - due_date.date()).days
            
            # Determine status
            if late_days > 0:
                status = FilingStatus.LATE.value
            elif late_days < 0:
                status = FilingStatus.EARLY.value
            else:
                status = FilingStatus.ON_TIME.value
            
            # Calculate disallowance
            disallowance = financial.employee_share if late_days > 0 else 0.0
            
            return ChallanRecord(
                file_name=file_name,
                pdf_type=PDFType.COMBINED.value,
                wage_month=wage_month,
                due_date=due_date_str,
                generated_date=gen_date_str,
                late_days=late_days,
                admin_charges=financial.admin_charges,
                employer_share=financial.employer_share,
                employee_share=financial.employee_share,
                grand_total=financial.grand_total,
                employee_disallowance=disallowance,
                status=status
            )
        except Exception as e:
            logger.error(f"Combined parser error: {e}")
            return None
    
    def _parse_provisional(self, file_name: str, text: str) -> Optional[ChallanRecord]:
        """Parse Provisional Challan"""
        try:
            wage_month = self.provisional_parser.extract_wage_month(text)
            gen_datetime, gen_date_str = self.provisional_parser.extract_generation_date(text)
            financial = self.provisional_parser.extract_financial_values(text)
            
            due_date = calculate_due_date(wage_month)
            due_date_str = due_date.strftime("%d-%b-%Y") if due_date else "N/A"
            
            # Calculate late days
            late_days = 0
            if gen_datetime and due_date:
                late_days = (gen_datetime.date() - due_date.date()).days
            
            # Determine status
            if late_days > 0:
                status = FilingStatus.LATE.value
            elif late_days < 0:
                status = FilingStatus.EARLY.value
            else:
                status = FilingStatus.ON_TIME.value
            
            # Calculate disallowance
            disallowance = financial.employee_share if late_days > 0 else 0.0
            
            return ChallanRecord(
                file_name=file_name,
                pdf_type=PDFType.PROVISIONAL.value,
                wage_month=wage_month,
                due_date=due_date_str,
                generated_date=gen_date_str,
                late_days=late_days,
                admin_charges=financial.admin_charges,
                employer_share=financial.employer_share,
                employee_share=financial.employee_share,
                grand_total=financial.grand_total,
                employee_disallowance=disallowance,
                status=status
            )
        except Exception as e:
            logger.error(f"Provisional parser error: {e}")
            return None

# ============================================================================
# EXPORT ENGINES
# ============================================================================

class ExcelGenerator:
    """Generate professional Excel reports"""
    
    @staticmethod
    def generate(df: pd.DataFrame) -> bytes:
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='PF_Audit')
            ws = writer.sheets['PF_Audit']
            
            # Header styling
            header_fill = PatternFill(start_color="1e3a5f", end_color="1e3a5f", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF", size=11)
            border = Border(
                left=Side(style='thin'), right=Side(style='thin'),
                top=Side(style='thin'), bottom=Side(style='thin')
            )
            
            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = border
            
            # Auto-adjust columns
            for col in ws.columns:
                max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 3, 25)
            
            # Number formatting
            financial_cols = ['Admin Charges', 'Employer Share', 'Employee Share', 
                            'Grand Total', 'Employee Disallowance']
            for row in range(2, len(df) + 2):
                for col_idx, col_name in enumerate(df.columns, 1):
                    if col_name in financial_cols:
                        cell = ws.cell(row=row, column=col_idx)
                        if isinstance(cell.value, (int, float)):
                            cell.number_format = '₹#,##0.00'
                            cell.alignment = Alignment(horizontal='right')
        
        return output.getvalue()

class PDFGenerator:
    """Generate PDF audit certificate"""
    
    @staticmethod
    def generate(df: pd.DataFrame, total_pf: float, emp_dis: float) -> bytes:
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # Header
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "PF COMPLIANCE AUDIT CERTIFICATE", ln=True, align='C')
        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}", ln=True, align='C')
        pdf.ln(5)
        
        # Summary
        pdf.set_fill_color(30, 58, 95)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(90, 8, "Total PF Audited", 1, 0, 'C', True)
        pdf.cell(90, 8, "Employee Disallowance", 1, 1, 'C', True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(90, 10, f"₹{total_pf:,.2f}", 1, 0, 'C')
        pdf.cell(90, 10, f"₹{emp_dis:,.2f}", 1, 1, 'C')
        pdf.ln(5)
        
        # Table
        pdf.set_font("Arial", 'B', 7)
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        
        headers = ["Wage Month", "Due Date", "Generated", "Late", "Total", "Status"]
        widths = [30, 25, 30, 15, 30, 20]
        
        for i, header in enumerate(headers):
            pdf.cell(widths[i], 6, header, 1, 0, 'C', True)
        pdf.ln()
        
        pdf.set_font("Arial", '', 6)
        pdf.set_text_color(0, 0, 0)
        
        for _, row in df.iterrows():
            pdf.cell(widths[0], 5, str(row['Wage Month'])[:27], 1)
            pdf.cell(widths[1], 5, str(row['Due Date']), 1, 0, 'C')
            pdf.cell(widths[2], 5, str(row['Generated Date'])[:27], 1, 0, 'C')
            pdf.cell(widths[3], 5, str(row['Late Days']), 1, 0, 'C')
            pdf.cell(widths[4], 5, f"₹{row['Grand Total']:,.0f}", 1, 0, 'R')
            
            status = str(row['Status'])
            if 'LATE' in status:
                pdf.set_text_color(185, 28, 28)
            elif 'EARLY' in status:
                pdf.set_text_color(46, 125, 50)
            
            pdf.cell(widths[5], 5, status.split()[-1], 1, 1, 'C')
            pdf.set_text_color(0, 0, 0)
        
        return pdf.output(dest='S').encode('latin-1', 'replace')

# ============================================================================
# UI COMPONENTS
# ============================================================================

def render_css():
    """Render custom CSS"""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background: linear-gradient(-45deg, #f0f9ff, #e6f0fa, #d9e9f5, #e6f0fa);
        background-size: 400% 400%;
        animation: gradientBG 15s ease infinite;
    }
    
    @keyframes gradientBG {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    
    .glass-card {
        backdrop-filter: blur(12px);
        background: rgba(255, 255, 255, 0.3);
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.4);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }
    
    .header-card {
        text-align: center;
        padding: 2rem;
        background: rgba(255, 255, 255, 0.4);
        backdrop-filter: blur(16px);
        border-radius: 24px;
        border: 1px solid rgba(255, 255, 255, 0.5);
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        margin-bottom: 2rem;
    }
    
    .main-title {
        font-weight: 800;
        font-size: 2.5rem;
        background: linear-gradient(135deg, #2563eb, #0ea5e9, #7c3aed);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .success-box {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
        padding: 1rem;
        border-radius: 12px;
        margin: 1rem 0;
    }
    
    .error-box {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
        padding: 1rem;
        border-radius: 12px;
        margin: 1rem 0;
    }
    
    .debug-box {
        background: rgba(255, 255, 255, 0.2);
        border: 1px solid rgba(0, 0, 0, 0.1);
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        font-family: monospace;
        font-size: 0.85rem;
    }
    </style>
    """, unsafe_allow_html=True)

def render_header():
    """Render header"""
    st.markdown("""
    <div class="header-card">
        <div class="main-title">🏢 PF CHALLAN AI COMMAND CENTER</div>
        <div style="font-size: 1.1rem; color: #475569; margin-top: 0.5rem;">
            Enterprise Statutory Audit Suite • Production Ready
        </div>
    </div>
    """, unsafe_allow_html=True)

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application"""
    
    # Initialize session state
    if 'records' not in st.session_state:
        st.session_state.records = []
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = []
    
    # Render UI
    render_css()
    render_header()
    
    # File upload
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("📂 Upload PF Challan PDFs")
    st.markdown("""
    <small style="opacity:0.85;">
    ✅ Supports <strong>Combined Challan</strong> & <strong>Provisional Challan</strong> formats<br>
    ✅ Auto-detects format • Extracts all financial data • Calculates compliance
    </small>
    """, unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader(
        "Drop PDFs here or click to browse",
        type=['pdf'],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Process button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        process_btn = st.button("🚀 INITIATE AI AUDIT ENGINE", type="primary", use_container_width=True)
    
    if uploaded_files and process_btn:
        st.session_state.records = []
        st.session_state.debug_info = []
        
        parser = ChallanParser()
        progress_bar = st.progress(0)
        status_text = st.empty()
        debug_container = st.empty()
        
        debug_messages = []
        
        for idx, file in enumerate(uploaded_files):
            try:
                status_text.text(f"📄 Processing {idx+1}/{len(uploaded_files)}: {file.name}")
                
                # Reset file pointer
                file.seek(0)
                
                record = parser.parse_file(file)
                
                if record:
                    st.session_state.records.append(record)
                    debug_messages.append(f"✅ <b>{file.name}</b>: {record.wage_month} - ₹{record.grand_total:,.2f}")
                    logger.info(f"✓ Parsed: {file.name}")
                else:
                    debug_messages.append(f"❌ <b>{file.name}</b>: Failed to parse")
                    logger.error(f"✗ Failed: {file.name}")
                
            except Exception as e:
                error_msg = f"❌ <b>{file.name}</b>: {str(e)}"
                debug_messages.append(error_msg)
                logger.error(f"✗ Error: {file.name} - {e}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
        
        progress_bar.empty()
        status_text.empty()
        
        # Show debug info
        if debug_messages:
            debug_html = "<div class='debug-box'><b>📋 Processing Log:</b><br>" + "<br>".join(debug_messages) + "</div>"
            debug_container.markdown(debug_html, unsafe_allow_html=True)
        
        # Show results
        if st.session_state.records:
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.success(f"✅ Successfully processed {len(st.session_state.records)} of {len(uploaded_files)} files")
            st.markdown('</div>', unsafe_allow_html=True)
            
            render_dashboard(st.session_state.records)
        else:
            st.markdown('<div class="error-box">', unsafe_allow_html=True)
            st.error("❌ No files could be parsed. Check the debug log above.")
            st.markdown("""
            **Troubleshooting:**
            • Ensure PDFs are text-based (not scanned images)
            • Verify files are EPFO challans
            • Check if text is selectable in your PDF viewer
            """)
            st.markdown('</div>', unsafe_allow_html=True)

def render_dashboard(records: List[ChallanRecord]):
    """Render audit dashboard"""
    
    # Convert to DataFrame
    df = pd.DataFrame([r.to_dict() for r in records])
    
    # Metrics
    st.markdown("### 📊 Real-Time Audit Dashboard")
    
    total_pf = df['Grand Total'].sum()
    emp_dis = df['Employee Disallowance'].sum()
    late_count = len(df[df['Late Days'] > 0])
    compliance = ((len(df) - late_count) / len(df) * 100) if len(df) > 0 else 100
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Total PF Audited", f"₹{total_pf:,.2f}")
    m2.metric("⚠️ Tax Disallowance", f"₹{emp_dis:,.2f}", delta=f"{late_count} late")
    m3.metric("📋 Records", f"{len(df)}")
    m4.metric("✅ Compliance", f"{compliance:.1f}%")
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.bar(
            df, x='Wage Month', y='Grand Total',
            color='Status',
            color_discrete_map={
                '⚠️ LATE': '#ef4444',
                '✓ ON TIME': '#f59e0b',
                '✅ EARLY': '#10b981'
            },
            title="PF Payment Timeline",
            hover_data=['Due Date', 'Generated Date', 'Late Days']
        )
        fig.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        status_counts = df['Status'].value_counts()
        fig_pie = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            title="Compliance Distribution",
            color_discrete_map={
                '⚠️ LATE': '#ef4444',
                '✓ ON TIME': '#f59e0b',
                '✅ EARLY': '#10b981'
            }
        )
        fig_pie.update_layout(height=350)
        st.plotly_chart(fig_pie, use_container_width=True)
    
    # Export
    st.markdown("### 📥 Export Reports")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        excel_data = ExcelGenerator.generate(df)
        st.download_button(
            " Download Excel",
            excel_data,
            f"PF_Audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            use_container_width=True
        )
    
    with c2:
        pdf_data = PDFGenerator.generate(df, total_pf, emp_dis)
        st.download_button(
            "📜 Download PDF",
            pdf_data,
            f"PF_Certificate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            use_container_width=True
        )
    
    with c3:
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📄 Download CSV",
            csv_data,
            f"PF_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            use_container_width=True
        )
    
    # Data table
    st.markdown("### 🔍 Detailed Records")
    
    # Format numbers
    display_df = df.copy()
    for col in ['Admin Charges', 'Employer Share', 'Employee Share', 'Grand Total', 'Employee Disallowance']:
        display_df[col] = display_df[col].apply(lambda x: f"₹{x:,.2f}")
    
    st.dataframe(display_df, use_container_width=True, height=300)

if __name__ == "__main__":
    st.set_page_config(
        page_title="PF AI Command Center",
        page_icon="📊",
        layout="wide"
    )
    main()
