import os
from openpyxl import Workbook
from typing import Tuple, Dict
from database_manager import db_manager
from flask import abort, session, request
from datetime import datetime
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

BASE_FOLDER = r"D:\C102641-Data\Valve_Final_Inspection"
REPORTS_FOLDER = os.path.join(BASE_FOLDER, "reports")
os.makedirs(REPORTS_FOLDER, exist_ok=True)

def validate_report_access():
    if "user_id" not in session:
        abort(401)

    if session.get("user_ip") != request.remote_addr:
        abort(403)
        
def _rows_to_tabledata(df):
    header = list(df.columns)
    data = [header] + df.values.tolist()
    return data

def generate_excel_report(df, out_path):
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Inspections")
        workbook  = writer.book
        worksheet = writer.sheets["Inspections"]
        for i, col in enumerate(df.columns):
            col_width = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, col_width)
    return out_path

def generate_pdf_report(summary: dict, df: pd.DataFrame, out_path):
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Daily Inspection Report", styles['Title']))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 8))

    summary_items = [[k, str(v)] for k, v in summary.items()]
    story.append(Paragraph("Summary", styles['Heading2']))
    story.append(Spacer(1,6))
    story.append(Table(summary_items, colWidths=[200, 300], style=[
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
    ]))
    story.append(Spacer(1,10))

    story.append(Paragraph("Recent Inspections (sample)", styles['Heading2']))
    story.append(Spacer(1,6))
    sample_df = df.head(50) if len(df) > 50 else df

    if sample_df.empty:
        story.append(Paragraph("No inspection rows found for the requested date range.", styles['Normal']))
    else:
        table_data = _rows_to_tabledata(sample_df)
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
        ]))
        story.append(table)

    doc = SimpleDocTemplate(out_path, pagesize=A4)
    doc.build(story)
    return out_path

def build_summary(df):
    total = len(df)
    accepted = len(df[df['Result'] == 'Accepted'])
    rejected = len(df[df['Result'] == 'Rejected'])
    defects = df[df['Result'] == 'Rejected']['Defect_type'].value_counts().to_dict() if 'Defect_type' in df.columns else {}
    numeric_cols = ['ssim_score', 'width_mm', 'height_mm', 'area_mm2']
    stats = {}
    for col in numeric_cols:
        if col in df.columns and not df.empty:
            stats[col] = {'min': float(df[col].min()) if not df[col].isnull().all() else None,
                          'max': float(df[col].max()) if not df[col].isnull().all() else None,
                          'avg': float(df[col].mean()) if not df[col].isnull().all() else None}
    summary = {"total": total, "accepted": accepted, "rejected": rejected, "defects_by_type": defects, "numeric_stats": stats}
    return summary

def generate_daily_report(df: pd.DataFrame, date_from, date_to, out_format="xlsx"):
    if df.empty:
        raise Exception("No inspection data found for selected date range")
    
    os.makedirs("reports", exist_ok=True)
    file_name = f"Inspection_Report_{date_from.date()}.{out_format}"
    out_path = os.path.join("reports", file_name)

    df.to_excel(out_path, index=False)
    return out_path, "Report generated"
