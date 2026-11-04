"""Generate a small text-table fixture, not a device datasheet."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

destination = Path(__file__).parent / 'validation-output' / 'fixture.pdf'
destination.parent.mkdir(parents=True, exist_ok=True)
document = canvas.Canvas(str(destination))
document.drawString(40, 800, 'TEST FIXTURE - Pin Descriptions')
table = Table([['Pin', 'Name', 'Type'], ['1', 'VDD', 'Power'], ['2', 'DATA', 'Input/Output'], ['EP', 'GND', 'Ground']], colWidths=[80, 100, 100], rowHeights=25)
table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 1, (0, 0, 0))]))
table.wrapOn(document, 500, 700)
table.drawOn(document, 40, 600)
document.save()
