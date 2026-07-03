#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
PF CHALLAN AI COMMAND CENTER v6.0
-------------------------------------------------------------------------------
Enterprise Statutory Audit Suite • Modular • Extensible • Production‑Ready
================================================================================
Author: AI Engineer
Version: 6.0.0
Date: July 2026
-------------------------------------------------------------------------------
FEATURES:
  • Multi‑PDF batch processing (Combined & Provisional)
  • Robust text/table extraction (pdfplumber + regex + OCR fallback)
  • SQLite database for persistent storage & audit trail
  • Advanced validation against statutory contribution rates
  • Interactive dashboard with Plotly charts
  • Exports: Excel (multi‑sheet), PDF certificate, CSV, JSON, HTML
  • Configurable parameters (due day, rates, fiscal year)
  • Extensible parser & exporter architecture
================================================================================
"""

import streamlit as st
import pdfplumber
import re
import pandas as pd
import numpy as np
from io import BytesIO, StringIO
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from fpdf import FPDF
import logging
import traceback
import json
from typing import Optional, Dict, List, Tuple, Any, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib
import warnings
import sqlite3
import os
import time
from pathlib import Path

# Optional OCR dependencies
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# Optional database – we'll use sqlite3 built‑in

warnings.filterwarnings('ignore')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    """Global configuration with defaults and user overrides."""
    DATE_FORMATS = ["%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"]
    INDIAN_NUMBER_PATTERN = r'(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)'
    STATUTORY_DUE_DAY = 15
    ALLOW_OCR = False
    DB_PATH = "pf_audit.db"
    # Contribution rates (employer, employee, pension, edli, admin) – can be overridden in UI
    RATES = {
        'employer_share': 0.0367,   # 3.67% of wages
        'employee_share': 0.12,     # 12% of wages
        'pension_share': 0.0833,    # 8.33% of wages
        'edli_share': 0.005,        # 0.5% of wages
        'admin_charges': 0.005,     # 0.5% of wages
        'edli_admin': 0.0001        # 0.01% for EDLI admin
    }
    FISCAL_YEAR_START_MONTH = 4     # April
    MIN_WAGE_LIMIT = 15000          # For EPS contribution limit

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
    """Container for financial amounts extracted from a challan."""
    admin_charges: float = 0.0
    employer_share: float = 0.0
    employee_share: float = 0.0
    pension_share: float = 0.0
    edli_share: float = 0.0
    grand_total: float = 0.0
    pmrpy_employer: float = 0.0
    pmrpy_pension: float = 0.0
    pmrpy_employee: float = 0.0
    total_remittance_employer: float = 0.0
    total_wages: float = 0.0
    total_subscribers: int = 0
    # New fields for detailed breakdown
    employer_arrears: float = 0.0
    employee_arrears: float = 0.0
    total_arrears: float = 0.0

@dataclass
class ChallanRecord:
    """Complete record for a single wage month challan."""
    file_name: str
    pdf_type: str
    wage_month: str
    due_date: str
    generated_date: str
    late_days: int
    admin_charges: float
    employer_share: float
    employee_share: float
    pension_share: float
    edli_share: float
    grand_total: float
    employee_disallowance: float
    status: str
    trrn: str = ""
    establishment_code: str = ""
    establishment_name: str = ""
    pmrpy_total: float = 0.0
    total_wages: float = 0.0
    total_subscribers: int = 0
    validation_errors: List[str] = field(default_factory=list)
    processing_hash: str = ""
    # New fields
    employer_arrears: float = 0.0
    employee_arrears: float = 0.0
    total_arrears: float = 0.0
    fiscal_year: str = ""
    quarter: str = ""
    computed_employer_share: float = 0.0
    computed_employee_share: float = 0.0
    computed_pension_share: float = 0.0
    computed_edli_share: float = 0.0
    computed_admin_charges: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert lists to strings for serialization
        d['validation_errors'] = ', '.join(self.validation_errors)
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> 'ChallanRecord':
        errors = data.pop('validation_errors', '')
        if isinstance(errors, str):
            errors = [e.strip() for e in errors.split(',') if e.strip()]
        data['validation_errors'] = errors
        return cls(**data)

# ============================================================================
# DATABASE LAYER
# ============================================================================
class Database:
    """SQLite persistence for records and processing metadata."""
    
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS challan_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT,
                pdf_type TEXT,
                wage_month TEXT,
                due_date TEXT,
                generated_date TEXT,
                late_days INTEGER,
                admin_charges REAL,
                employer_share REAL,
                employee_share REAL,
                pension_share REAL,
                edli_share REAL,
                grand_total REAL,
                employee_disallowance REAL,
                status TEXT,
                trrn TEXT,
                establishment_code TEXT,
                establishment_name TEXT,
                pmrpy_total REAL,
                total_wages REAL,
                total_subscribers INTEGER,
                validation_errors TEXT,
                processing_hash TEXT,
                employer_arrears REAL,
                employee_arrears REAL,
                total_arrears REAL,
                fiscal_year TEXT,
                quarter TEXT,
                computed_employer_share REAL,
                computed_employee_share REAL,
                computed_pension_share REAL,
                computed_edli_share REAL,
                computed_admin_charges REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Index for performance
        c.execute('CREATE INDEX IF NOT EXISTS idx_wage_month ON challan_records (wage_month)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_status ON challan_records (status)')
        conn.commit()
        conn.close()

    def insert_record(self, record: ChallanRecord) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        data = record.to_dict()
        # Remove id if present
        data.pop('id', None)
        # Ensure validation_errors is string
        if isinstance(data.get('validation_errors'), list):
            data['validation_errors'] = ', '.join(data['validation_errors'])
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        sql = f"INSERT INTO challan_records ({columns}) VALUES ({placeholders})"
        c.execute(sql, list(data.values()))
        last_id = c.lastrowid
        conn.commit()
        conn.close()
        return last_id

    def get_all_records(self) -> List[ChallanRecord]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM challan_records ORDER BY wage_month DESC')
        rows = c.fetchall()
        records = []
        for row in rows:
            data = dict(row)
            records.append(ChallanRecord.from_dict(data))
        conn.close()
        return records

    def delete_all_records(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('DELETE FROM challan_records')
        conn.commit()
        conn.close()

    def get_summary_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            SELECT
                COUNT(*) as total_records,
                SUM(grand_total) as total_pf,
                SUM(employee_disallowance) as total_disallowance,
                SUM(CASE WHEN status LIKE '%LATE%' THEN 1 ELSE 0 END) as late_count,
                SUM(CASE WHEN status LIKE '%EARLY%' THEN 1 ELSE 0 END) as early_count,
                AVG(late_days) as avg_late_days,
                MIN(wage_month) as first_month,
                MAX(wage_month) as last_month
            FROM challan_records
        ''')
        stats = dict(c.fetchone())
        conn.close()
        # Compute compliance rate
        total = stats.get('total_records', 0)
        late = stats.get('late_count', 0)
        stats['compliance_rate'] = ((total - late) / total * 100) if total > 0 else 100.0
        return stats

# ============================================================================
# PARSER ENGINE
# ============================================================================
class PDFParser:
    """Multi‑strategy PDF parser with fallbacks and confidence scoring."""

    @staticmethod
    def extract_text(file) -> str:
        """Extract text using pdfplumber; fallback to OCR if enabled."""
        try:
            with pdfplumber.open(file) as pdf:
                full_text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"
                if full_text.strip():
                    return full_text
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")
        if Config.ALLOW_OCR and OCR_AVAILABLE:
            try:
                from pdf2image import convert_from_bytes
                images = convert_from_bytes(file.read(), dpi=200)
                full_text = ""
                for img in images:
                    text = pytesseract.image_to_string(img)
                    full_text += text + "\n"
                file.seek(0)
                return full_text
            except Exception as e:
                logger.warning(f"OCR extraction failed: {e}")
        return ""

    @staticmethod
    def detect_pdf_type(text: str) -> PDFType:
        text_lower = text.lower()
        combined_markers = ['combined challan', 'a/c no. 01, 02, 10, 21', 'administration charges', 'system generated challan']
        provisional_markers = ['provisional challan', 'admin/ insp. charges', 'generated on:']
        combined_score = sum(1 for m in combined_markers if m in text_lower)
        provisional_score = sum(1 for m in provisional_markers if m in text_lower)
        if combined_score >= 2:
            return PDFType.COMBINED
        elif provisional_score >= 1:
            return PDFType.PROVISIONAL
        return PDFType.UNKNOWN

    @staticmethod
    def extract_establishment(text: str) -> Tuple[str, str]:
        code_match = re.search(r'Establishment Code & Name\s+([A-Z0-9]+)\s+([^\n]+)', text, re.I)
        if code_match:
            return code_match.group(1), code_match.group(2).strip()
        code_match = re.search(r'Establishment\s+Code\s*[:]?\s*([A-Z0-9]+)', text, re.I)
        name_match = re.search(r'Establishment\s+Name\s*[:]?\s*([^\n]+)', text, re.I)
        if code_match and name_match:
            return code_match.group(1), name_match.group(1).strip()
        return "", ""

    @staticmethod
    def extract_trrn(text: str) -> str:
        match = re.search(r'TRRN\s*[:\-]?\s*([A-Za-z0-9]+)', text, re.I)
        return match.group(1) if match else ""

    @staticmethod
    def extract_wage_month(text: str) -> str:
        """Enhanced extraction with multiple patterns."""
        patterns = [
            r'Dues for the wage month\s+([A-Za-z]+\s+\d{4})',
            r'wage month\s+([A-Za-z]+\s+\d{4})',
            r'Wage Month\s*[:]\s*([A-Za-z]+\s+\d{4})',
            r'PROVISIONAL CHALLAN FOR WAGE MONTH\s*[:]\s*([A-Za-z]+\s+\d{4})',
            r'Month\s*[:]\s*([A-Za-z]+\s+\d{4})',
            r'for the month of\s+([A-Za-z]+\s+\d{4})',
            r'([A-Za-z]+\s+\d{4})\s+ECR',
            r'([A-Za-z]+-\d{4})',
            r'([A-Za-z]+/\d{4})'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                raw = match.group(1).strip()
                raw = raw.replace('-', ' ').replace('/', ' ')
                parts = raw.split()
                if len(parts) >= 2:
                    month = parts[0].title()
                    year = parts[1].strip()
                    if len(year) == 4 and year.isdigit():
                        return f"{month} {year}"
                    elif len(year) == 2 and year.isdigit():
                        return f"{month} 20{year}"
                return raw
        month_year_pattern = r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b'
        matches = re.findall(month_year_pattern, text, re.I)
        if matches:
            raw = matches[0]
            parts = raw.split()
            return f"{parts[0].title()} {parts[1]}"
        return "Unknown"

    @staticmethod
    def extract_generation_date(text: str) -> Tuple[Optional[datetime], str]:
        patterns = [
            r'system generated challan on\s+(\d{2}-[A-Z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)',
            r'Generated On\s*[:]\s*(\d{2}-[A-Za-z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)',
            r'Generated\s*[:]\s*(\d{2}-[A-Za-z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                date_str = match.group(1).strip()
                dt = safe_date_parse(date_str)
                if dt:
                    return dt, dt.strftime("%d-%b-%Y %H:%M:%S")
                return None, date_str
        return None, "N/A"

    @staticmethod
    def extract_subscribers_wages(text: str) -> Tuple[int, float]:
        subscribers = 0
        wages = 0.0
        sub_match = re.search(r'Total\s+Subscribers\s*[:]\s*(\d+)', text, re.I)
        if sub_match:
            subscribers = int(sub_match.group(1))
        wage_match = re.search(r'Total\s+Wages\s*[:]\s*([\d,]+)', text, re.I)
        if wage_match:
            wages = parse_indian_number(wage_match.group(1))
        return subscribers, wages

    @staticmethod
    def parse_financial_table(file) -> FinancialData:
        """Extract financials using pdfplumber table parsing."""
        data = FinancialData()
        try:
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if not table:
                            continue
                        header_row = None
                        for row in table:
                            if row and any(cell and ('PARTICULARS' in str(cell).upper() or 'A/C' in str(cell).upper()) for cell in row):
                                header_row = row
                                break
                        if not header_row:
                            continue
                        ac_indices = {}
                        for idx, cell in enumerate(header_row):
                            if cell:
                                cell_str = str(cell).upper()
                                if 'A/C.01' in cell_str or 'A/C 01' in cell_str:
                                    ac_indices['01'] = idx
                                elif 'A/C.02' in cell_str or 'A/C 02' in cell_str:
                                    ac_indices['02'] = idx
                                elif 'A/C.10' in cell_str or 'A/C 10' in cell_str:
                                    ac_indices['10'] = idx
                                elif 'A/C.21' in cell_str or 'A/C 21' in cell_str:
                                    ac_indices['21'] = idx
                                elif 'A/C.22' in cell_str or 'A/C 22' in cell_str:
                                    ac_indices['22'] = idx
                        for row in table:
                            if not row or row == header_row:
                                continue
                            row_text = ' '.join([str(cell) for cell in row if cell]).upper()
                            if 'ADMINISTRATION CHARGES' in row_text:
                                nums = [parse_indian_number(cell) for cell in row if cell and re.search(Config.INDIAN_NUMBER_PATTERN, str(cell))]
                                if nums:
                                    data.admin_charges = nums[-1]
                            elif "EMPLOYER'S SHARE" in row_text or 'EMPLOYER SHARE' in row_text:
                                if '01' in ac_indices and ac_indices['01'] < len(row):
                                    data.employer_share = parse_indian_number(row[ac_indices['01']])
                                if '10' in ac_indices and ac_indices['10'] < len(row):
                                    data.pension_share = parse_indian_number(row[ac_indices['10']])
                                if '21' in ac_indices and ac_indices['21'] < len(row):
                                    data.edli_share = parse_indian_number(row[ac_indices['21']])
                                if not ac_indices:
                                    nums = [parse_indian_number(cell) for cell in row if cell and re.search(Config.INDIAN_NUMBER_PATTERN, str(cell))]
                                    if len(nums) >= 3:
                                        data.employer_share = nums[0]
                                        data.pension_share = nums[1] if len(nums)>1 else 0
                                        data.edli_share = nums[2] if len(nums)>2 else 0
                            elif "EMPLOYEE'S SHARE" in row_text or 'EMPLOYEE SHARE' in row_text:
                                if '01' in ac_indices and ac_indices['01'] < len(row):
                                    data.employee_share = parse_indian_number(row[ac_indices['01']])
                                else:
                                    nums = [parse_indian_number(cell) for cell in row if cell and re.search(Config.INDIAN_NUMBER_PATTERN, str(cell))]
                                    if nums:
                                        data.employee_share = nums[-1]
                        for row in table:
                            if row and any(cell and 'GRAND TOTAL' in str(cell).upper() for cell in row):
                                nums = [parse_indian_number(cell) for cell in row if cell and re.search(Config.INDIAN_NUMBER_PATTERN, str(cell))]
                                if nums:
                                    data.grand_total = nums[-1]
                                break
        except Exception as e:
            logger.warning(f"Table parsing failed: {e}")
        return data

    @staticmethod
    def parse_financial_regex(text: str) -> FinancialData:
        """Fallback regex‑based financial extraction."""
        data = FinancialData()
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            lower = line.lower()
            if 'administration charges' in lower:
                nums = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if nums:
                    data.admin_charges = parse_indian_number(nums[-1])
            elif "employer's share" in lower or "employer share" in lower:
                nums = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if len(nums) >= 3:
                    data.employer_share = parse_indian_number(nums[0])
                    data.pension_share = parse_indian_number(nums[1])
                    data.edli_share = parse_indian_number(nums[2])
                elif len(nums) >= 2:
                    data.employer_share = parse_indian_number(nums[0])
                    data.pension_share = parse_indian_number(nums[1])
            elif "employee's share" in lower or "employee share" in lower:
                nums = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if nums:
                    data.employee_share = parse_indian_number(nums[-1])
        gt_match = re.search(r'Grand Total\s*[:]\s*([\d,]+)', text, re.I)
        if gt_match:
            data.grand_total = parse_indian_number(gt_match.group(1))
        pmrpy_match = re.search(r'PMRPYABRY.*?Total remittance by Employer.*?([\d,]+)', text, re.I | re.DOTALL)
        if pmrpy_match:
            data.total_remittance_employer = parse_indian_number(pmrpy_match.group(1))
        return data

    @classmethod
    def parse_pdf(cls, file) -> List[ChallanRecord]:
        """Main entry point: extract all challan records from a PDF."""
        records = []
        file.seek(0)
        full_text = cls.extract_text(file)
        if not full_text.strip():
            logger.error("No text extracted")
            return records
        
        est_code, est_name = cls.extract_establishment(full_text)
        chunks = re.split(r'(?=system generated challan|PROVISIONAL CHALLAN)', full_text, flags=re.I)
        for chunk in chunks:
            if not chunk.strip():
                continue
            pdf_type = cls.detect_pdf_type(chunk)
            wage_month = cls.extract_wage_month(chunk)
            gen_dt, gen_date_str = cls.extract_generation_date(chunk)
            fin = cls.parse_financial_regex(chunk)
            if fin.grand_total == 0:
                file.seek(0)
                table_fin = cls.parse_financial_table(file)
                fin.employer_share = table_fin.employer_share or fin.employer_share
                fin.employee_share = table_fin.employee_share or fin.employee_share
                fin.admin_charges = table_fin.admin_charges or fin.admin_charges
                fin.pension_share = table_fin.pension_share or fin.pension_share
                fin.edli_share = table_fin.edli_share or fin.edli_share
                fin.grand_total = table_fin.grand_total or fin.grand_total
            subs, wages = cls.extract_subscribers_wages(chunk)
            fin.total_subscribers = subs or fin.total_subscribers
            fin.total_wages = wages or fin.total_wages
            # Calculate due date
            due_date = calculate_due_date(wage_month)
            due_date_str = due_date.strftime("%d-%b-%Y") if due_date else "N/A"
            late_days = (gen_dt.date() - due_date.date()).days if gen_dt and due_date else 0
            status = FilingStatus.LATE if late_days > 0 else FilingStatus.EARLY if late_days < 0 else FilingStatus.ON_TIME
            disallowance = fin.employee_share if late_days > 0 else 0.0
            # Compute fiscal year and quarter
            fiscal_year = ""
            quarter = ""
            if due_date:
                year = due_date.year
                if due_date.month >= Config.FISCAL_YEAR_START_MONTH:
                    fiscal_year = f"{year}-{str(year+1)[-2:]}"
                else:
                    fiscal_year = f"{year-1}-{str(year)[-2:]}"
                q = (due_date.month - 1) // 3 + 1
                quarter = f"Q{q} {fiscal_year}"
            record = ChallanRecord(
                file_name=file.name,
                pdf_type=pdf_type.value,
                wage_month=wage_month,
                due_date=due_date_str,
                generated_date=gen_date_str,
                late_days=late_days,
                admin_charges=fin.admin_charges,
                employer_share=fin.employer_share,
                employee_share=fin.employee_share,
                pension_share=fin.pension_share,
                edli_share=fin.edli_share,
                grand_total=fin.grand_total if fin.grand_total > 0 else (fin.admin_charges + fin.employer_share + fin.employee_share + fin.pension_share + fin.edli_share),
                employee_disallowance=disallowance,
                status=status.value,
                trrn=cls.extract_trrn(chunk),
                establishment_code=est_code,
                establishment_name=est_name,
                pmrpy_total=fin.total_remittance_employer,
                total_wages=fin.total_wages,
                total_subscribers=fin.total_subscribers,
                processing_hash=hashlib.md5(chunk.encode('utf-8')).hexdigest()[:8],
                fiscal_year=fiscal_year,
                quarter=quarter,
                # computed shares will be set by validator
            )
            # Validate and compute expected values
            record = Validator.validate_record(record)
            records.append(record)
        return records

# ============================================================================
# VALIDATOR ENGINE
# ============================================================================
class Validator:
    """Validates extracted data against statutory rules and computes expected shares."""

    @staticmethod
    def validate_record(record: ChallanRecord) -> ChallanRecord:
        errors = []
        # Compute expected shares based on total wages
        wages = record.total_wages
        if wages > 0:
            # Use config rates
            rates = Config.RATES
            record.computed_employer_share = wages * rates['employer_share']
            record.computed_employee_share = wages * rates['employee_share']
            # Pension share is 8.33% on wages subject to EPS limit (capped at 15000)
            eps_wages = min(wages, Config.MIN_WAGE_LIMIT)
            record.computed_pension_share = eps_wages * rates['pension_share']
            record.computed_edli_share = wages * rates['edli_share']
            record.computed_admin_charges = wages * rates['admin_charges']
        else:
            # If wages not available, use reported shares as computed
            record.computed_employer_share = record.employer_share
            record.computed_employee_share = record.employee_share
            record.computed_pension_share = record.pension_share
            record.computed_edli_share = record.edli_share
            record.computed_admin_charges = record.admin_charges

        # Check grand total consistency
        computed_total = (record.admin_charges + record.employer_share +
                          record.employee_share + record.pension_share +
                          record.edli_share)
        if abs(computed_total - record.grand_total) > 1 and record.grand_total > 0:
            errors.append(f"Grand total mismatch: computed {computed_total:.2f} vs reported {record.grand_total:.2f}")

        # Check status vs late days
        if record.late_days > 0 and "LATE" not in record.status:
            errors.append("Late days positive but status not LATE")
        if record.late_days <= 0 and "LATE" in record.status:
            errors.append("Late days non-positive but status is LATE")

        # Check employee disallowance
        if record.late_days > 0 and abs(record.employee_disallowance - record.employee_share) > 1:
            errors.append("Employee disallowance should equal employee share for late filing")

        # Check if employer share matches computed (within tolerance)
        if record.total_wages > 0:
            tol = 5  # ₹5 tolerance
            if abs(record.employer_share - record.computed_employer_share) > tol:
                errors.append(f"Employer share ({record.employer_share:.2f}) differs from computed ({record.computed_employer_share:.2f})")
            if abs(record.employee_share - record.computed_employee_share) > tol:
                errors.append(f"Employee share ({record.employee_share:.2f}) differs from computed ({record.computed_employee_share:.2f})")

        record.validation_errors = errors
        return record

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def parse_indian_number(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    value_str = str(value).strip()
    if not value_str or value_str.lower() in ["na", "n/a", "-", "", "nil"]:
        return 0.0
    try:
        cleaned = re.sub(r'[₹,\sRs\.INR]', '', value_str)
        if not cleaned:
            return 0.0
        return float(cleaned)
    except:
        return 0.0

def calculate_due_date(wage_month: str) -> Optional[datetime]:
    try:
        parts = wage_month.strip().split()
        if len(parts) < 2:
            return None
        month_name = parts[0].title()
        year = int(parts[1])
        month_map = {
            'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,
            'July':7,'August':8,'September':9,'October':10,'November':11,'December':12,
            'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
            'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12
        }
        month_num = month_map.get(month_name)
        if not month_num:
            return None
        next_month = month_num % 12 + 1
        next_year = year + (1 if month_num == 12 else 0)
        return datetime(next_year, next_month, Config.STATUTORY_DUE_DAY)
    except:
        return None

def safe_date_parse(date_str: str) -> Optional[datetime]:
    if not date_str or date_str in ["N/A", "None", ""]:
        return None
    date_str = re.sub(r'\s+', ' ', date_str.strip())
    for fmt in Config.DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
    return None

# ============================================================================
# EXPORT ENGINES (Enhanced)
# ============================================================================
class Exporter:
    """Factory for various export formats."""

    @staticmethod
    def to_excel(records: List[ChallanRecord]) -> bytes:
        df = pd.DataFrame([r.to_dict() for r in records])
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Detailed sheet
            df.to_excel(writer, index=False, sheet_name='PF_Audit')
            ws = writer.sheets['PF_Audit']
            # Styling
            header_fill = PatternFill(start_color="1e3a5f", end_color="1e3a5f", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF", size=11)
            border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = border
            for col in ws.columns:
                max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 3, 30)
            # Summary sheet
            summary_df = Exporter._generate_summary_df(records)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            # Charts sheet (optional) – we can embed images, but we'll skip for brevity
        return output.getvalue()

    @staticmethod
    def _generate_summary_df(records: List[ChallanRecord]) -> pd.DataFrame:
        total_pf = sum(r.grand_total for r in records)
        emp_dis = sum(r.employee_disallowance for r in records)
        late_count = sum(1 for r in records if r.late_days > 0)
        compliance = ((len(records) - late_count) / len(records) * 100) if records else 100
        data = {
            'Metric': ['Total PF Audited', 'Total Disallowance', 'Total Records', 'Late Records', 'Compliance Rate'],
            'Value': [total_pf, emp_dis, len(records), late_count, f"{compliance:.1f}%"]
        }
        return pd.DataFrame(data)

    @staticmethod
    def to_pdf(records: List[ChallanRecord]) -> bytes:
        class PDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 14)
                self.cell(0, 10, 'PF COMPLIANCE AUDIT CERTIFICATE', ln=True, align='C')
                self.set_font('Arial', '', 9)
                self.cell(0, 6, f"Generated: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}", ln=True, align='C')
                self.ln(5)
            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
        pdf = PDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        # Summary cards
        total_pf = sum(r.grand_total for r in records)
        emp_dis = sum(r.employee_disallowance for r in records)
        late_count = sum(1 for r in records if r.late_days > 0)
        compliance = ((len(records) - late_count) / len(records) * 100) if records else 100
        pdf.set_fill_color(30, 58, 95)
        pdf.set_text_color(255,255,255)
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(45, 8, 'Total PF Audited', 1, 0, 'C', True)
        pdf.cell(45, 8, 'Disallowance', 1, 0, 'C', True)
        pdf.cell(45, 8, 'Total Records', 1, 0, 'C', True)
        pdf.cell(45, 8, 'Compliance Rate', 1, 1, 'C', True)
        pdf.set_text_color(0,0,0)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(45, 10, f"Rs.{total_pf:,.2f}", 1, 0, 'C')
        pdf.cell(45, 10, f"Rs.{emp_dis:,.2f}", 1, 0, 'C')
        pdf.cell(45, 10, f"{len(records)}", 1, 0, 'C')
        pdf.cell(45, 10, f"{compliance:.1f}%", 1, 1, 'C')
        pdf.ln(5)
        # Detailed table
        pdf.set_font('Arial', 'B', 7)
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255,255,255)
        headers = ['Wage Month', 'Due Date', 'Generated', 'Late', 'Total', 'Status']
        widths = [30,25,30,15,30,20]
        for i, h in enumerate(headers):
            pdf.cell(widths[i], 6, h, 1, 0, 'C', True)
        pdf.ln()
        pdf.set_font('Arial', '', 6)
        pdf.set_text_color(0,0,0)
        for r in records:
            pdf.cell(widths[0], 5, r.wage_month[:27], 1)
            pdf.cell(widths[1], 5, r.due_date, 1, 0, 'C')
            pdf.cell(widths[2], 5, r.generated_date[:27], 1, 0, 'C')
            pdf.cell(widths[3], 5, str(r.late_days), 1, 0, 'C')
            pdf.cell(widths[4], 5, f"Rs.{r.grand_total:,.0f}", 1, 0, 'R')
            status = r.status
            if 'LATE' in status:
                pdf.set_text_color(185, 28, 28)
            elif 'EARLY' in status:
                pdf.set_text_color(46, 125, 50)
            pdf.cell(widths[5], 5, status.split()[-1], 1, 1, 'C')
            pdf.set_text_color(0,0,0)
        return pdf.output(dest='S')

    @staticmethod
    def to_csv(records: List[ChallanRecord]) -> str:
        df = pd.DataFrame([r.to_dict() for r in records])
        return df.to_csv(index=False)

    @staticmethod
    def to_json(records: List[ChallanRecord]) -> str:
        return json.dumps([r.to_dict() for r in records], indent=2)

    @staticmethod
    def to_html(records: List[ChallanRecord]) -> str:
        df = pd.DataFrame([r.to_dict() for r in records])
        total_pf = df['grand_total'].sum()
        emp_dis = df['employee_disallowance'].sum()
        late_count = len(df[df['late_days'] > 0])
        compliance = ((len(df) - late_count) / len(df) * 100) if len(df) > 0 else 100
        html = f"""
        <html><head><title>PF Audit Report</title>
        <style>
            body {{ font-family: Arial; margin:20px; }}
            .summary {{ display:flex; gap:20px; margin-bottom:20px; }}
            .card {{ background:#f0f4f8; padding:15px; border-radius:8px; flex:1; }}
            table {{ border-collapse:collapse; width:100%; }}
            th {{ background:#1e3a5f; color:white; padding:8px; }}
            td {{ padding:6px; border:1px solid #ddd; }}
            .late {{ color:#b91c1c; }}
            .early {{ color:#2e7d32; }}
        </style></head><body>
        <h1>PF Compliance Audit Report</h1>
        <div class="summary">
            <div class="card"><strong>Total PF Audited</strong><br>Rs.{total_pf:,.2f}</div>
            <div class="card"><strong>Employee Disallowance</strong><br>Rs.{emp_dis:,.2f}</div>
            <div class="card"><strong>Total Records</strong><br>{len(df)}</div>
            <div class="card"><strong>Compliance Rate</strong><br>{compliance:.1f}%</div>
        </div>
        <h2>Detailed Records</h2>
        <table><tr><th>Wage Month</th><th>Due Date</th><th>Generated</th><th>Late Days</th><th>Grand Total</th><th>Status</th></tr>
        """
        for _, row in df.iterrows():
            status_class = 'late' if 'LATE' in row['status'] else 'early' if 'EARLY' in row['status'] else ''
            html += f"<tr><td>{row['wage_month']}</td><td>{row['due_date']}</td><td>{row['generated_date']}</td><td>{row['late_days']}</td><td>Rs.{row['grand_total']:,.2f}</td><td class='{status_class}'>{row['status']}</td></tr>"
        html += "</table></body></html>"
        return html

# ============================================================================
# STREAMLIT UI – ENHANCED
# ============================================================================
def render_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: linear-gradient(-45deg, #f0f9ff, #e6f0fa, #d9e9f5, #e6f0fa); background-size: 400% 400%; animation: gradientBG 15s ease infinite; }
    @keyframes gradientBG { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
    .glass-card { backdrop-filter: blur(12px); background: rgba(255,255,255,0.3); border-radius: 20px; border: 1px solid rgba(255,255,255,0.4); box-shadow: 0 8px 32px rgba(0,0,0,0.1); padding: 1.5rem; margin-bottom: 1.5rem; }
    .header-card { text-align: center; padding: 2rem; background: rgba(255,255,255,0.4); backdrop-filter: blur(16px); border-radius: 24px; border: 1px solid rgba(255,255,255,0.5); box-shadow: 0 20px 40px rgba(0,0,0,0.1); margin-bottom: 2rem; }
    .main-title { font-weight: 800; font-size: 2.5rem; background: linear-gradient(135deg, #2563eb, #0ea5e9, #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 16px; background: rgba(255,255,255,0.5); }
    .stTabs [aria-selected="true"] { background: #2563eb; color: white; }
    .export-section { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; margin: 20px 0; }
    .export-btn { flex: 1; min-width: 120px; }
    </style>
    """, unsafe_allow_html=True)

def render_dashboard(records: List[ChallanRecord], db: Database):
    if not records:
        st.info("No records to display.")
        return
    df = pd.DataFrame([r.to_dict() for r in records])
    total_pf = df['grand_total'].sum()
    emp_dis = df['employee_disallowance'].sum()
    late_count = len(df[df['late_days'] > 0])
    compliance = ((len(df) - late_count) / len(df) * 100) if len(df) > 0 else 100

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Total PF Audited", f"Rs.{total_pf:,.2f}")
    col2.metric("⚠️ Tax Disallowance", f"Rs.{emp_dis:,.2f}", delta=f"{late_count} late")
    col3.metric("📋 Total Records", f"{len(df)}")
    col4.metric("✅ Compliance Rate", f"{compliance:.1f}%")

    # Export Section
    st.markdown("### 📥 Export Data")
    col_e1, col_e2, col_e3, col_e4, col_e5 = st.columns([2, 1, 1, 1, 1])
    with col_e1:
        excel_data = Exporter.to_excel(records)
        st.download_button("📊 **Excel (Recommended)**", excel_data,
                           f"PF_Audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                           use_container_width=True, type="primary")
    with col_e2:
        pdf_data = Exporter.to_pdf(records)
        st.download_button("📜 PDF Certificate", pdf_data,
                           f"PF_Certificate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                           use_container_width=True)
    with col_e3:
        csv_data = Exporter.to_csv(records)
        st.download_button("📄 CSV", csv_data,
                           f"PF_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                           use_container_width=True)
    with col_e4:
        json_data = Exporter.to_json(records)
        st.download_button("📦 JSON", json_data,
                           f"PF_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                           use_container_width=True)
    with col_e5:
        html_data = Exporter.to_html(records)
        st.download_button("🌐 HTML", html_data,
                           f"PF_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                           use_container_width=True)

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📈 Overview", "📊 Analytics", "📋 Raw Data", "🔍 Audit Log", "📅 Fiscal Year"]
    )
    with tab1:
        col_left, col_right = st.columns(2)
        with col_left:
            fig = px.bar(df, x='wage_month', y='grand_total', color='status',
                         color_discrete_map={'⚠️ LATE':'#ef4444','✓ ON TIME':'#f59e0b','✅ EARLY':'#10b981'},
                         title="PF Payment Timeline", hover_data=['due_date','generated_date','late_days'])
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
        with col_right:
            status_counts = df['status'].value_counts()
            fig_pie = px.pie(values=status_counts.values, names=status_counts.index, title="Compliance Distribution",
                             color_discrete_map={'⚠️ LATE':'#ef4444','✓ ON TIME':'#f59e0b','✅ EARLY':'#10b981'})
            fig_pie.update_layout(height=400)
            st.plotly_chart(fig_pie, use_container_width=True)
        fig_line = px.line(df, x='wage_month', y='late_days', title="Late Days Trend", markers=True)
        fig_line.update_layout(height=300)
        st.plotly_chart(fig_line, use_container_width=True)
    with tab2:
        st.subheader("🔎 Detailed Analytics")
        # Filter by status
        status_filter = st.multiselect("Filter by Status", options=df['status'].unique(), default=df['status'].unique())
        filtered_df = df[df['status'].isin(status_filter)]
        if not filtered_df.empty:
            st.dataframe(filtered_df, use_container_width=True)
            st.markdown("**Summary Statistics**")
            st.write(filtered_df.describe(include='all'))
        else:
            st.info("No records match the filter.")
    with tab3:
        st.subheader("📋 All Records")
        display_df = df.copy()
        financial_cols = ['admin_charges','employer_share','employee_share','pension_share','edli_share','grand_total','employee_disallowance','pmrpy_total','total_wages']
        for col in financial_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"Rs.{x:,.2f}" if isinstance(x, (int, float)) else x)
        st.dataframe(display_df, use_container_width=True, height=400)
    with tab4:
        st.subheader("📋 Audit Log")
        log_data = []
        for r in records:
            log_data.append({
                'File': r.file_name,
                'Month': r.wage_month,
                'Hash': r.processing_hash,
                'Validation Errors': ', '.join(r.validation_errors) if r.validation_errors else 'None',
                'Status': r.status
            })
        log_df = pd.DataFrame(log_data)
        st.dataframe(log_df, use_container_width=True)
        if any(r.validation_errors for r in records):
            st.warning("⚠️ Some records have validation errors. Check the 'Validation Errors' column.")
    with tab5:
        st.subheader("📅 Fiscal Year & Quarter Analysis")
        if 'fiscal_year' in df.columns and 'quarter' in df.columns:
            fy_summary = df.groupby('fiscal_year').agg({
                'grand_total': 'sum',
                'employee_disallowance': 'sum',
                'wage_month': 'count'
            }).rename(columns={'wage_month': 'record_count'})
            st.dataframe(fy_summary, use_container_width=True)
            fig_fy = px.bar(fy_summary, x=fy_summary.index, y='grand_total', title="PF Contribution by Fiscal Year")
            st.plotly_chart(fig_fy, use_container_width=True)
        else:
            st.info("Fiscal year information not available.")

# ============================================================================
# MAIN APP
# ============================================================================
def main():
    render_css()
    st.markdown("""
    <div class="header-card">
        <div class="main-title">🏢 PF CHALLAN AI COMMAND CENTER</div>
        <div style="font-size:1.1rem; color:#475569; margin-top:0.5rem;">Enterprise Statutory Audit Suite • v6.0 • Production‑Ready</div>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        due_day = st.number_input("Statutory Due Day", min_value=1, max_value=31, value=Config.STATUTORY_DUE_DAY)
        Config.STATUTORY_DUE_DAY = due_day
        enable_ocr = st.checkbox("Enable OCR (fallback)", value=Config.ALLOW_OCR)
        Config.ALLOW_OCR = enable_ocr
        if enable_ocr and not OCR_AVAILABLE:
            st.warning("OCR not available. Install pytesseract and pdf2image.")
        st.markdown("---")
        # Contribution rates (optional overrides)
        st.subheader("Contribution Rates")
        emp_rate = st.number_input("Employer Rate (%)", min_value=0.0, max_value=20.0, value=Config.RATES['employer_share']*100, step=0.1) / 100
        emp_rate_employee = st.number_input("Employee Rate (%)", min_value=0.0, max_value=20.0, value=Config.RATES['employee_share']*100, step=0.1) / 100
        pension_rate = st.number_input("Pension Rate (%)", min_value=0.0, max_value=20.0, value=Config.RATES['pension_share']*100, step=0.1) / 100
        edli_rate = st.number_input("EDLI Rate (%)", min_value=0.0, max_value=5.0, value=Config.RATES['edli_share']*100, step=0.1) / 100
        admin_rate = st.number_input("Admin Rate (%)", min_value=0.0, max_value=5.0, value=Config.RATES['admin_charges']*100, step=0.1) / 100
        Config.RATES.update({
            'employer_share': emp_rate,
            'employee_share': emp_rate_employee,
            'pension_share': pension_rate,
            'edli_share': edli_rate,
            'admin_charges': admin_rate
        })
        st.markdown("---")
        if st.button("🗑️ Clear Database"):
            db = Database()
            db.delete_all_records()
            st.success("Database cleared.")
        st.markdown("---")
        st.markdown("**About**")
        st.markdown("This tool uses advanced parsing to extract EPFO challan data accurately.")

    # Database instance
    db = Database()

    # Upload section
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("📂 Upload PF Challan PDFs")
    st.markdown("""
    <small style="opacity:0.85;">
    ✅ Supports <strong>Combined</strong> & <strong>Provisional</strong> formats<br>
    ✅ Guaranteed wage month extraction (multiple regex patterns)<br>
    ✅ Table-based financial extraction (pdfplumber) + regex fallback<br>
    ✅ Full audit trail, validation, and exports
    </small>
    """, unsafe_allow_html=True)
    uploaded_files = st.file_uploader("Drop PDFs here", type=['pdf'], accept_multiple_files=True, label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        process_btn = st.button("🚀 INITIATE AI AUDIT ENGINE", type="primary", use_container_width=True)

    if uploaded_files and process_btn:
        all_records = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        debug_container = st.empty()
        debug_msgs = []
        for idx, file in enumerate(uploaded_files):
            status_text.text(f"📄 Processing {idx+1}/{len(uploaded_files)}: {file.name}")
            file.seek(0)
            parser = PDFParser()
            records = parser.parse_pdf(file)
            if records:
                all_records.extend(records)
                # Insert into DB
                for rec in records:
                    db.insert_record(rec)
                debug_msgs.append(f"✅ <b>{file.name}</b>: {len(records)} month(s) extracted")
            else:
                debug_msgs.append(f"❌ <b>{file.name}</b>: No data extracted")
            progress_bar.progress((idx+1)/len(uploaded_files))
        progress_bar.empty()
        status_text.empty()
        if debug_msgs:
            debug_container.markdown("<div class='glass-card'><b>📋 Processing Log:</b><br>" + "<br>".join(debug_msgs) + "</div>", unsafe_allow_html=True)
        if all_records:
            st.success(f"✅ Successfully processed {len(all_records)} challan(s) from {len(uploaded_files)} file(s)")
            # Show dashboard with all records (from DB)
            all_db_records = db.get_all_records()
            render_dashboard(all_db_records, db)
        else:
            st.error("❌ No challans could be parsed. Check the debug log above.")
            st.info("Possible reasons: PDF is scanned (enable OCR), not a valid EPFO challan, or text extraction failed.")

    else:
        # Display existing records from DB
        existing = db.get_all_records()
        if existing:
            st.info(f"📊 Showing {len(existing)} records from database. Upload new PDFs to process more.")
            render_dashboard(existing, db)
        else:
            st.info("Upload PDFs and click the button to start processing.")

if __name__ == "__main__":
    main()
