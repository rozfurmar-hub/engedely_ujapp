from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

buffer = io.BytesIO()
doc = SimpleDocTemplate(buffer, pagesize=A4)

story = []

for _, row in df.iterrows():
    table = []
    for key, label in human_labels.items():
        value = row.get(key, "")
        table.append([label, str(value)])

    t = Table(table, colWidths=[200, 300])
    t.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (0,-1), 'LEFT'),
        ('ALIGN', (1,0), (1,-1), 'LEFT'),
    ]))

    story.append(t)
    story.append(Spacer(1, 20))

doc.build(story)
buffer.seek(0)

st.download_button(
    "PDF export",
    buffer,
    file_name="export.pdf",
    mime="application/pdf"
)
