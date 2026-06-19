import streamlit as st
import pdfplumber
import anthropic
import json
import re
import io
import os
import base64
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER

st.set_page_config(page_title="SKS Invoice Generator", page_icon="📄", layout="centered")

st.title("SKS Invoice Generator")
st.markdown("Upload a Taurus Biogas invoice to generate the SKS version.")

uploaded_file = st.file_uploader("Upload Taurus Invoice PDF", type=["pdf"])

def extract_text_from_pdf(file_bytes):
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def parse_invoice_with_claude(text):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    prompt = f"""Extract all invoice data from this text and return ONLY valid JSON with no extra text or markdown.

Return this exact structure:
{{
  "bill_to": {{
    "name": "company name",
    "address_line1": "street address",
    "address_line2": "city, state zip"
  }},
  "invoice_number": "1626",
  "date": "06/19/2026",
  "due_date": "07/19/2026",
  "terms": "Net 30",
  "po_number": "4400117356",
  "line_items": [
    {{"description": "SKS-Wheeler O&M Fee", "amount": "5,000.00"}},
    {{"description": "SKS-Mibelloon O&M Fee", "amount": "5,000.00"}}
  ],
  "subtotal_label": "Wheeler + Mibelloon",
  "subtotal": "68,314.62",
  "tax": "0.00",
  "total": "68,314.62",
  "balance_due": "$68,314.62"
}}

Invoice text:
{text}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return json.loads(raw)

def generate_sks_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )

    styles = getSampleStyleSheet()
    story = []

    # --- HEADER ---
    header_style_left = ParagraphStyle('HeaderLeft', fontSize=9, leading=13, fontName='Helvetica-Bold')
    header_style_normal = ParagraphStyle('HeaderNormal', fontSize=9, leading=13, fontName='Helvetica')

    logo_path = os.path.join(os.path.dirname(__file__), "sks_logo.jpg")
    logo = Image(logo_path, width=2.2*inch, height=0.82*inch)

    left_block = [
        Paragraph("SKS Development LLC", header_style_left),
        Paragraph("2175 NW Raleigh St Ste 110", header_style_normal),
        Paragraph("Portland, OR  97210", header_style_normal),
        Paragraph("+15038539392", header_style_normal),
        Paragraph("Nathan Kennedy", header_style_normal),
    ]

    header_table = Table(
        [[left_block, logo]],
        colWidths=[4*inch, 2.75*inch]
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.2*inch))

    # --- INVOICE TITLE ---
    invoice_title_style = ParagraphStyle('InvoiceTitle', fontSize=22, fontName='Helvetica', textColor=colors.HexColor('#555555'))
    story.append(Paragraph("INVOICE", invoice_title_style))
    story.append(Spacer(1, 0.15*inch))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.15*inch))

    # --- BILL TO + INVOICE DETAILS ---
    label_style = ParagraphStyle('Label', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#4a90d9'))
    value_style = ParagraphStyle('Value', fontSize=9, fontName='Helvetica', leading=13)
    detail_label_style = ParagraphStyle('DetailLabel', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#4a90d9'), alignment=TA_RIGHT)
    detail_value_style = ParagraphStyle('DetailValue', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT, leading=13)

    bill_to = data.get("bill_to", {})
    bill_block = [
        Paragraph("BILL TO", label_style),
        Paragraph(bill_to.get("name", ""), value_style),
        Paragraph(bill_to.get("address_line1", ""), value_style),
        Paragraph(bill_to.get("address_line2", ""), value_style),
    ]

    detail_block = [
        [Paragraph("INVOICE #", detail_label_style), Paragraph(data.get("invoice_number", ""), detail_value_style)],
        [Paragraph("DATE", detail_label_style), Paragraph(data.get("date", ""), detail_value_style)],
        [Paragraph("DUE DATE", detail_label_style), Paragraph(data.get("due_date", ""), detail_value_style)],
        [Paragraph("TERMS", detail_label_style), Paragraph(data.get("terms", ""), detail_value_style)],
    ]
    detail_table = Table(detail_block, colWidths=[1.2*inch, 1.5*inch])
    detail_table.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
    ]))

    top_table = Table([[bill_block, detail_table]], colWidths=[4*inch, 2.75*inch])
    top_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(top_table)
    story.append(Spacer(1, 0.15*inch))

    # --- PO NUMBER ---
    story.append(Paragraph("PO #", label_style))
    story.append(Paragraph(data.get("po_number", ""), value_style))
    story.append(Spacer(1, 0.2*inch))

    # --- LINE ITEMS TABLE ---
    col_header_style = ParagraphStyle('ColHeader', fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#4a90d9'))
    col_header_right = ParagraphStyle('ColHeaderRight', fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#4a90d9'), alignment=TA_RIGHT)
    line_desc_style = ParagraphStyle('LineDesc', fontSize=9, fontName='Helvetica')
    line_amt_style = ParagraphStyle('LineAmt', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT)

    table_data = [[Paragraph("DATE", col_header_style), Paragraph("DESCRIPTION", col_header_style), Paragraph("AMOUNT", col_header_right)]]

    for item in data.get("line_items", []):
        table_data.append([
            Paragraph("", line_desc_style),
            Paragraph(item.get("description", ""), line_desc_style),
            Paragraph(item.get("amount", ""), line_amt_style),
        ])

    line_table = Table(table_data, colWidths=[0.8*inch, 4.45*inch, 1.5*inch])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f0f7ff')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fafafa')]),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 0.1*inch))

    # --- TOTALS ---
    subtotal_label = data.get("subtotal_label", "")
    totals_data = [
        [Paragraph(subtotal_label, value_style), Paragraph("SUBTOTAL", detail_label_style), Paragraph(data.get("subtotal", ""), line_amt_style)],
        [Paragraph("", value_style), Paragraph("TAX", detail_label_style), Paragraph(data.get("tax", ""), line_amt_style)],
        [Paragraph("", value_style), Paragraph("TOTAL", detail_label_style), Paragraph(data.get("total", ""), line_amt_style)],
    ]
    totals_table = Table(totals_data, colWidths=[3*inch, 1.75*inch, 2*inch])
    totals_table.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LINEABOVE', (0,0), (-1,0), 0.5, colors.HexColor('#dddddd')),
        ('LINEBELOW', (0,-1), (-1,-1), 0.5, colors.HexColor('#dddddd')),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 0.2*inch))

    # --- BALANCE DUE ---
    balance_style_label = ParagraphStyle('BalLabel', fontSize=10, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    balance_style_value = ParagraphStyle('BalValue', fontSize=14, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    balance_data = [[
        Paragraph("BALANCE DUE", balance_style_label),
        Paragraph(data.get("balance_due", ""), balance_style_value),
    ]]
    balance_table = Table(balance_data, colWidths=[4.75*inch, 2*inch])
    balance_table.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
    ]))
    story.append(balance_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

if uploaded_file:
    with st.spinner("Reading invoice..."):
        file_bytes = uploaded_file.read()
        text = extract_text_from_pdf(file_bytes)

    with st.spinner("Extracting data with AI..."):
        try:
            data = parse_invoice_with_claude(text)
            st.success("Invoice data extracted!")

            with st.expander("Preview extracted data"):
                st.json(data)

        except Exception as e:
            st.error(f"Failed to parse invoice: {e}")
            st.stop()

    with st.spinner("Generating SKS invoice PDF..."):
        try:
            pdf_bytes = generate_sks_pdf(data)
            original_name = os.path.splitext(uploaded_file.name)[0]
            filename = f"{original_name}_v_SKS.pdf"

            st.download_button(
                label="⬇️ Download SKS Invoice PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf"
            )
        except Exception as e:
            st.error(f"Failed to generate PDF: {e}")
