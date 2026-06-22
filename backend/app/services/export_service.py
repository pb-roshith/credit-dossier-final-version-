"""
Export Service — generates PPT, PDF, and DOCX documents from deal narratives.
Also provides a combined PDF report from all sections.
"""

from __future__ import annotations

import io
import logging
import re
import base64
from datetime import datetime

import markdown
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sqlalchemy.orm import Session, joinedload
from xhtml2pdf import pisa
from html2docx import html2docx

from app.models.deal import Deal, Section

logger = logging.getLogger(__name__)


def _format_amount(amount: float, currency: str) -> str:
    if currency == "INR":
        cr = amount / 10_000_000
        return f"INR {cr:,.2f} Cr"
    return f"{currency} {amount:,.0f}"


def _parse_table_data(table_str: str) -> pd.DataFrame | None:
    lines = table_str.strip().split('\n')
    if len(lines) < 3: 
        return None
    
    headers = [col.strip() for col in lines[0].split('|')[1:-1]]
    rows = []
    for line in lines[2:]:
        cols = [col.strip() for col in line.split('|')[1:-1]]
        if len(cols) == len(headers):
            rows.append(cols)
    if not rows: 
        return None
    
    df = pd.DataFrame(rows, columns=headers)
    
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col].str.replace(r'[^0-9.-]', '', regex=True), errors='coerce')
    
    if df.shape[1] > 1 and df.iloc[:, 1:].notna().any().any():
        return df
    return None


def _clean_unprintable_chars(text: str) -> str:
    """Removes emojis, dingbats, and unsupported unicode characters that break PDF rendering."""
    # Keep ASCII, extended Latin, common punctuation, Euro, Pound, and dashes
    # This regex removes characters outside of these safe ranges.
    clean_text = re.sub(r'[^\x00-\x7F\xA0-\xFF\u0100-\u017F\u2013-\u2014\u2018-\u201D\u20AC\u00A3]', '', text)
    return clean_text

def _markdown_to_html_with_graphs(text: str, primary_color: str, secondary_color: str) -> str:
    """Detects numeric markdown tables, injects matplotlib charts, and converts to HTML."""
    table_pattern = re.compile(r'(^\|[^\n]+\|\n\|[-:| ]+\|\n(?:\|[^\n]+\|\n)+)', re.MULTILINE)
    
    def replacer(match):
        table_str = match.group(1)
        df = _parse_table_data(table_str)
        if df is not None:
            try:
                fig, ax = plt.subplots(figsize=(8, 4))
                # Use the dynamic colors
                colors = [primary_color, secondary_color, "#64748b", "#94a3b8", "#cbd5e1"]
                bars = df.plot(x=df.columns[0], kind='bar', ax=ax, rot=45, color=colors[:len(df.columns)-1])
                
                # Add value labels
                for container in ax.containers:
                    ax.bar_label(container, fmt='%.1f', padding=3, color='#334155', fontsize=8, fontweight='bold')
                
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_visible(False)
                ax.set_xlabel("")
                ax.set_yticks([]) # Hide y-ticks to rely on bar labels
                plt.tight_layout()
                
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=300, transparent=True)
                plt.close(fig)
                
                img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                img_tag = f"\n\n<div style='text-align:center; margin: 20px 0;'><img src='data:image/png;base64,{img_b64}' width='500' /></div>\n\n"
                return table_str + img_tag
            except Exception as e:
                logger.error(f"Failed to plot table: {e}")
                return table_str
        return table_str

    transformed = table_pattern.sub(replacer, text)
    html = markdown.markdown(transformed, extensions=['tables'])
    return html


