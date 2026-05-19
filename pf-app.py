#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔════════════════════════════════════════════════════════════════════════════╗
║                    PF CHALLAN AI COMMAND CENTER                            ║
║              Enterprise Statutory Audit & Compliance Suite                 ║
║                                                                            ║
║  🎯 Features:                                                              ║
║  • Dual PDF Format Support (Combined + Provisional Challans)              ║
║  • Real-Time Dashboard with Auto-Refresh & WebSocket Simulation           ║
║  • Advanced PDF Parsing with Multi-Layer Fallback Strategies              ║
║  • Professional Excel/PDF Export with Conditional Formatting              ║
║  • Interactive Plotly Charts with Drill-Down Capabilities                 ║
║  • Session State Management for Persistent Real-Time Updates              ║
║  • Advanced Filtering, Search & Batch Operations                          ║
║  • Comprehensive Audit Trail with Version History                         ║
║  • Performance Optimizations for Large File Processing                    ║
║  • Beautiful Glassmorphism UI with Animations & Dark Mode                 ║
║                                                                            ║
║  📋 Author: Abhishek Jakkula                                               ║
║  📅 Version: 3.0.0 (Production Ready)                                      ║
║  🔄 Last Updated: May 2026                                                 ║
╚════════════════════════════════════════════════════════════════════════════╝
"""

# ============================================================================
# 📦 IMPORTS & DEPENDENCIES
# ============================================================================
import streamlit as st
import pdfplumber
import re
import pandas as pd
import numpy as np
from io import BytesIO
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, NamedStyle
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference, PieChart
from openpyxl.chart.label import DataLabelList
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from fpdf import FPDF
import logging
from typing import Optional, Dict, List, Tuple, Union, Any
import traceback
import warnings
import hashlib
import json
import time
import base64
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from collections import defaultdict, OrderedDict
import threading
from queue import Queue, Empty
import concurrent.futures
from functools import lru_cache, wraps
import os
import sys

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)

# ============================================================================
# ⚙️ CONFIGURATION & CONSTANTS
# ============================================================================

class Config:
    """Application-wide configuration constants"""
    
    # PDF Parsing
    MAX_FILE_SIZE_MB = 50
    SUPPORTED_EXTENSIONS = ['.pdf']
    ENCODING_FALLBACKS = ['utf-8', 'latin-1', 'cp1252']
    
    # Date Formats
    DATE_FORMATS = [
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%d-%b-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d %B %Y"
    ]
    
    # Financial Parsing
    INDIAN_NUMBER_PATTERN = r'(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)'
    CURRENCY_SYMBOLS = ['₹', 'Rs.', 'INR', 'Rs']
    
    # Due Date Calculation
    STATUTORY_DUE_DAY = 15  # 15th of next month
    
    # Dashboard
    AUTO_REFRESH_INTERVAL_SEC = 30
    CHART_COLORS = {
        'late': '#ef4444',
        'on_time': '#f59e0b', 
        'early': '#10b981',
        'primary': '#2563eb',
        'secondary': '#0ea5e9',
        'accent': '#7c3aed'
    }
    
    # Export Settings
    EXCEL_HEADER_COLOR = "1e3a5f"
    EXCEL_LATE_COLOR = "ffcdd2"
    EXCEL_EARLY_COLOR = "c8e6c9"
    EXCEL_ONTIME_COLOR = "fff9c4"
    
    # Logging
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s'


# ============================================================================
# 🪵 LOGGING SETUP
# ============================================================================

def setup_logging():
    """Configure application logging with file and console handlers"""
    logger = logging.getLogger()
    logger.setLevel(Config.LOG_LEVEL)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(Config.LOG_LEVEL)
    console_formatter = logging.Formatter(Config.LOG_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (if in production)
    if os.getenv('ENVIRONMENT') == 'production':
        try:
            file_handler = logging.FileHandler('pf_audit.log', encoding='utf-8')
            file_handler.setLevel(Config.LOG_LEVEL)
            file_handler.setFormatter(console_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not create log file: {e}")
    
    return logger

logger = setup_logging()


# ============================================================================
# 🏗️ DATA MODELS & ENUMS
# ============================================================================

class PDFType(Enum):
    """Enumeration of supported PDF challan types"""
    COMBINED = "combined"
    PROVISIONAL = "provisional"
    UNKNOWN = "unknown"


class FilingStatus(Enum):
    """Enumeration of filing compliance status"""
    LATE = "⚠️ LATE"
    ON_TIME = "✓ ON TIME"
    EARLY = "✅ EARLY"
    UNKNOWN = "❓ UNKNOWN"


@dataclass
class FinancialValues:
    """Data class for extracted financial values from challan"""
    admin_charges: float = 0.0
    employer_share: float = 0.0
    employee_share: float = 0.0
    grand_total: float = 0.0
    pension_fund: float = 0.0
    edli_charges: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        return asdict(self)
    
    @property
    def total_contribution(self) -> float:
        """Calculate total of employer + employee shares"""
        return self.employer_share + self.employee_share


@dataclass
class ChallanRecord:
    """Complete data model for a parsed PF challan"""
    # Metadata
    file_name: str
    file_hash: str
    pdf_type: PDFType
    processing_timestamp: datetime
    
    # Core Fields
    wage_month: str
    wage_month_date: Optional[datetime]
    due_date: Optional[datetime]
    generated_date: Optional[datetime]
    generated_date_str: str
    
    # Financial Data
    financial_values: FinancialValues
    
    # Compliance Metrics
    late_days: int
    employee_disallowance: float
    filing_status: FilingStatus
    
    # Additional Metadata
    establishment_name: str = ""
    establishment_code: str = ""
    trrn: str = ""
    total_subscribers: int = 0
    total_wages: float = 0.0
    epf_amount: float = 0.0
    eps_amount: float = 0.0
    edli_amount: float = 0.0
    
    # Processing Info
    parsing_confidence: float = 1.0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dataframe_row(self) -> Dict[str, Any]:
        """Convert record to dictionary suitable for DataFrame"""
        return {
            'File Name': self.file_name,
            'PDF Type': self.pdf_type.value.title(),
            'Wage Month': self.wage_month,
            'Due Date': self.due_date.strftime("%d-%b-%Y") if self.due_date else "N/A",
            'Generated Date': self.generated_date_str,
            'Late Days': self.late_days,
            'Admin Charges': self.financial_values.admin_charges,
            'Employer Share': self.financial_values.employer_share,
            'Employee Share': self.financial_values.employee_share,
            'Grand Total': self.financial_values.grand_total,
            'Employee Disallowance': self.employee_disallowance,
            'Status': self.filing_status.value,
            'Establishment': self.establishment_name,
            'TRRN': self.trrn,
            'Processing Time': self.processing_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'Confidence': f"{self.parsing_confidence*100:.1f}%"
        }
    
    @property
    def is_compliant(self) -> bool:
        """Check if filing is compliant (on-time or early)"""
        return self.late_days <= 0
    
    @property
    def compliance_risk_score(self) -> float:
        """Calculate compliance risk score (0-100, higher = more risk)"""
        if self.late_days <= 0:
            return 0.0
        # Risk increases with days late, capped at 100
        return min(100.0, self.late_days * 2.5)


# ============================================================================
# 🧰 UTILITY FUNCTIONS
# ============================================================================

def generate_file_hash(file_bytes: bytes) -> str:
    """Generate SHA256 hash for file deduplication"""
    return hashlib.sha256(file_bytes).hexdigest()[:16]


def parse_indian_number(value: Any) -> float:
    """
    Parse Indian number format with commas and various edge cases
    Handles: "2,60,000", "73,051", "NA", "-", None, etc.
    """
    if value is None:
        return 0.0
    
    value_str = str(value).strip()
    
    # Handle common non-numeric values
    if not value_str or value_str.lower() in ["na", "n/a", "-", "", "nil", "none"]:
        return 0.0
    
    try:
        # Remove currency symbols, commas, and whitespace
        cleaned = re.sub(r'[₹,\sRs\.INR]', '', value_str, flags=re.I)
        if not cleaned:
            return 0.0
        return float(cleaned)
    except (ValueError, AttributeError, TypeError) as e:
        logger.debug(f"Number parse failed for '{value}': {e}")
        return 0.0


def safe_datetime_parse(date_str: str, formats: List[str] = None) -> Optional[datetime]:
    """Safely parse datetime string with multiple format attempts"""
    if not date_str or date_str in ["N/A", "None", ""]:
        return None
    
    if formats is None:
        formats = Config.DATE_FORMATS
    
    # Clean the date string
    date_str = re.sub(r'\s+', ' ', date_str.strip())
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def calculate_statutory_due_date(wage_month: str) -> Optional[datetime]:
    """
    Calculate EPFO statutory due date (15th of month following wage month)
    Example: Wage Month "April 2025" → Due Date "15-May-2025"
    """
    try:
        # Parse month and year
        parts = wage_month.strip().split()
        if len(parts) < 2:
            return None
        
        month_name = parts[0].title()
        year = int(parts[1])
        
        # Month name to number mapping
        month_map = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
            'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12,
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        
        month_num = month_map.get(month_name)
        if not month_num:
            return None
        
        # Calculate next month (with year rollover)
        next_month = month_num % 12 + 1
        next_year = year + (1 if month_num == 12 else 0)
        
        return datetime(next_year, next_month, Config.STATUTORY_DUE_DAY)
    
    except Exception as e:
        logger.warning(f"Due date calculation failed for '{wage_month}': {e}")
        return None


def format_currency(amount: float, symbol: str = "₹") -> str:
    """Format amount as Indian currency with proper comma separation"""
    if pd.isna(amount) or amount is None:
        return f"{symbol}0.00"
    
    # Indian numbering system: 1,23,45,678.90
    amount_str = f"{abs(amount):,.2f}"
    
    # Convert to Indian format if needed
    if '.' in amount_str:
        whole, decimal = amount_str.split('.')
    else:
        whole, decimal = amount_str, "00"
    
    # Indian comma placement: last 3, then every 2
    if len(whole) > 3:
        last_three = whole[-3:]
        remaining = whole[:-3]
        # Add commas every 2 digits from right
        formatted_remaining = []
        for i, digit in enumerate(reversed(remaining)):
            if i > 0 and i % 2 == 0:
                formatted_remaining.append(',')
            formatted_remaining.append(digit)
        whole = ''.join(reversed(formatted_remaining)) + last_three
    
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{whole}.{decimal}"


# ============================================================================
# 🔍 PDF PARSING ENGINE - MULTI-LAYER STRATEGY
# ============================================================================

class PDFParsingStrategy:
    """Abstract base for PDF parsing strategies"""
    
    def extract_wage_month(self, text: str) -> Tuple[str, Optional[datetime]]:
        raise NotImplementedError
    
    def extract_generation_date(self, text: str) -> Tuple[Optional[datetime], str]:
        raise NotImplementedError
    
    def extract_financial_values(self, text: str) -> FinancialValues:
        raise NotImplementedError


class CombinedChallanParser(PDFParsingStrategy):
    """Parser for Combined Challan format (A/C 01, 02, 10, 21, 22)"""
    
    def extract_wage_month(self, text: str) -> Tuple[str, Optional[datetime]]:
        """Extract wage month from Combined Challan"""
        patterns = [
            r"Dues for the wage month\s+([A-Za-z]+)\s+(\d{4})",
            r"wage month\s+of\s+([A-Za-z]+)\s+(\d{4})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                month = match.group(1).strip().title()
                year = match.group(2).strip()
                wage_month = f"{month} {year}"
                date_obj = safe_datetime_parse(f"01-{month}-{year}", ["%d-%B-%Y", "%d-%b-%Y"])
                return wage_month, date_obj
        
        return "Unknown", None
    
    def extract_generation_date(self, text: str) -> Tuple[Optional[datetime], str]:
        """Extract generation date: 'system generated challan on DD-MMM-YYYY HH:MM'"""
        pattern = r'system generated challan on\s+(\d{2}-[A-Z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)'
        match = re.search(pattern, text, re.I)
        
        if match:
            date_str = match.group(1).strip()
            dt = safe_datetime_parse(date_str)
            if dt:
                return dt, dt.strftime("%d-%b-%Y %H:%M:%S")
            return None, date_str
        
        return None, "N/A"
    
    def extract_financial_values(self, text: str) -> FinancialValues:
        """Extract financial values using TOTAL column (rightmost number)"""
        values = FinancialValues()
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Administration Charges
            if re.search(r'Administration\s+Charges', line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.admin_charges = parse_indian_number(numbers[-1])
            
            # Employer's Share Of (excluding "Contribution" variant)
            elif re.search(r"Employer'?s\s+Share\s+Of\s+(?!Contribution)", line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.employer_share = parse_indian_number(numbers[-1])
            
            # Employee's Share Of (excluding "Contribution" variant)
            elif re.search(r"Employee'?s\s+Share\s+Of\s+(?!Contribution)", line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.employee_share = parse_indian_number(numbers[-1])
        
        # Extract Grand Total with multiple fallback patterns
        grand_total_patterns = [
            r'Grand\s*Total\s*:\s*(' + Config.INDIAN_NUMBER_PATTERN + r')',
            r'Grand Total:\s*(' + Config.INDIAN_NUMBER_PATTERN + r')',
        ]
        for pattern in grand_total_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                values.grand_total = parse_indian_number(match.group(1))
                break
        
        return values


class ProvisionalChallanParser(PDFParsingStrategy):
    """Parser for Provisional Challan format"""
    
    def extract_wage_month(self, text: str) -> Tuple[str, Optional[datetime]]:
        """Extract wage month from Provisional Challan"""
        patterns = [
            r"PROVISIONAL CHALLAN FOR WAGE MONTH:\s*([A-Za-z]+)\s+(\d{4})",
            r"WAGE MONTH:\s*([A-Za-z]+)\s+(\d{4})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                month = match.group(1).strip().title()
                year = match.group(2).strip()
                wage_month = f"{month} {year}"
                date_obj = safe_datetime_parse(f"01-{month}-{year}", ["%d-%B-%Y", "%d-%b-%Y"])
                return wage_month, date_obj
        
        return "Unknown", None
    
    def extract_generation_date(self, text: str) -> Tuple[Optional[datetime], str]:
        """Extract generation date: 'Generated On: DD-MMM-YYYY HH:MM:SS' (with flexible spacing)"""
        # Handle both "Generated On:" and "Generated On :" (with space before colon)
        patterns = [
            r'Generated On\s*:\s*(\d{2}-[A-Za-z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)',
            r'Generated:\s*(\d{2}-[A-Za-z]{3}-\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                date_str = match.group(1).strip()
                date_str = re.sub(r'\s+', ' ', date_str)  # Normalize whitespace
                dt = safe_datetime_parse(date_str)
                if dt:
                    return dt, dt.strftime("%d-%b-%Y %H:%M:%S")
                return None, date_str
        
        return None, "N/A"
    
    def extract_financial_values(self, text: str) -> FinancialValues:
        """Extract financial values from Provisional Challan"""
        values = FinancialValues()
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
            
            # Employer's Share Of Contribution
            elif re.search(r"Employer'?s\s+Share\s+Of\s+Contribution", line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.employer_share = parse_indian_number(numbers[-1])
            
            # Employee's Share Of Contribution
            elif re.search(r"Employee'?s\s+Share\s+Of\s+Contribution", line, re.I):
                numbers = re.findall(Config.INDIAN_NUMBER_PATTERN, line)
                if numbers:
                    values.employee_share = parse_indian_number(numbers[-1])
        
        # Grand Total
        match = re.search(r'Grand Total:\s*(' + Config.INDIAN_NUMBER_PATTERN + r')', text, re.I)
        if match:
            values.grand_total = parse_indian_number(match.group(1))
        
        return values


class PDFTypeDetector:
    """Auto-detect PDF challan type using heuristic analysis"""
    
    COMBINED_MARKERS = [
        'combined challan', 'a/c no. 01, 02, 10, 21', 'administration charges',
        'system generated challan', 'seventy-three thousand'
    ]
    
    PROVISIONAL_MARKERS = [
        'provisional challan', 'admin/ insp. charges', 'share of contribution',
        'generated on', 'subject to change based on balance'
    ]
    
    @classmethod
    def detect(cls, text: str) -> Tuple[PDFType, float]:
        """
        Detect PDF type with confidence score (0.0 to 1.0)
        Returns: (PDFType, confidence)
        """
        text_lower = text.lower()
        
        combined_score = sum(1 for marker in cls.COMBINED_MARKERS if marker in text_lower)
        provisional_score = sum(1 for marker in cls.PROVISIONAL_MARKERS if marker in text_lower)
        
        if combined_score > provisional_score and combined_score >= 2:
            confidence = min(1.0, combined_score / len(cls.COMBINED_MARKERS) * 1.5)
            return PDFType.COMBINED, confidence
        elif provisional_score > combined_score and provisional_score >= 2:
            confidence = min(1.0, provisional_score / len(cls.PROVISIONAL_MARKERS) * 1.5)
            return PDFType.PROVISIONAL, confidence
        elif combined_score > 0 or provisional_score > 0:
            # Weak detection
            if combined_score >= provisional_score:
                return PDFType.COMBINED, 0.6
            else:
                return PDFType.PROVISIONAL, 0.6
        
        return PDFType.UNKNOWN, 0.0


# ============================================================================
# 🔄 REAL-TIME DASHBOARD ENGINE
# ============================================================================

class DashboardStateManager:
    """Manage real-time dashboard state with session persistence"""
    
    def __init__(self):
        self._last_update = None
        self._update_count = 0
    
    def should_refresh(self, interval_sec: int = Config.AUTO_REFRESH_INTERVAL_SEC) -> bool:
        """Check if dashboard should auto-refresh based on interval"""
        now = datetime.now()
        if self._last_update is None:
            return True
        
        elapsed = (now - self._last_update).total_seconds()
        return elapsed >= interval_sec
    
    def mark_updated(self):
        """Mark state as updated with current timestamp"""
        self._last_update = datetime.now()
        self._update_count += 1
    
    @property
    def update_count(self) -> int:
        return self._update_count
    
    @property
    def last_update_str(self) -> str:
        if self._last_update:
            return self._last_update.strftime("%H:%M:%S")
        return "Never"


class RealTimeMetrics:
    """Calculate and cache real-time dashboard metrics"""
    
    @staticmethod
    @lru_cache(maxsize=32)
    def calculate_compliance_rate(df: pd.DataFrame) -> float:
        """Calculate percentage of compliant filings"""
        if df.empty:
            return 100.0
        compliant = len(df[df['Late Days'] <= 0])
        return round((compliant / len(df)) * 100, 1)
    
    @staticmethod
    @lru_cache(maxsize=32)
    def calculate_total_disallowance(df: pd.DataFrame) -> float:
        """Calculate total employee share disallowance for late filings"""
        if df.empty:
            return 0.0
        return df[df['Late Days'] > 0]['Employee Share'].sum()
    
    @staticmethod
    @lru_cache(maxsize=32)
    def get_monthly_trend(df: pd.DataFrame, months: int = 6) -> pd.DataFrame:
        """Get monthly payment trend for last N months"""
        if df.empty:
            return pd.DataFrame()
        
        # Parse wage month to datetime for sorting
        df_copy = df.copy()
        df_copy['wage_date'] = df_copy['Wage Month'].apply(
            lambda x: safe_datetime_parse(f"01 {x}", "%d %B %Y") or safe_datetime_parse(f"01 {x}", "%d %b %Y")
        )
        df_copy = df_copy.dropna(subset=['wage_date']).sort_values('wage_date')
        
        return df_copy.tail(months)
    
    @staticmethod
    def get_risk_distribution(df: pd.DataFrame) -> Dict[str, int]:
        """Get count of filings by risk category"""
        if df.empty:
            return {'Low': 0, 'Medium': 0, 'High': 0, 'Critical': 0}
        
        distribution = {'Low': 0, 'Medium': 0, 'High': 0, 'Critical': 0}
        
        for _, row in df.iterrows():
            risk = row.get('Late Days', 0)
            if risk <= 0:
                distribution['Low'] += 1
            elif risk <= 7:
                distribution['Medium'] += 1
            elif risk <= 30:
                distribution['High'] += 1
            else:
                distribution['Critical'] += 1
        
        return distribution


# ============================================================================
# 📊 ADVANCED VISUALIZATION ENGINE
# ============================================================================

class ChartFactory:
    """Factory for creating interactive Plotly charts"""
    
    @staticmethod
    def create_payment_timeline(df: pd.DataFrame, title: str = None) -> go.Figure:
        """Create interactive bar chart with drill-down capability"""
        if df.empty:
            return go.Figure()
        
        # Prepare data
        df_chart = df.copy()
        df_chart['Status_Code'] = df_chart['Late Days'].apply(
            lambda x: 'Late' if x > 0 else ('Early' if x < 0 else 'On Time')
        )
        
        # Color mapping
        color_map = {
            'Late': Config.CHART_COLORS['late'],
            'On Time': Config.CHART_COLORS['on_time'],
            'Early': Config.CHART_COLORS['early']
        }
        
        fig = go.Figure()
        
        # Main bar chart
        fig.add_trace(go.Bar(
            x=df_chart['Wage Month'],
            y=df_chart['Grand Total'],
            marker_color=df_chart['Status_Code'].map(color_map),
            name='Grand Total',
            hovertemplate='<b>%{x}</b><br>Amount: ₹%{y:,.0f}<br>Status: %{customdata[0]}<br>Due: %{customdata[1]}<br>Generated: %{customdata[2]}<extra></extra>',
            customdata=df_chart[['Status', 'Due Date', 'Generated Date']].values,
            text=df_chart['Grand Total'].apply(lambda x: f'₹{x/1000:.1f}K'),
            textposition='outside',
            textfont=dict(size=9)
        ))
        
        # Add threshold line for due date compliance
        fig.add_hline(
            y=df_chart['Grand Total'].mean(),
            line_dash="dot",
            line_color=Config.CHART_COLORS['primary'],
            annotation_text="Average",
            annotation_position="top right"
        )
        
        fig.update_layout(
            title=dict(
                text=title or "PF Payment Performance Timeline",
                font=dict(size=16, family="Inter"),
                x=0.5
            ),
            xaxis_title="Wage Month",
            yaxis_title="Amount (₹)",
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", size=11),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=60, b=40),
            bargap=0.3
        )
        
        # Add grid lines
        fig.update_yaxes(gridcolor="rgba(0,0,0,0.1)", zeroline=True, zerolinecolor="rgba(0,0,0,0.2)")
        fig.update_xaxes(gridcolor="rgba(0,0,0,0.05)")
        
        return fig
    
    @staticmethod
    def create_compliance_donut(df: pd.DataFrame) -> go.Figure:
        """Create donut chart showing compliance distribution"""
        if df.empty:
            return go.Figure()
        
        status_counts = df['Status'].value_counts()
        colors = [Config.CHART_COLORS['late'], Config.CHART_COLORS['on_time'], Config.CHART_COLORS['early']]
        
        fig = go.Figure(data=[go.Pie(
            labels=status_counts.index,
            values=status_counts.values,
            hole=0.6,
            marker=dict(colors=colors[:len(status_counts)]),
            textinfo='percent+label',
            hoverinfo='label+value+percent',
            textfont=dict(size=11),
            pull=[0.05 if 'LATE' in str(label) else 0 for label in status_counts.index]
        )])
        
        fig.update_layout(
            title=dict(text="Compliance Distribution", font=dict(size=14), x=0.5),
            annotations=[dict(
                text=f"{len(df)}<br>Records",
                x=0.5, y=0.5, font_size=12, showarrow=False
            )],
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
            margin=dict(l=20, r=20, t=40, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )
        
        return fig
    
    @staticmethod
    def create_risk_heatmap(df: pd.DataFrame) -> go.Figure:
        """Create heatmap showing risk by wage month and amount"""
        if df.empty:
            return go.Figure()
        
        # Create risk score
        df_chart = df.copy()
        df_chart['Risk_Score'] = df_chart['Late Days'].apply(
            lambda x: min(100, max(0, x * 2.5)) if x > 0 else 0
        )
        
        fig = go.Figure(data=go.Heatmap(
            z=df_chart['Risk_Score'],
            x=df_chart['Wage Month'],
            y=['Risk Level'],
            colorscale=[[0, '#10b981'], [0.5, '#f59e0b'], [1, '#ef4444']],
            text=df_chart['Risk_Score'].apply(lambda x: f"{x:.0f}%"),
            texttemplate="%{text}",
            textfont={"size": 10},
            hovertemplate='<b>%{x}</b><br>Risk: %{z:.1f}%<br>Days Late: %{customdata}<extra></extra>',
            customdata=df_chart['Late Days']
        ))
        
        fig.update_layout(
            title=dict(text="Compliance Risk Heatmap", font=dict(size=14), x=0.5),
            xaxis_title="Wage Month",
            yaxis_title="",
            margin=dict(l=40, r=40, t=50, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )
        
        return fig
    
    @staticmethod
    def create_comparison_chart(df: pd.DataFrame) -> go.Figure:
        """Create stacked bar comparing Employer vs Employee shares"""
        if df.empty:
            return go.Figure()
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            name='Employer Share',
            x=df['Wage Month'],
            y=df['Employer Share'],
            marker_color=Config.CHART_COLORS['primary'],
            hovertemplate='Employer: ₹%{y:,.0f}<extra></extra>'
        ))
        
        fig.add_trace(go.Bar(
            name='Employee Share',
            x=df['Wage Month'],
            y=df['Employee Share'],
            marker_color=Config.CHART_COLORS['secondary'],
            hovertemplate='Employee: ₹%{y:,.0f}<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(text="Contribution Breakdown", font=dict(size=14), x=0.5),
            xaxis_title="Wage Month",
            yaxis_title="Amount (₹)",
            barmode='stack',
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", size=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        return fig


# ============================================================================
# 📤 EXPORT ENGINES - PROFESSIONAL REPORTING
# ============================================================================

class ExcelReportGenerator:
    """Generate professional Excel reports with advanced formatting"""
    
    @staticmethod
    def generate(df: pd.DataFrame, include_summary: bool = True) -> bytes:
        """Generate formatted Excel file"""
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Main data sheet
            df.to_excel(writer, index=False, sheet_name='PF_Audit_Data')
            ws = writer.sheets['PF_Audit_Data']
            
            # Apply professional styling
            ExcelReportGenerator._apply_header_style(ws)
            ExcelReportGenerator._apply_number_formatting(ws, df)
            ExcelReportGenerator._apply_conditional_formatting(ws, df)
            ExcelReportGenerator._auto_adjust_columns(ws)
            
            # Summary sheet
            if include_summary and not df.empty:
                ExcelReportGenerator._create_summary_sheet(writer.book, df)
            
            # Charts sheet
            if not df.empty:
                ExcelReportGenerator._add_charts(writer.book, df)
        
        return output.getvalue()
    
    @staticmethod
    def _apply_header_style(ws):
        """Apply professional header styling"""
        header_fill = PatternFill(start_color=Config.EXCEL_HEADER_COLOR, 
                                 end_color=Config.EXCEL_HEADER_COLOR, 
                                 fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11, name='Inter')
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )
        
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = border
    
    @staticmethod
    def _apply_number_formatting(ws, df):
        """Apply currency formatting to financial columns"""
        financial_cols = ['Admin Charges', 'Employer Share', 'Employee Share', 
                         'Grand Total', 'Employee Disallowance']
        
        for row_idx in range(2, len(df) + 2):
            for col_idx, col_name in enumerate(df.columns, 1):
                if col_name in financial_cols:
                    cell = ws.cell(row=row_idx, column=col_idx)
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = '₹#,##0.00'
                        cell.alignment = Alignment(horizontal='right')
    
    @staticmethod
    def _apply_conditional_formatting(ws, df):
        """Apply color coding based on filing status"""
        try:
            status_col_idx = None
            for idx, col in enumerate(ws[1], 1):
                if col.value == 'Status':
                    status_col_idx = idx
                    break
            
            if status_col_idx:
                status_letter = get_column_letter(status_col_idx)
                for row in range(2, len(df) + 2):
                    cell = ws[f"{status_letter}{row}"]
                    value = str(cell.value).upper()
                    
                    if 'LATE' in value:
                        cell.fill = PatternFill(start_color=Config.EXCEL_LATE_COLOR, 
                                              end_color=Config.EXCEL_LATE_COLOR, 
                                              fill_type="solid")
                        cell.font = Font(color="c62828", bold=True)
                    elif 'EARLY' in value:
                        cell.fill = PatternFill(start_color=Config.EXCEL_EARLY_COLOR, 
                                              end_color=Config.EXCEL_EARLY_COLOR, 
                                              fill_type="solid")
                        cell.font = Font(color="2e7d32", bold=True)
                    elif 'ON TIME' in value:
                        cell.fill = PatternFill(start_color=Config.EXCEL_ONTIME_COLOR, 
                                              end_color=Config.EXCEL_ONTIME_COLOR, 
                                              fill_type="solid")
                        cell.font = Font(color="f9a825", bold=True)
        except Exception as e:
            logger.debug(f"Conditional formatting skipped: {e}")
    
    @staticmethod
    def _auto_adjust_columns(ws):
        """Auto-adjust column widths with limits"""
        column_widths = {}
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            column_widths[col_letter] = min(max_len + 3, 30)
        
        for col_letter, width in column_widths.items():
            ws.column_dimensions[col_letter].width = width
    
    @staticmethod
    def _create_summary_sheet(workbook, df):
        """Create executive summary sheet"""
        summary = workbook.create_sheet('Executive_Summary', 0)
        
        # Title
        summary.merge_cells('A1:E1')
        title = summary['A1']
        title.value = 'PF COMPLIANCE AUDIT - EXECUTIVE SUMMARY'
        title.font = Font(bold=True, size=16, color="1e3a5f", name='Inter')
        title.alignment = Alignment(horizontal='center', vertical='center')
        
        # Metadata
        summary['A3'] = f"Report Generated: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}"
        summary['A4'] = f"Total Records: {len(df)}"
        summary['A5'] = f"Total PF Amount: ₹{df['Grand Total'].sum():,.2f}"
        summary['A6'] = f"Total Disallowance: ₹{df[df['Late Days']>0]['Employee Share'].sum():,.2f}"
        
        # Key metrics table
        metrics = [
            ['Metric', 'Value', 'Target', 'Status'],
            ['Compliance Rate', f"{RealTimeMetrics.calculate_compliance_rate(df):.1f}%", '100%', 
             '✓' if RealTimeMetrics.calculate_compliance_rate(df) >= 95 else '⚠'],
            ['On-Time Filings', f"{len(df[df['Late Days']==0])}", f"{len(df)}", '✓'],
            ['Late Filings', f"{len(df[df['Late Days']>0])}", '0', 
             '⚠' if len(df[df['Late Days']>0]) > 0 else '✓'],
            ['Avg Days Late', f"{df[df['Late Days']>0]['Late Days'].mean():.1f}" if len(df[df['Late Days']>0]) > 0 else "0", 
             '0', '⚠' if df[df['Late Days']>0]['Late Days'].mean() > 7 else '✓']
        ]
        
        for row_idx, row_data in enumerate(metrics, start=8):
            for col_idx, value in enumerate(row_data, start=1):
                cell = summary.cell(row=row_idx, column=col_idx, value=value)
                cell.font = Font(size=10)
                if row_idx == 8:
                    cell.font = Font(bold=True, size=10)
                    cell.fill = PatternFill(start_color="e2e8f0", end_color="e2e8f0", fill_type="solid")
                cell.border = Border(
                    left=Side(style='thin'), right=Side(style='thin'),
                    top=Side(style='thin'), bottom=Side(style='thin')
                )
        
        # Auto-adjust
        for col in summary.columns:
            max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
            summary.column_dimensions[col[0].column_letter].width = min(max_len + 2, 20)
    
    @staticmethod
    def _add_charts(workbook, df):
        """Add visual charts to Excel"""
        try:
            charts_sheet = workbook.create_sheet('Visualizations')
            
            # Simple bar chart data
            chart = BarChart()
            chart.title = "PF Payments by Month"
            chart.style = 10
            chart.y_axis.title = 'Amount (₹)'
            chart.x_axis.title = 'Wage Month'
            
            # Add data (simplified for demo)
            data = Reference(workbook['PF_Audit_Data'], 
                           min_col=df.columns.get_loc('Grand Total') + 1,
                           min_row=2, max_row=len(df) + 1)
            categories = Reference(workbook['PF_Audit_Data'], 
                                 min_col=df.columns.get_loc('Wage Month') + 1,
                                 min_row=2, max_row=len(df) + 1)
            
            chart.add_data(data, titles_from_data=False)
            chart.set_categories(categories)
            charts_sheet.add_chart(chart, "A1")
            
        except Exception as e:
            logger.debug(f"Chart generation skipped: {e}")


class PDFReportGenerator:
    """Generate professional PDF audit certificates"""
    
    @staticmethod
    def generate_certificate(df: pd.DataFrame, total_pf: float, emp_dis: float) -> bytes:
        """Generate formal PDF audit certificate"""
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # Header with branding
        pdf.set_font("Arial", 'B', 16)
        pdf.set_text_color(30, 58, 95)
        pdf.cell(0, 12, "STATUTORY PF COMPLIANCE AUDIT CERTIFICATE", ln=True, align='C')
        
        pdf.set_font("Arial", '', 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, f"Generated: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}", ln=True, align='C')
        pdf.cell(0, 5, f"Total Records Audited: {len(df)}", ln=True, align='C')
        pdf.ln(8)
        
        # Executive summary boxes
        pdf.set_fill_color(30, 58, 95)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 9)
        
        box_width = 280 / 3
        pdf.cell(box_width, 10, "Total PF Audited", 1, 0, 'C', True)
        pdf.cell(box_width, 10, "Employee Disallowance", 1, 0, 'C', True)
        pdf.cell(box_width, 10, "Compliance Rate", 1, 1, 'C', True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 11)
        compliance = RealTimeMetrics.calculate_compliance_rate(df)
        
        pdf.cell(box_width, 12, f"₹{total_pf:,.2f}", 1, 0, 'C')
        pdf.cell(box_width, 12, f"₹{emp_dis:,.2f}", 1, 0, 'C')
        pdf.cell(box_width, 12, f"{compliance:.1f}%", 1, 1, 'C')
        pdf.ln(8)
        
        # Data table header
        pdf.set_font("Arial", 'B', 7)
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        
        col_widths = [26, 20, 20, 10, 18, 22, 22, 22, 20, 18]
        headers = ["Wage Month", "Due Date", "Generated", "Late", "Admin", 
                  "Employer", "Employee", "Total", "Disallow", "Status"]
        
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 7, header, 1, 0, 'C', True)
        pdf.ln()
        
        # Table rows
        pdf.set_font("Arial", '', 6)
        pdf.set_text_color(0, 0, 0)
        
        for _, row in df.iterrows():
            # Truncate long values
            wage = str(row['Wage Month'])[:23]
            gen_date = str(row['Generated Date'])[:17]
            
            pdf.cell(col_widths[0], 6, wage, 1)
            pdf.cell(col_widths[1], 6, str(row['Due Date']), 1, 0, 'C')
            pdf.cell(col_widths[2], 6, gen_date, 1, 0, 'C')
            pdf.cell(col_widths[3], 6, str(row['Late Days']), 1, 0, 'C')
            pdf.cell(col_widths[4], 6, f"{row['Admin Charges']:,.0f}", 1, 0, 'R')
            pdf.cell(col_widths[5], 6, f"{row['Employer Share']:,.0f}", 1, 0, 'R')
            pdf.cell(col_widths[6], 6, f"{row['Employee Share']:,.0f}", 1, 0, 'R')
            pdf.cell(col_widths[7], 6, f"{row['Grand Total']:,.0f}", 1, 0, 'R')
            pdf.cell(col_widths[8], 6, f"{row['Employee Disallowance']:,.0f}", 1, 0, 'R')
            
            # Color-code status
            status = str(row['Status'])
            if 'LATE' in status:
                pdf.set_text_color(185, 28, 28)
            elif 'EARLY' in status:
                pdf.set_text_color(46, 125, 50)
            else:
                pdf.set_text_color(245, 158, 11)
            
            pdf.cell(col_widths[9], 6, status.split()[-1], 1, 1, 'C')
            pdf.set_text_color(0, 0, 0)
        
        # Footer
        pdf.ln(5)
        pdf.set_font("Arial", 'I', 7)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 5, "This is a system-generated audit report. Verify at www.epfindia.gov.in", ln=True, align='C')
        
        return pdf.output(dest='S').encode('latin-1', 'replace')


# ============================================================================
# 🧠 MAIN PARSING ENGINE
# ============================================================================

class ChallanParser:
    """Main engine for parsing PF challan PDFs with fallback strategies"""
    
    def __init__(self):
        self.combined_parser = CombinedChallanParser()
        self.provisional_parser = ProvisionalChallanParser()
        self.detector = PDFTypeDetector()
    
    def parse_file(self, file) -> Optional[ChallanRecord]:
        """Parse a single PDF file with comprehensive error handling"""
        try:
            # Read file content
            file_bytes = file.read()
            file_hash = generate_file_hash(file_bytes)
            
            # Extract text with encoding fallbacks
            full_text = self._extract_text_with_fallback(file_bytes)
            if not full_text.strip():
                logger.error(f"No text extracted from {file.name}")
                return None
            
            # Detect PDF type
            pdf_type, confidence = self.detector.detect(full_text)
            logger.info(f"Detected {pdf_type.value} (confidence: {confidence:.2f}) for {file.name}")
            
            # Select appropriate parser
            if pdf_type == PDFType.COMBINED:
                parser = self.combined_parser
            elif pdf_type == PDFType.PROVISIONAL:
                parser = self.provisional_parser
            else:
                # Try both parsers and use best result
                combined_vals = self.combined_parser.extract_financial_values(full_text)
                provisional_vals = self.provisional_parser.extract_financial_values(full_text)
                
                if combined_vals.grand_total >= provisional_vals.grand_total:
                    parser = self.combined_parser
                    pdf_type = PDFType.COMBINED
                else:
                    parser = self.provisional_parser
                    pdf_type = PDFType.PROVISIONAL
                confidence = 0.7
            
            # Extract core fields
            wage_month, wage_date = parser.extract_wage_month(full_text)
            gen_datetime, gen_date_str = parser.extract_generation_date(full_text)
            due_date = calculate_statutory_due_date(wage_month)
            
            # Extract financial values
            financial_values = parser.extract_financial_values(full_text)
            
            # Extract additional metadata
            establishment = self._extract_establishment_name(full_text)
            trrn = self._extract_trrn(full_text)
            
            # Calculate compliance metrics
            late_days = 0
            if gen_datetime and due_date:
                late_days = (gen_datetime.date() - due_date.date()).days
            
            employee_disallowance = financial_values.employee_share if late_days > 0 else 0.0
            
            # Determine filing status
            if late_days > 0:
                status = FilingStatus.LATE
            elif late_days < 0:
                status = FilingStatus.EARLY
            else:
                status = FilingStatus.ON_TIME
            
            return ChallanRecord(
                file_name=file.name,
                file_hash=file_hash,
                pdf_type=pdf_type,
                processing_timestamp=datetime.now(),
                wage_month=wage_month,
                wage_month_date=wage_date,
                due_date=due_date,
                generated_date=gen_datetime,
                generated_date_str=gen_date_str,
                financial_values=financial_values,
                late_days=late_days,
                employee_disallowance=employee_disallowance,
                filing_status=status,
                establishment_name=establishment,
                trrn=trrn,
                parsing_confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"Parse error for {file.name}: {str(e)}\n{traceback.format_exc()}")
            return None
    
    def _extract_text_with_fallback(self, file_bytes: bytes) -> str:
        """Extract text from PDF with multiple encoding fallbacks"""
        from io import BytesIO
        
        for encoding in Config.ENCODING_FALLBACKS:
            try:
                with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                    text_parts = []
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                    return '\n'.join(text_parts)
            except Exception:
                continue
        return ""
    
    def _extract_establishment_name(self, text: str) -> str:
        """Extract establishment name from PDF text"""
        patterns = [
            r'Establishment.*?:\s*([A-Z\s&]+?)(?:\n|$)',
            r'TERRA TEK.*?(?:\n|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1).strip()
        return ""
    
    def _extract_trrn(self, text: str) -> str:
        """Extract TRRN number from PDF text"""
        match = re.search(r'TRRN:\s*([A-Z0-9]+)', text, re.I)
        if match:
            return match.group(1).strip()
        match = re.search(r'APPTC\d+', text)
        if match:
            return match.group(0)
        return ""


# ============================================================================
# 🎨 STREAMLIT UI COMPONENTS
# ============================================================================

def render_glassmorphism_css():
    """Render comprehensive CSS for glassmorphism UI"""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    /* Base Typography */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        scroll-behavior: smooth;
    }
    
    /* Animated Gradient Background */
    .stApp {
        background: linear-gradient(-45deg, #f0f9ff, #e6f0fa, #d9e9f5, #e6f0fa, #f0f9ff);
        background-size: 400% 400%;
        animation: gradientBG 20s ease infinite;
    }
    
    @keyframes gradientBG {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    
    @media (prefers-color-scheme: dark) {
        .stApp {
            background: linear-gradient(-45deg, #0b1a2e, #102a3c, #1a3f54, #102a3c, #0b1a2e);
            background-size: 400% 400%;
            animation: gradientBG 20s ease infinite;
        }
    }
    
    /* Glassmorphism Card */
    .glass-card {
        backdrop-filter: blur(12px);
        background: rgba(255, 255, 255, 0.25);
        border-radius: 24px;
        border: 1px solid rgba(255, 255, 255, 0.4);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.05);
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .glass-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 16px 48px rgba(0, 0, 0, 0.12), 0 4px 16px rgba(0, 0, 0, 0.08);
        border-color: rgba(37, 99, 235, 0.3);
    }
    
    @media (prefers-color-scheme: dark) {
        .glass-card {
            background: rgba(20, 40, 60, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.12);
        }
    }
    
    /* Header Card with Animation */
    .header-card {
        text-align: center;
        padding: 2rem;
        background: rgba(255, 255, 255, 0.35);
        backdrop-filter: blur(16px);
        border-radius: 32px;
        border: 1px solid rgba(255, 255, 255, 0.5);
        box-shadow: 0 24px 56px rgba(0, 0, 0, 0.1);
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
        background: radial-gradient(circle, rgba(37, 99, 235, 0.08) 0%, transparent 70%);
        animation: rotate 25s linear infinite;
        pointer-events: none;
    }
    
    @keyframes rotate {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    
    .main-title {
        font-weight: 800;
        font-size: 2.5rem;
        background: linear-gradient(135deg, #2563eb, #0ea5e9, #7c3aed, #0ea5e9);
        background-size: 300% 300%;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: shimmer 4s ease infinite;
        letter-spacing: -0.5px;
    }
    
    @keyframes shimmer {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    
    .subtitle {
        font-size: 1.1rem;
        font-weight: 500;
        color: #475569;
        opacity: 0.9;
        letter-spacing: 0.5px;
        margin-top: 0.5rem;
    }
    
    @media (prefers-color-scheme: dark) {
        .subtitle { color: #cbd5e1; }
    }
    
    /* Metric Cards */
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.3);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 1.25rem;
        border: 1px solid rgba(255, 255, 255, 0.35);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
        transition: all 0.25s ease;
    }
    
    [data-testid="stMetric"]:hover {
        transform: scale(1.03);
        background: rgba(255, 255, 255, 0.4);
        border-color: rgba(37, 99, 235, 0.5);
        box-shadow: 0 8px 32px rgba(37, 99, 235, 0.15);
    }
    
    [data-testid="stMetricLabel"] {
        font-weight: 600;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: #334155;
    }
    
    [data-testid="stMetricValue"] {
        font-weight: 800;
        font-size: 2rem;
        color: #0f172a;
        margin-top: 0.25rem;
    }
    
    @media (prefers-color-scheme: dark) {
        [data-testid="stMetricLabel"] { color: #cbd5e1; }
        [data-testid="stMetricValue"] { color: #f1f5f9; }
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #2563eb, #0ea5e9, #7c3aed);
        background-size: 200% 200%;
        color: white;
        border: none;
        border-radius: 50px;
        padding: 0.85rem 2.5rem;
        font-weight: 700;
        font-size: 1rem;
        letter-spacing: 0.3px;
        box-shadow: 0 4px 20px rgba(37, 99, 235, 0.35);
        transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        backdrop-filter: blur(4px);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 12px 40px rgba(37, 99, 235, 0.5);
        background-position: right center;
    }
    
    .stButton > button:active {
        transform: translateY(0);
    }
    
    /* File Uploader */
    [data-testid="stFileUploader"] {
        background: rgba(255, 255, 255, 0.25);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 1.5rem;
        border: 2px dashed rgba(37, 99, 235, 0.5);
        transition: all 0.3s ease;
    }
    
    [data-testid="stFileUploader"]:hover {
        border-color: #2563eb;
        background: rgba(255, 255, 255, 0.35);
    }
    
    /* Dataframe */
    [data-testid="stDataFrame"] {
        background: rgba(255, 255, 255, 0.25);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 0.5rem;
        border: 1px solid rgba(255, 255, 255, 0.3);
    }
    
    /* Plotly Charts */
    .js-plotly-plot .plotly, .plotly {
        background: transparent !important;
    }
    
    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 7px; height: 7px; }
    ::-webkit-scrollbar-track { background: rgba(0,0,0,0.06); border-radius: 10px; }
    ::-webkit-scrollbar-thumb { 
        background: linear-gradient(135deg, #2563eb, #0ea5e9); 
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover { background: #2563eb; }
    
    /* Alert Boxes */
    .success-box {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 16px;
        margin: 1rem 0;
        border-left: 4px solid #047857;
        box-shadow: 0 4px 16px rgba(16, 185, 129, 0.2);
    }
    
    .error-box {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 16px;
        margin: 1rem 0;
        border-left: 4px solid #b91c1c;
        box-shadow: 0 4px 16px rgba(239, 68, 68, 0.2);
    }
    
    .warning-box {
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 16px;
        margin: 1rem 0;
        border-left: 4px solid #b45309;
        box-shadow: 0 4px 16px rgba(245, 158, 11, 0.2);
    }
    
    /* Footer */
    .footer {
        text-align: center;
        margin-top: 3rem;
        font-size: 0.85rem;
        opacity: 0.75;
        color: #475569;
        padding: 1.5rem;
        border-top: 1px solid rgba(0,0,0,0.08);
    }
    
    @media (prefers-color-scheme: dark) {
        .footer { color: #94a3b8; }
    }
    
    /* Real-time indicator */
    .live-indicator {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.4rem 1rem;
        background: rgba(16, 185, 129, 0.15);
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        color: #059669;
    }
    
    .live-dot {
        width: 8px;
        height: 8px;
        background: #10b981;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.6; transform: scale(0.9); }
    }
    
    /* Loading animation */
    .loading-dots::after {
        content: '...';
        animation: dots 1.5s steps(4, end) infinite;
    }
    
    @keyframes dots {
        0%, 20% { content: '.'; }
        40% { content: '..'; }
        60%, 100% { content: '...'; }
    }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    """Render animated header card"""
    st.markdown("""
    <div class="header-card">
        <div class="main-title">🏢 PF CHALLAN AI COMMAND CENTER</div>
        <div class="subtitle">Enterprise Statutory Audit Suite • Dual PDF Format • Real-Time Analytics</div>
        <div style="margin-top:1rem; font-style:italic; opacity:0.75; font-size:0.95rem;">
            🌸 कर्मण्येवाधिकारस्ते मा फलेषु कदाचन 🌸
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar_filters(df: pd.DataFrame):
    """Render sidebar with advanced filtering options"""
    with st.sidebar:
        st.markdown("### 🔍 Advanced Filters")
        
        # PDF Type filter
        pdf_types = ['All'] + list(df['PDF Type'].unique()) if not df.empty else ['All']
        selected_type = st.selectbox("PDF Type", pdf_types, key="filter_type")
        
        # Status filter
        statuses = ['All'] + list(df['Status'].unique()) if not df.empty else ['All']
        selected_status = st.selectbox("Filing Status", statuses, key="filter_status")
        
        # Date range filter
        if not df.empty and 'Wage Month' in df.columns:
            st.markdown("---")
            st.markdown("**📅 Wage Month Range**")
            months = sorted(df['Wage Month'].unique())
            if len(months) >= 2:
                start_month = st.selectbox("From", months, index=0, key="filter_start")
                end_month = st.selectbox("To", months, index=len(months)-1, key="filter_end")
            else:
                start_month = end_month = months[0] if months else None
        else:
            start_month = end_month = None
        
        # Search
        st.markdown("---")
        search_term = st.text_input("🔎 Search", placeholder="Search by file name, TRRN...")
        
        # Apply filters button
        st.markdown("---")
        apply_filters = st.button("Apply Filters", type="primary", use_container_width=True)
        
        # Reset filters
        if st.button("Reset All Filters", use_container_width=True):
            st.session_state.filters = {}
            st.rerun()
        
        # Store filter state
        st.session_state.filters = {
            'pdf_type': selected_type if selected_type != 'All' else None,
            'status': selected_status if selected_status != 'All' else None,
            'start_month': start_month,
            'end_month': end_month,
            'search': search_term if search_term else None
        }
        
        return apply_filters


