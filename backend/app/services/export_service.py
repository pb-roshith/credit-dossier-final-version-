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
    
    headers = [col.replace('**', '').replace('*', '').strip() for col in lines[0].split('|')[1:-1]]
    rows = []
    for line in lines[2:]:
        cols = [col.replace('**', '').replace('*', '').strip() for col in line.split('|')[1:-1]]
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


def _section_narrative(section: Section) -> str:
    """Return final narrative text with UI-only source markers removed."""
    content = section.final_generated_content or section.generated_content or ""
    # Current inline citation format.
    content = re.sub(
        r"\s*\[Source\s*:\s*[^\]\r\n]+\]",
        "",
        content,
        flags=re.IGNORECASE,
    )
    # Remove legacy numbered reference sections and their inline markers.
    content = re.sub(
        r"\n{0,2}#{1,6}\s*(?:References|Sources|Bibliography)\b.*\Z",
        "",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    content = re.sub(r"\[(?:\d{1,2})(?:\s*,\s*\d{1,2})*\]", "", content)
    return content.strip()

def _markdown_to_html_with_graphs(text: str, theme_palette: list[str]) -> str:
    """Detects numeric markdown tables, injects matplotlib charts, and converts to HTML."""
    table_pattern = re.compile(r'(^[ \t]*\|[^\n]+\|[ \t]*\n[ \t]*\|[-:| ]+\|[ \t]*\n(?:[ \t]*\|[^\n]+\|[ \t]*(?:\n|$))+)', re.MULTILINE)
    
    def replacer(match):
        table_str = match.group(1)
        # Ensure table has empty lines around it so python-markdown parses it correctly
        formatted_table = f"\n\n{table_str.strip()}\n\n"
        
        df = _parse_table_data(table_str)
        if df is not None:
            try:
                fig, ax = plt.subplots(figsize=(10, 6))
                # Use the dynamic colors from the full palette
                colors = theme_palette if len(theme_palette) >= 5 else (theme_palette + ["#64748b", "#94a3b8", "#cbd5e1", "#334155", "#0f172a"])
                bars = df.plot(x=df.columns[0], kind='bar', ax=ax, color=colors[:len(df.columns)-1], width=0.7)
                
                def format_label(val):
                    if pd.isna(val) or val == 0:
                        return ""
                    abs_val = abs(val)
                    if abs_val >= 1_000_000:
                        return f"{val/1_000_000:.1f}M"
                    elif abs_val >= 1_000:
                        return f"{val/1_000:.1f}K"
                    elif abs_val >= 1:
                        return f"{val:.1f}"
                    else:
                        return f"{val:.2f}"

                # Add value labels
                for container in ax.containers:
                    labels = [format_label(v.get_height()) for v in container]
                    ax.bar_label(container, labels=labels, padding=3, color='#334155', fontsize=9, fontweight='bold', rotation=90)
                
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_visible(False)
                ax.set_xlabel("")
                ax.set_yticks([]) # Hide y-ticks to rely on bar labels
                plt.xticks(rotation=45, ha='right', fontsize=10)
                ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=min(3, len(df.columns)-1), frameon=False)
                plt.tight_layout()
                
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=300, transparent=True, bbox_inches='tight')
                plt.close(fig)
                
                img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                img_tag = f"<div style='text-align:center; margin: 20px 0;'><img src='data:image/png;base64,{img_b64}' style='max-width: 100%; height: auto;' /></div>\n\n"
                return formatted_table + img_tag
            except Exception as e:
                logger.error(f"Failed to plot table: {e}")
                return formatted_table
        return formatted_table

    transformed = table_pattern.sub(replacer, text)
    html = markdown.markdown(transformed, extensions=['tables'])
    
    # Post-process HTML to force equal column widths in PDF
    def fix_table_widths(match):
        table_html = match.group(0)
        # Find number of columns from the first row
        tr_match = re.search(r'<tr\b[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
        if not tr_match:
            return table_html
            
        cells = re.findall(r'<(?:th|td)\b', tr_match.group(1), re.IGNORECASE)
        if not cells:
            return table_html
            
        col_count = len(cells)
        if col_count == 0:
            return table_html
            
        width_pct = int(100 / col_count)
        
        # Inject HTML width attribute into ALL th and td tags to force xhtml2pdf to obey boundaries
        table_html = re.sub(r'<(th|td)\b([^>]*)>', f'<\\1 width="{width_pct}%" \\2>', table_html, flags=re.IGNORECASE)
        return table_html

    html = re.sub(r'<table\b.*?>.*?</table>', fix_table_widths, html, flags=re.DOTALL | re.IGNORECASE)
    
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
            if s.state == "ready" and _section_narrative(s).strip()
        ]

        # Use the deal's dynamic theme colors, handling None or empty strings
        p_color = getattr(deal, "primary_color", None) or "#002060"
        s_color = getattr(deal, "secondary_color", None) or "#800020"
        
        # Parse full palette
        import json
        raw_palette = getattr(deal, "theme_palette", None)
        if raw_palette:
            try:
                theme_palette = json.loads(raw_palette)
            except Exception:
                theme_palette = [p_color, s_color, "#1e293b", "#3b82f6", "#f59e0b"]
        else:
            theme_palette = [p_color, s_color, "#1e293b", "#3b82f6", "#f59e0b"]

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
            clean_content = _clean_unprintable_chars(_section_narrative(section))
            content_html = _markdown_to_html_with_graphs(clean_content, theme_palette)
            html_parts.append(content_html)
            if i < len(valid_sections):
                html_parts.append(page_break)

        css = f"""
        @page {{ size: a4 portrait; margin: 2.0cm; }}
        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.5; color: #334155; }}
        h1, h2, h3, h4 {{ color: {p_color}; margin-top: 25px; margin-bottom: 12px; font-weight: 600; }}
        p {{ margin-bottom: 15px; text-align: justify; }}
        table {{ width: 100%; table-layout: fixed; border-collapse: collapse; margin-top: 15px; margin-bottom: 25px; border: 1px solid #cbd5e1; -pdf-keep-with-next: false; }}
        th {{ background-color: {p_color}; color: white; padding: 8px 10px; text-align: left; font-weight: bold; border: 1px solid {p_color}; word-wrap: break-word; }}
        td {{ border: 1px solid #cbd5e1; padding: 8px 10px; vertical-align: top; word-wrap: break-word; }}
        tr:nth-child(even) {{ background-color: #f8fafc; }}
        ul, ol {{ margin-top: 10px; margin-bottom: 15px; padding-left: 20px; }}
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
    async def generate_pptx(deal: Deal) -> bytes:
        """Generate a well-designed PPTX pitch book using Mistral for formatting."""
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        import json
        import urllib.request
        import urllib.parse
        import asyncio
        import httpx
        import re
        from app.services.mistral_library_service import _get_client, _call_with_retry
        from app.config import settings

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        p_color = getattr(deal, "primary_color", None) or "#002060"
        s_color = getattr(deal, "secondary_color", None) or "#800020"
        
        theme_palette = deal.theme_palette if isinstance(deal.theme_palette, list) else []
        if not theme_palette:
            theme_palette = [p_color, s_color, "#64748b", "#94a3b8", "#cbd5e1"]

        # Convert hex (e.g. "#002060") to RGBColor
        def hex_to_rgb(hex_str: str) -> RGBColor:
            hex_str = hex_str.lstrip('#')
            if len(hex_str) != 6:
                return RGBColor(0, 0, 0)
            return RGBColor(int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))

        primary_rgb = hex_to_rgb(p_color)
        secondary_rgb = hex_to_rgb(s_color)

        # Title slide
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = primary_rgb

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
        p2.font.color.rgb = secondary_rgb
        p2.alignment = PP_ALIGN.CENTER

        valid_sections = [
            s for s in sorted(deal.sections, key=lambda x: x.order_index) 
            if s.state == "ready" and _section_narrative(s).strip()
        ]

        client = _get_client()

        system_prompt = """
        You are an expert presentation designer. Convert the following text into a well-designed presentation format.
        Return ONLY valid JSON with this exact schema:
        {
          "slides": [
            {
              "title": "Main point title",
              "bullet_points": ["Summarized point 1", "Summarized point 2"],
              "image_prompt": "A keyword or short prompt for an image representing the slide (e.g. 'finance graph', 'factory building', 'corporate team'), or null if no image is needed."
            }
          ]
        }
        Do not output any markdown code blocks, just the raw JSON.
        Make it brief and concise, 1-2 slides maximum depending on content length.
        """

        table_pattern = re.compile(r'(^[ \t]*\|[^\n]+\|[ \t]*\n[ \t]*\|[-:| ]+\|[ \t]*\n(?:[ \t]*\|[^\n]+\|[ \t]*(?:\n|$))+)', re.MULTILINE)
        sem = asyncio.Semaphore(5)

        async def process_section(section):
            async with sem:
                content = _section_narrative(section)
                charts = []
                native_tables = []
                
                # Extract markdown tables
                matches = table_pattern.findall(content)
                for table_str in matches:
                    df = _parse_table_data(table_str)
                    if df is not None:
                        try:
                            import matplotlib.pyplot as plt
                            fig, ax = plt.subplots(figsize=(10, 6))
                            colors = theme_palette if len(theme_palette) >= 5 else (theme_palette + ["#64748b", "#94a3b8", "#cbd5e1", "#334155", "#0f172a"])
                            bars = df.plot(x=df.columns[0], kind='bar', ax=ax, color=colors[:len(df.columns)-1], width=0.7)
                            
                            def format_label(val):
                                if pd.isna(val) or val == 0:
                                    return ""
                                abs_val = abs(val)
                                if abs_val >= 1_000_000:
                                    return f"{val/1_000_000:.1f}M"
                                elif abs_val >= 1_000:
                                    return f"{val/1_000:.1f}K"
                                elif abs_val >= 1:
                                    return f"{val:.1f}"
                                else:
                                    return f"{val:.2f}"
                                    
                            for container in ax.containers:
                                labels = [format_label(v.get_height()) for v in container]
                                ax.bar_label(container, labels=labels, padding=3, color='#334155', fontsize=9, fontweight='bold', rotation=90)
                                
                            ax.spines['top'].set_visible(False)
                            ax.spines['right'].set_visible(False)
                            ax.spines['left'].set_visible(False)
                            ax.set_xlabel("")
                            ax.set_yticks([])
                            plt.xticks(rotation=45, ha='right', fontsize=10)
                            ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=min(3, len(df.columns)-1), frameon=False)
                            plt.tight_layout()
                            
                            buf = io.BytesIO()
                            fig.savefig(buf, format='png', dpi=300, transparent=True, bbox_inches='tight')
                            plt.close(fig)
                            charts.append(buf.getvalue())
                        except Exception as e:
                            logger.error(f"Failed to generate PPT chart: {e}")
                    else:
                        lines = table_str.strip().split('\n')
                        if len(lines) >= 3:
                            headers = [col.strip() for col in lines[0].split('|')[1:-1]]
                            rows = []
                            for line in lines[2:]:
                                cols = [col.strip() for col in line.split('|')[1:-1]]
                                if len(cols) == len(headers):
                                    rows.append(cols)
                            if rows:
                                native_tables.append((headers, rows))
                
                try:
                    response = await _call_with_retry(
                        lambda sec=section: client.chat.complete_async(
                            model=settings.MISTRAL_MODEL,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": f"Section: {sec.title}\n\nContent:\n{_section_narrative(sec)}"}
                            ],
                            temperature=0.2,
                            response_format={"type": "json_object"}
                        ),
                        description=f"PPT slide generation for '{section.title}'",
                    )
                    
                    raw = response.choices[0].message.content or "{}"
                    if raw.startswith("```"):
                        lines = raw.split("\n")
                        lines = [l for l in lines if not l.strip().startswith("```")]
                        raw = "\n".join(lines).strip()
                    
                    slide_data = json.loads(raw)
                    slides_list = slide_data.get("slides", [])
                    
                except Exception as e:
                    logger.error(f"Failed to generate slides for {section.title}: {e}")
                    slides_list = [{
                        "title": section.title,
                        "bullet_points": [content[:500] + "..."],
                        "image_prompt": None
                    }]

                # Allocate generated charts to slides instead of fetching AI images
                for i, slide_info in enumerate(slides_list):
                    slide_info["img_bytes"] = None
                    if i < len(charts):
                        slide_info["img_bytes"] = charts[i]
                        slide_info["image_prompt"] = None

                # Fetch AI images only if no chart was assigned
                async with httpx.AsyncClient(timeout=15.0) as http_client:
                    for slide_info in slides_list:
                        if slide_info["img_bytes"] is not None:
                            continue
                        img_prompt = slide_info.get("image_prompt")
                        if img_prompt and str(img_prompt).lower() not in ["null", "none"]:
                            try:
                                safe_prompt = urllib.parse.quote(str(img_prompt))
                                img_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=400&height=300&nologo=true"
                                resp = await http_client.get(img_url, headers={'User-Agent': 'Mozilla/5.0'})
                                if resp.status_code == 200:
                                    slide_info["img_bytes"] = resp.content
                            except Exception as e:
                                logger.warning(f"Failed to fetch image for prompt '{img_prompt}': {e}")
                                
                return section, slides_list, native_tables

        tasks = [process_section(sec) for sec in valid_sections]
        results = await asyncio.gather(*tasks)

        for section, slides_list, native_tables in results:
            for slide_info in slides_list:
                slide = prs.slides.add_slide(prs.slide_layouts[1])
                title_shape = slide.shapes.title
                body_shape = slide.placeholders[1]

                title_shape.text = slide_info.get("title", section.title)
                title_shape.text_frame.paragraphs[0].font.color.rgb = primary_rgb
                
                tf = body_shape.text_frame
                tf.clear() # Clear default formatting safely
                
                for idx, point in enumerate(slide_info.get("bullet_points", [])):
                    if idx == 0:
                        p = tf.paragraphs[0]
                    else:
                        p = tf.add_paragraph()
                    p.text = str(point)
                    p.font.size = Pt(16)
                    p.font.color.rgb = RGBColor(0x33, 0x33, 0x33) # Dark Gray, not white
                    p.level = 0
                    p.space_after = Pt(10)
                
                img_bytes = slide_info.get("img_bytes")
                if img_bytes:
                    try:
                        img_stream = io.BytesIO(img_bytes)
                        slide.shapes.add_picture(img_stream, Inches(7.5), Inches(2.0), width=Inches(5.0))
                        body_shape.width = Inches(6.5)
                    except Exception as e:
                        logger.warning(f"Failed to embed image: {e}")

            for headers, rows in native_tables:
                slide = prs.slides.add_slide(prs.slide_layouts[1])
                slide.shapes.title.text = f"{section.title} - Data"
                slide.shapes.title.text_frame.paragraphs[0].font.color.rgb = primary_rgb
                
                sp = slide.placeholders[1]._element
                sp.getparent().remove(sp)
                
                rows_cnt = len(rows) + 1
                cols_cnt = len(headers)
                left = Inches(1.0)
                top = Inches(2.0)
                width = Inches(11.0)
                height = Inches(0.5 * rows_cnt)
                
                table_shape = slide.shapes.add_table(rows_cnt, cols_cnt, left, top, width, height)
                table = table_shape.table
                
                for col_idx, header in enumerate(headers):
                    if col_idx >= cols_cnt: break
                    cell = table.cell(0, col_idx)
                    cell.text = header
                    cell.text_frame.paragraphs[0].font.bold = True
                    cell.text_frame.paragraphs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = primary_rgb
                    
                for row_idx, row_data in enumerate(rows):
                    for col_idx, cell_data in enumerate(row_data):
                        if col_idx < cols_cnt:
                            cell = table.cell(row_idx + 1, col_idx)
                            cell.text = str(cell_data)
                            cell.text_frame.paragraphs[0].font.size = Pt(12)
                            cell.text_frame.paragraphs[0].font.color.rgb = RGBColor(0x33, 0x33, 0x33)

        buffer = io.BytesIO()
        prs.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def generate_combined_report(deal: Deal) -> bytes:
        return ExportService.generate_pdf(deal)