class ExportService:
    """Generates export documents from deal data."""

    @staticmethod
    def get_deal_with_sections(db: Session, deal_id: str) -> Deal | None:
        return (
            db.query(Deal)
            .options(joinedload(Deal.sections), joinedload(Deal.versions))
            .filter(Deal.id == deal_id)
            .first()
        )

    @staticmethod
    def _generate_html_document(deal: Deal, for_pdf: bool = True) -> str:
        # Filter generated sections
        valid_sections = [
            s for s in sorted(deal.sections, key=lambda x: x.order_index) 
            if s.state == "ready" and s.generated_content and s.generated_content.strip()
        ]

        # Use the deal's dynamic theme colors
        p_color = getattr(deal, "primary_color", "#002060")
        s_color = getattr(deal, "secondary_color", "#800020")

        html_parts = []
        
        # Cover
        html_parts.append(f"<h1 style='text-align: center; font-size: 32pt; font-weight: bold; margin-top: 200px; color: {p_color};'>CREDIT PITCH BOOK</h1>")
        html_parts.append(f"<h2 style='text-align: center; font-size: 22pt; margin-top: 10px; color: {s_color};'>{deal.customer}</h2>")
        html_parts.append(f"<p style='text-align: center; color: #64748b; font-size: 14pt; margin-top: 30px;'>{deal.industry} | {deal.segment} | {deal.geography}</p>")
        html_parts.append(f"<p style='text-align: center; color: #64748b; font-size: 14pt;'>Facility: {deal.facility} — {_format_amount(deal.amount, deal.currency)}</p>")
        html_parts.append(f"<p style='text-align: center; color: #94a3b8; font-size: 11pt; margin-top: 80px;'>Generated: {datetime.now().strftime('%B %d, %Y')}</p>")
        
        page_break = "<pdf:nextpage />" if for_pdf else "<br/><br/><br/>"
        html_parts.append(page_break)
        
        # TOC
        html_parts.append(f"<h2 style='color: {p_color}; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;'>TABLE OF CONTENTS</h2><ul style='list-style-type: none; padding-left: 0;'>")
        for i, section in enumerate(valid_sections, 1):
            html_parts.append(f"<li style='margin-bottom: 12px; font-size: 12pt; color: #334155;'><strong style='color: {p_color};'>{i}.</strong> {section.title}</li>")
        html_parts.append("</ul>")
        html_parts.append(page_break)

        # Summary Table
        html_parts.append(f"<h2 style='color: {p_color}; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;'>DEAL SUMMARY</h2>")
        html_parts.append("<table border='1' cellpadding='10' style='width: 100%; border-collapse: collapse; margin-top: 20px;'>")
        html_parts.append(f"<tr><th style='background-color: {p_color}; color: white; width: 35%; font-weight: bold;'>Parameter</th><th style='background-color: {p_color}; color: white; font-weight: bold;'>Details</th></tr>")
        
        summary_items = [
            ("Customer", deal.customer),
            ("Customer Type", deal.customer_type),
            ("Industry / Sector", f"{deal.industry} / {deal.sector}"),
            ("Segment", deal.segment),
            ("Geography", deal.geography),
            ("KYC Status", deal.kyc.title()),
            ("Facility Type", deal.facility),
            ("Amount", _format_amount(deal.amount, deal.currency)),
            ("Tenure", f"{deal.tenure} months"),
            ("Pricing", deal.pricing),
            ("Repayment", deal.repayment),
            ("Collateral", "Secured" if deal.collateral else "Clean / Unsecured"),
            ("Target Date", deal.due),
        ]
        
        for k, v in summary_items:
            html_parts.append(f"<tr><td style='background-color: #f8fafc;'><strong style='color: #334155;'>{k}</strong></td><td>{v}</td></tr>")
        html_parts.append("</table>")
        html_parts.append(page_break)

        # Sections
        for i, section in enumerate(valid_sections, 1):
            html_parts.append(f"<h2 style='color: {p_color}; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;'>{i}. {section.title}</h2>")
            clean_content = _clean_unprintable_chars(section.generated_content)
            content_html = _markdown_to_html_with_graphs(clean_content, p_color, s_color)
            html_parts.append(content_html)
            if i < len(valid_sections):
                html_parts.append(page_break)

        css = f"""
        @page {{ size: a4 portrait; margin: 2.5cm; }}
        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.6; color: #334155; }}
        h1, h2, h3, h4 {{ color: {p_color}; margin-top: 25px; margin-bottom: 12px; font-weight: 600; }}
        p {{ margin-bottom: 15px; text-align: justify; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; margin-bottom: 30px; border: 1px solid #cbd5e1; }}
        th {{ background-color: {p_color}; color: white; padding: 10px; text-align: left; font-weight: bold; border: 1px solid {p_color}; }}
        td {{ border: 1px solid #cbd5e1; padding: 10px; }}
        tr:nth-child(even) {{ background-color: #f8fafc; }}
        ul, ol {{ margin-top: 12px; margin-bottom: 15px; padding-left: 25px; }}
        li {{ margin-bottom: 6px; }}
        img {{ max-width: 100%; }}
        blockquote {{ border-left: 4px solid #cbd5e1; margin-left: 0; padding-left: 15px; color: #64748b; font-style: italic; }}
        """

        full_html = f"""
        <html>
        <head>
        <style>{css}</style>
        </head>
        <body>
        {''.join(html_parts)}
        </body>
        </html>
        """
        return full_html


    @staticmethod
    def generate_pdf(deal: Deal) -> bytes:
        """Generate a perfectly formatted PDF with embedded graphs using xhtml2pdf."""
        html = ExportService._generate_html_document(deal, for_pdf=True)
        buffer = io.BytesIO()
        
        # xhtml2pdf logging is noisy, suppress it temporarily if desired, but default is fine
        pisa_status = pisa.CreatePDF(html, dest=buffer)
        
        if pisa_status.err:
            logger.error("Error generating PDF via xhtml2pdf")
            
        return buffer.getvalue()

    @staticmethod
    def generate_docx(deal: Deal) -> bytes:
        """Generate a formatted DOCX with embedded graphs using html2docx."""
        html = ExportService._generate_html_document(deal, for_pdf=False)
        buffer = html2docx(html, title=f"{deal.customer} Credit Pitch Book")
        return buffer.getvalue()

    @staticmethod
    def generate_pptx(deal: Deal) -> bytes:
        """Generate a basic PPTX pitch book."""
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        def _strip_markdown(text: str) -> str:
            text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
            text = re.sub(r"\*(.*?)\*", r"\1", text)
            text = re.sub(r"#{1,6}\s*", "", text)
            text = re.sub(r"`(.*?)`", r"\1", text)
            text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
            return text

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # Title slide
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(0x0f, 0x17, 0x2a)

        txBox = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(11), Inches(1.5))
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = "CREDIT PITCH BOOK"
        p.font.size = Pt(36)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.alignment = PP_ALIGN.CENTER

        txBox2 = slide.shapes.add_textbox(Inches(1), Inches(3.5), Inches(11), Inches(1))
        tf2 = txBox2.text_frame
        p2 = tf2.paragraphs[0]
        p2.text = deal.customer
        p2.font.size = Pt(28)
        p2.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p2.alignment = PP_ALIGN.CENTER

        valid_sections = [
            s for s in sorted(deal.sections, key=lambda x: x.order_index) 
            if s.state == "ready" and s.generated_content and s.generated_content.strip()
        ]

        for section in valid_sections:
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            
            title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.8))
            p = title_box.text_frame.paragraphs[0]
            p.text = section.title
            p.font.size = Pt(24)
            p.font.bold = True
            p.font.color.rgb = RGBColor(0x0f, 0x17, 0x2a)

            content = section.generated_content
            clean = _strip_markdown(content)
            if len(clean) > 2000:
                clean = clean[:2000] + "\n\n[Content truncated — see PDF/DOCX for full text]"

            content_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(12), Inches(5.5))
            tf = content_box.text_frame
            tf.word_wrap = True

            for line in clean.split("\n"):
                line = line.strip()
                if not line:
                    continue
                p = tf.add_paragraph()
                p.text = line
                p.font.size = Pt(11)

        buffer = io.BytesIO()
        prs.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def generate_combined_report(deal: Deal) -> bytes:
        return ExportService.generate_pdf(deal)
