"""Convert submission markdown docs to .docx format."""
import re, os
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

BASE = os.path.dirname(os.path.abspath(__file__))


def md_table_to_docx(doc, table_text):
    """Parse a markdown table block and add it to the docx document."""
    lines = [l.strip() for l in table_text.strip().split('\n') if l.strip() and not l.strip().startswith('|--')]
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip('|').split('|')]
        rows.append(cells)
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncols, style='Light Grid Accent 1')
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row_data in enumerate(rows):
        for j, cell_text in enumerate(row_data):
            if j < ncols:
                cell = table.rows[i].cells[j]
                cell.text = cell_text
                if i == 0:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.bold = True
    doc.add_paragraph()


def convert_md_to_docx(md_path, docx_path):
    doc = Document()

    # Set default font
    style = doc.styles['Normal']
    font = style.font
    font.name = '宋体'
    font.size = Pt(11)

    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into blocks
    # Handle tables first (extract them)
    table_pattern = re.compile(r'(\|.+\|[\r\n]+\|[-| ]+\|[\r\n]+(?:\|.+\|[\r\n]+)*)', re.MULTILINE)
    table_blocks = list(table_pattern.finditer(content))
    table_positions = {m.start(): m.end() for m in table_blocks}

    i = 0
    while i < len(content):
        if i in table_positions:
            # Insert table
            table_text = content[i:table_positions[i]]
            md_table_to_docx(doc, table_text)
            i = table_positions[i]
            continue

        # Find next line
        next_nl = content.find('\n', i)
        if next_nl < 0:
            line = content[i:]
            i = len(content)
        else:
            line = content[i:next_nl]
            i = next_nl + 1

        line = line.strip()
        if not line:
            continue

        # Headers
        if line.startswith('# '):
            doc.add_heading(line[2:], level=1)
        elif line.startswith('## '):
            doc.add_heading(line[3:], level=2)
        elif line.startswith('### '):
            doc.add_heading(line[4:], level=3)
        elif line.startswith('#### '):
            doc.add_heading(line[5:], level=4)
        elif line.startswith('!['):
            # Skip image tags
            continue
        elif line.startswith('- ') or line.startswith('* '):
            doc.add_paragraph(line[2:], style='List Bullet')
        elif re.match(r'^\d+\.', line):
            doc.add_paragraph(re.sub(r'^\d+\.\s*', '', line), style='List Number')
        elif line.startswith('```'):
            # Skip code blocks
            j = content.find('```', i)
            if j >= 0:
                code = content[i:j].strip()
                p = doc.add_paragraph()
                run = p.add_run(code)
                run.font.name = 'Consolas'
                run.font.size = Pt(9)
                i = j + 3
            continue
        elif line.startswith('---'):
            doc.add_paragraph('_' * 60)
        else:
            # Regular paragraph
            # Remove bold markers
            line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
            line = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
            doc.add_paragraph(line)

    doc.save(docx_path)
    print(f'  -> {os.path.basename(docx_path)}')


if __name__ == '__main__':
    for md_file in ['数据来源说明.md', '数据探查记录表.md', 'README.md', '数据清洗说明.md']:
        md_path = os.path.join(BASE, md_file)
        docx_path = os.path.join(BASE, md_file.replace('.md', '.docx'))
        if os.path.exists(md_path):
            print(f'Converting {md_file}...')
            convert_md_to_docx(md_path, docx_path)
    print('Done!')
