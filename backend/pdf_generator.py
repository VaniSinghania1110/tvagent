import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_trip_itinerary_pdf(trip_data: dict, booking_data: dict = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom Luxury Styles
    primary_color = colors.HexColor("#0B2027")
    gold_color = colors.HexColor("#C9A227")
    gold_dark = colors.HexColor("#997A16")
    bg_light = colors.HexColor("#FAF8F5")
    forest_green = colors.HexColor("#166534")
    border_color = colors.HexColor("#E2D8C6")
    ink_color = colors.HexColor("#17242A")
    ink_soft = colors.HexColor("#55625F")

    header_title_style = ParagraphStyle(
        'DocHeaderTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.white
    )

    header_sub_style = ParagraphStyle(
        'DocHeaderSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#E5C358")
    )

    trip_title_style = ParagraphStyle(
        'TripTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=primary_color
    )

    tagline_style = ParagraphStyle(
        'TripTagline',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=11,
        leading=15,
        textColor=ink_soft
    )

    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=primary_color,
        spaceBefore=14,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=ink_color
    )

    spec_label_style = ParagraphStyle(
        'SpecLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=ink_soft
    )

    spec_val_style = ParagraphStyle(
        'SpecVal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=primary_color
    )

    day_title_style = ParagraphStyle(
        'DayTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=13,
        textColor=primary_color
    )

    day_meta_style = ParagraphStyle(
        'DayMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=gold_dark
    )

    inc_item_style = ParagraphStyle(
        'IncItem',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=forest_green
    )

    exc_item_style = ParagraphStyle(
        'ExcItem',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#991B1B")
    )

    story = []

    # 1. TOP OFFICIAL HEADER BLOCK
    header_data = [
        [
            Paragraph("<b>TRAVELVERSE</b> &bull; OFFICIAL EXPEDITION DOSSIER", header_sub_style),
            Paragraph("VERIFIED OPERATOR &bull; SECURE PROTOCOL", header_sub_style)
        ],
        [
            Paragraph("Official Expedition Itinerary", header_title_style),
            Paragraph(f"Host: <b>{trip_data.get('agent_name', 'Host Guide')}</b><br/>{trip_data.get('agency_name', 'Certified Agency')}", ParagraphStyle('RightHost', parent=header_sub_style, alignment=2, textColor=colors.white))
        ]
    ]
    header_table = Table(header_data, colWidths=[330, 190])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), primary_color),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 12),
        ('LINEBELOW', (0, -1), (-1, -1), 3, gold_color),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # 2. OPTIONAL RESERVATION VOUCHER BANNER (IF BOOKING PRESENT)
    if booking_data:
        b_code = booking_data.get('booking_code') or 'CONFIRMED'
        u_name = booking_data.get('user_name') or 'Valued Guest'
        seats = booking_data.get('seats', 1)
        b_date = booking_data.get('created_at', 'Recent')

        voucher_data = [
            [
                Paragraph(f"<b>PASSENGER RESERVATION VOUCHER</b><br/><font size='12' color='#17242A'><b>{u_name}</b></font> &bull; {seats} Confirmed Seat(s)", body_style),
                Paragraph(f"<font color='#065F46'><b>&bull; STATUS: CONFIRMED</b></font><br/><b>Ref: {b_code}</b><br/>Booked: {b_date}", ParagraphStyle('VRight', parent=body_style, alignment=2, fontSize=8.5))
            ]
        ]
        voucher_table = Table(voucher_data, colWidths=[330, 190])
        voucher_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#A7F3D0")),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(voucher_table)
        story.append(Spacer(1, 10))

    # 3. TITLE & EXPEDITION BANNER
    title = trip_data.get('title', 'Expedition Itinerary')
    tagline = trip_data.get('tagline') or f"Curated expedition across {trip_data.get('destination', 'the destination')}"
    story.append(Paragraph(title, trip_title_style))
    story.append(Paragraph(tagline, tagline_style))
    story.append(Spacer(1, 10))

    # 4. 6-METRIC PARAMETERS GRID
    dest = trip_data.get('destination', 'Global')
    dur = f"{trip_data.get('duration_days', 2)} Days"
    diff = trip_data.get('difficulty', 'Moderate').split('(')[0].strip()
    cap = f"Max {trip_data.get('max_capacity', 15)} Spots"
    price = f"${trip_data.get('price', 200)} {trip_data.get('currency', 'USD')} / Person"
    season = trip_data.get('season_climate', 'Optimal Season')

    specs_data = [
        [
            Paragraph("DESTINATION", spec_label_style),
            Paragraph("DURATION & PACING", spec_label_style),
            Paragraph("DIFFICULTY LEVEL", spec_label_style)
        ],
        [
            Paragraph(f"<b>{dest}</b>", spec_val_style),
            Paragraph(f"<b>{dur}</b>", spec_val_style),
            Paragraph(f"<b>{diff}</b>", spec_val_style)
        ],
        [
            Paragraph("PRICE PER PERSON", spec_label_style),
            Paragraph("GROUP CAPACITY", spec_label_style),
            Paragraph("OPTIMAL SEASON", spec_label_style)
        ],
        [
            Paragraph(f"<b>{price}</b>", spec_val_style),
            Paragraph(f"<b>{cap}</b>", spec_val_style),
            Paragraph(f"<b>{season}</b>", spec_val_style)
        ]
    ]
    specs_table = Table(specs_data, colWidths=[173, 173, 174])
    specs_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_light),
        ('BOX', (0, 0), (-1, -1), 1, border_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(specs_table)
    story.append(Spacer(1, 10))

    # 5. EXPEDITION OVERVIEW
    story.append(Paragraph("EXPEDITION OVERVIEW & HIGHLIGHTS", section_heading_style))
    desc = trip_data.get('description') or f"Join our certified guides on an extraordinary departure across {dest}."
    story.append(Paragraph(desc, body_style))
    story.append(Spacer(1, 10))

    # 6. DAY-BY-DAY ITINERARY TIMELINE
    itinerary = trip_data.get('itinerary') or []
    if itinerary:
        story.append(Paragraph("DAY-BY-DAY ITINERARY TIMELINE", section_heading_style))
        for d in itinerary:
            d_num = d.get('day', 1)
            d_title = d.get('title', 'Exploration & Journey')
            d_acts = d.get('activities', '')
            d_meals = d.get('meals', 'Breakfast Included')
            d_stay = d.get('stay', 'Curated Boutique Stay')

            day_block = [
                [
                    Paragraph(f"<b>DAY {d_num}</b>", ParagraphStyle('DNum', parent=body_style, fontName='Helvetica-Bold', fontSize=10, textColor=gold_dark, alignment=1)),
                    Paragraph(f"<b>{d_title}</b><br/><font color='#4A5568'>{d_acts}</font><br/><font size='8' color='#718096'>Meals: <b>{d_meals}</b> &bull; Stay: <b>{d_stay}</b></font>", body_style)
                ]
            ]
            day_table = Table(day_block, colWidths=[65, 455])
            day_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#FFFDF9")),
                ('BACKGROUND', (1, 0), (1, -1), colors.HexColor("#FFFFFF")),
                ('BOX', (0, 0), (-1, -1), 0.75, border_color),
                ('LINEBEFORE', (1, 0), (1, -1), 1.5, gold_color),
                ('PADDING', (0, 0), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(KeepTogether([day_table, Spacer(1, 5)]))

    # 7. INCLUSIONS & EXCLUSIONS 2-COLUMN TABLE
    inclusions = trip_data.get('inclusions') or ['All curated accommodations', 'Daily breakfast & dinners', 'All fort & monument passes', 'Private AC transport', 'Certified guide']
    exclusions = trip_data.get('exclusions') or ['Airfare to rendezvous point', 'Personal travel & medical insurance', 'Discretionary tips & drinks']

    inc_text = "<br/>".join([f"&bull; {inc}" for inc in inclusions])
    exc_text = "<br/>".join([f"&bull; {exc}" for exc in exclusions])

    inc_exc_data = [
        [
            Paragraph("<b>GUARANTEED INCLUSIONS</b>", ParagraphStyle('IncH', parent=body_style, fontName='Helvetica-Bold', fontSize=9, textColor=forest_green)),
            Paragraph("<b>WHAT IS NOT INCLUDED</b>", ParagraphStyle('ExcH', parent=body_style, fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor("#991B1B")))
        ],
        [
            Paragraph(inc_text, inc_item_style),
            Paragraph(exc_text, exc_item_style)
        ]
    ]
    inc_exc_table = Table(inc_exc_data, colWidths=[255, 265])
    inc_exc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F0FDF4")),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor("#FEF2F2")),
        ('BOX', (0, 0), (0, -1), 1, colors.HexColor("#BBF7D0")),
        ('BOX', (1, 0), (1, -1), 1, colors.HexColor("#FECACA")),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(Spacer(1, 8))
    story.append(KeepTogether([
        Paragraph("PACKAGE PARAMETERS & POLICIES", section_heading_style),
        inc_exc_table
    ]))

    # 8. LOGISTICS, MEETING POINT & SAFETY
    mp = trip_data.get('meeting_point') or '08:30 AM at Central Transit Terminal'
    dp = trip_data.get('dropoff_point') or '05:00 PM at Concluding City Airport'
    pack_list = trip_data.get('packing_essentials') or ['Walking shoes with grip', 'Weather-appropriate layers', 'UV sunglasses', 'Photo ID card']
    pack_str = ", ".join(pack_list) if isinstance(pack_list, list) else str(pack_list)
    health = trip_data.get('health_advisory') or 'Moderate walking required. Please inform host guide of any medical or dietary needs.'

    log_data = [
        [
            Paragraph("<b>Meeting Point & Reporting Time:</b>", spec_label_style),
            Paragraph(mp, body_style)
        ],
        [
            Paragraph("<b>Concluding Drop-off Point:</b>", spec_label_style),
            Paragraph(dp, body_style)
        ],
        [
            Paragraph("<b>Mandatory Packing Essentials:</b>", spec_label_style),
            Paragraph(pack_str, body_style)
        ],
        [
            Paragraph("<b>Health & Altitude Advisory:</b>", spec_label_style),
            Paragraph(health, body_style)
        ]
    ]
    log_table = Table(log_data, colWidths=[160, 360])
    log_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_light),
        ('BOX', (0, 0), (-1, -1), 1, border_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(Spacer(1, 8))
    story.append(KeepTogether([
        Paragraph("RENDEZVOUS & TRAVEL LOGISTICS", section_heading_style),
        log_table
    ]))

    # 9. CERTIFICATION FOOTER
    h_agent = trip_data.get('agent_name', 'Host Guide')
    h_agency = trip_data.get('agency_name', 'TravelVerse Expeditions')
    h_email = trip_data.get('agent_email', '')

    footer_data = [
        [
            Paragraph(f"<b>Certified Operator:</b> {h_agent} &bull; {h_agency}<br/><font color='#718096'>Official Contact: {h_email}</font>", body_style),
            Paragraph("<b>&bull; OFFICIAL TRAVELVERSE SEAL</b><br/><font size='8' color='#C9A227'>VERIFIED EXPEDITION PROTOCOL</font>", ParagraphStyle('Seal', parent=body_style, alignment=2))
        ]
    ]
    footer_table = Table(footer_data, colWidths=[330, 190])
    footer_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 1, border_color),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(Spacer(1, 14))
    story.append(KeepTogether([footer_table]))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