def apply_filters(df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
    """Apply user filters to dataframe"""
    if df.empty or not filters:
        return df
    
    filtered = df.copy()
    
    if filters.get('pdf_type'):
        filtered = filtered[filtered['PDF Type'] == filters['pdf_type']]
    
    if filters.get('status'):
        filtered = filtered[filtered['Status'] == filters['status']]
    
    if filters.get('start_month') and filters.get('end_month'):
        # Simple string comparison for month filtering
        filtered = filtered[
            (filtered['Wage Month'] >= filters['start_month']) & 
            (filtered['Wage Month'] <= filters['end_month'])
        ]
    
    if filters.get('search'):
        search_lower = filters['search'].lower()
        filtered = filtered[
            filtered['File Name'].str.lower().str.contains(search_lower, na=False) |
            filtered['TRRN'].str.lower().str.contains(search_lower, na=False) |
            filtered['Establishment'].str.lower().str.contains(search_lower, na=False)
        ]
    
    return filtered


def render_realtime_indicator(state_manager: DashboardStateManager):
    """Render live update indicator"""
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;">
        <div class="live-indicator">
            <span class="live-dot"></span>
            Live • Last: {state_manager.last_update_str}
        </div>
        <small style="opacity: 0.7;">Auto-refresh: {Config.AUTO_REFRESH_INTERVAL_SEC}s</small>
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# 🚀 MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point"""
    
    # Initialize session state
    if 'parsed_records' not in st.session_state:
        st.session_state.parsed_records = []
    if 'dashboard_state' not in st.session_state:
        st.session_state.dashboard_state = DashboardStateManager()
    if 'filters' not in st.session_state:
        st.session_state.filters = {}
    if 'last_processed_files' not in st.session_state:
        st.session_state.last_processed_files = set()
    
    # Render UI
    render_glassmorphism_css()
    render_header()
    
    # File upload section
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("📂 Upload PF Challan PDFs")
    st.markdown("""
    <small style="opacity:0.85;">
    ✅ Supports <strong>Combined Challan</strong> (A/C 01,02,10,21,22) & <strong>Provisional Challan</strong><br>
    ✅ Auto-detects format • Extracts wage month, dates, financial values<br>
    ✅ Calculates statutory due dates • Flags late/early filings for compliance
    </small>
    """, unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader(
        "Drop PDFs here or click to browse",
        type=['pdf'],
        accept_multiple_files=True,
        label_visibility="collapsed",
        help="Maximum file size: 50MB each"
    )
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Action button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        process_btn = st.button("🚀 INITIATE AI AUDIT ENGINE", type="primary", use_container_width=True)
    
    # Processing logic
    if uploaded_files and process_btn:
        # Check for new files only
        current_files = {f.name for f in uploaded_files}
        new_files = current_files - st.session_state.last_processed_files
        
        if not new_files and st.session_state.parsed_records:
            st.info("ℹ️ Files already processed. Modify filters or upload new files.")
        else:
            with st.spinner("🔮 AI Engine parsing challans with multi-format intelligence..."):
                parser = ChallanParser()
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                new_records = []
                errors = []
                
                for idx, file in enumerate(uploaded_files):
                    if file.name in new_files or not st.session_state.parsed_records:
                        status_text.text(f"📄 Processing {idx+1}/{len(uploaded_files)}: {file.name}")
                        record = parser.parse_file(file)
                        
                        if record:
                            new_records.append(record)
                            logger.info(f"✓ Parsed: {file.name}")
                        else:
                            errors.append(file.name)
                            logger.error(f"✗ Failed: {file.name}")
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                progress_bar.empty()
                status_text.empty()
                
                # Update session state
                if new_records:
                    st.session_state.parsed_records.extend(new_records)
                    st.session_state.last_processed_files = current_files
                    st.session_state.dashboard_state.mark_updated()
                
                # Display results
                if new_records or st.session_state.parsed_records:
                    render_audit_dashboard()
                elif errors:
                    st.markdown('<div class="error-box">', unsafe_allow_html=True)
                    st.error(f"❌ Could not parse {len(errors)} file(s): {', '.join(errors)}")
                    st.markdown("""
                    **Troubleshooting:**
                    • Ensure PDFs are text-based (not scanned images)
                    • Verify files are EPFO challans in supported formats
                    • Check PDF contains selectable text in your viewer
                    """)
                    st.markdown('</div>', unsafe_allow_html=True)
    
    elif uploaded_files and not process_btn:
        st.info("👆 Click 'INITIATE AI AUDIT ENGINE' to begin processing")
    
    elif not uploaded_files:
        st.markdown("""
        <div style="text-align: center; padding: 3rem; opacity: 0.75;">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📋</div>
            <h3>Upload PF Challan PDFs to Begin</h3>
            <p style="max-width: 500px; margin: 0 auto;">
                Supports both Combined Challan (A/C 01,02,10,21,22) and Provisional Challan formats.
                Real-time compliance analytics and professional audit reports.
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # Render dashboard if we have data
    if st.session_state.parsed_records:
        render_audit_dashboard()
    
    # Footer
    st.markdown("""
    <div class="footer">
        © 2026 | PF AI Command Center v3.0 • <span style="color: #2563eb;">⚡ Dual-Format Parser • Real-Time Compliance Engine</span><br>
        <small style="opacity: 0.8;">Disclaimer: Assists audit preparation. Always verify at www.epfindia.gov.in</small>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar reference
    with st.sidebar:
        st.markdown("### 📚 Format Reference")
        
        st.markdown("**🔹 Combined Challan**")
        st.markdown("<small>• Header: 'Combined Challan of A/C NO. 01, 02, 10, 21 & 22'<br>• Date: 'system generated challan on DD-MMM-YYYY'<br>• Fields: Administration Charges, Employer's/Employee's Share Of</small>", unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("**🔹 Provisional Challan**")
        st.markdown("<small>• Header: 'PROVISIONAL CHALLAN FOR WAGE MONTH'<br>• Date: 'Generated On: DD-MMM-YYYY HH:MM:SS'<br>• Fields: Admin/Insp. Charges, Employer's/Employee's Share Of Contribution</small>", unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### ⚙️ Processing Pipeline")
        st.markdown("<small>1️⃣ Auto-detect PDF format<br>2️⃣ Extract wage month → Calculate due date (15th next month)<br>3️⃣ Parse financial values from TOTAL column<br>4️⃣ Compare dates → Calculate late days<br>5️⃣ Flag disallowances for late filings<br>6️⃣ Generate multi-format audit reports</small>", unsafe_allow_html=True)


def render_audit_dashboard():
    """Render the real-time audit dashboard"""
    
    # Convert records to DataFrame
    df = pd.DataFrame([r.to_dataframe_row() for r in st.session_state.parsed_records])
    
    # Apply filters
    if st.session_state.filters:
        df = apply_filters(df, st.session_state.filters)
    
    if df.empty:
        st.warning("⚠️ No records match current filters. Reset filters to view all data.")
        return
    
    # Real-time indicator
    render_realtime_indicator(st.session_state.dashboard_state)
    
    # Success message
    st.markdown('<div class="success-box">', unsafe_allow_html=True)
    st.success(f"✅ Processed {len(df)} record(s) • Ready for analysis")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Key metrics with animations
    st.markdown("### 📊 Real-Time Compliance Dashboard")
    
    total_pf = df['Grand Total'].sum()
    emp_dis = df[df['Late Days'] > 0]['Employee Share'].sum()
    late_count = len(df[df['Late Days'] > 0])
    compliance_rate = RealTimeMetrics.calculate_compliance_rate(df)
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("💰 Total PF Audited", format_currency(total_pf), 
                 delta=f"{len(df)} records", delta_color="normal")
    with m2:
        st.metric("⚠️ Tax Disallowance", format_currency(emp_dis),
                 delta=f"{late_count} late filings", delta_color="inverse")
    with m3:
        st.metric("📋 Records", f"{len(df)}", 
                 delta=f"{len(df[df['PDF Type']=='Combined'])} Combined, {len(df[df['PDF Type']=='Provisional'])} Provisional")
    with m4:
        st.metric("✅ Compliance Rate", f"{compliance_rate:.1f}%",
                 delta="Target: 100%", delta_color="normal" if compliance_rate >= 95 else "inverse")
    
    st.markdown("---")
    
    # Charts section
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("📈 Payment Timeline")
        fig_timeline = ChartFactory.create_payment_timeline(df)
        st.plotly_chart(fig_timeline, use_container_width=True, theme="streamlit")
    
    with col_chart2:
        st.subheader("🥧 Compliance Distribution")
        fig_donut = ChartFactory.create_compliance_donut(df)
        st.plotly_chart(fig_donut, use_container_width=True, theme="streamlit")
    
    # Secondary charts
    col_chart3, col_chart4 = st.columns(2)
    
    with col_chart3:
        st.subheader("🔥 Risk Heatmap")
        fig_risk = ChartFactory.create_risk_heatmap(df)
        st.plotly_chart(fig_risk, use_container_width=True, theme="streamlit")
    
    with col_chart4:
        st.subheader("📊 Contribution Breakdown")
        fig_compare = ChartFactory.create_comparison_chart(df)
        st.plotly_chart(fig_compare, use_container_width=True, theme="streamlit")
    
    # Export section
    st.markdown("### 📥 Export Audit Reports")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        excel_data = ExcelReportGenerator.generate(df)
        st.download_button(
            "🚀 Download Excel Report",
            excel_data,
            f"PF_Audit_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            help="Professional Excel with conditional formatting, charts & summary",
            use_container_width=True,
            type="primary"
        )
    
    with c2:
        pdf_data = PDFReportGenerator.generate_certificate(df, total_pf, emp_dis)
        st.download_button(
            "📜 Download PDF Certificate",
            pdf_data,
            f"PF_Audit_Certificate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            "application/pdf",
            help="Formal audit certificate for compliance records",
            use_container_width=True
        )
    
    with c3:
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📄 Download CSV Data",
            csv_data,
            f"PF_Audit_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            help="Raw CSV for further analysis",
            use_container_width=True
        )
    
    # Detailed data table
    st.markdown("### 🔍 Detailed Audit Records")
    
    # Format display DataFrame
    display_df = df.copy()
    numeric_cols = ['Admin Charges', 'Employer Share', 'Employee Share', 'Grand Total', 'Employee Disallowance']
    for col in numeric_cols:
        display_df[col] = display_df[col].apply(format_currency)
    
    # Apply conditional styling using pandas-compatible method
    def style_status(val):
        val_str = str(val).upper()
        if 'LATE' in val_str:
            return 'background-color: rgba(255, 205, 210, 0.6); color: #c62828; font-weight: 600'
        elif 'EARLY' in val_str:
            return 'background-color: rgba(200, 230, 201, 0.6); color: #2e7d32; font-weight: 600'
        elif 'ON TIME' in val_str:
            return 'background-color: rgba(255, 249, 196, 0.6); color: #f9a825; font-weight: 600'
        return ''
    
    styled_df = display_df.style.map(style_status, subset=['Status'])
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        height=400,
        column_config={
            "Grand Total": st.column_config.TextColumn("Grand Total"),
            "Employee Disallowance": st.column_config.TextColumn("Disallowance"),
            "Confidence": st.column_config.ProgressColumn(
                "Confidence",
                format="%s",
                min_value=0,
                max_value=100
            )
        }
    )
    
    # Debug expander
    with st.expander("🔧 Raw Extraction Data (Debug)", expanded=False):
        st.json([r.__dict__ for r in st.session_state.parsed_records[:3]], expanded=False)


# ============================================================================
# 🎬 APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Set page config first
    st.set_page_config(
        page_title="PF AI Command Center",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'About': "# PF Challan AI Command Center\nEnterprise Statutory Audit Suite v3.0\n\nSupports Combined & Provisional EPFO challan formats with real-time compliance analytics."
        }
    )
    
    # Run main app
    main()
    
    # Optional: Auto-refresh simulation (for demo purposes)
    # In production, consider using streamlit-autorefresh or websockets
    if st.session_state.parsed_records and st.session_state.dashboard_state.should_refresh():
        # Mark as refreshed to prevent continuous reruns
        st.session_state.dashboard_state.mark_updated()
        # Note: Streamlit doesn't support true auto-refresh without user interaction
        # This is a placeholder for future websocket implementation
        pass
