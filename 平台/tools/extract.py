"""Read-only extraction of chapter 2 and source page images. No OCR estimates are simulation inputs."""
from pathlib import Path
import json, hashlib, unicodedata
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / '数据中心供电-负载协同优化运行技术研究_叶桂森.pdf'

def main():
    out = ROOT / 'evidence'
    out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(SOURCE)
    text = []
    for i in range(29, 61):
        raw = doc[i].get_text()
        clean = ''.join(c for c in unicodedata.normalize('NFKC', raw)
                        if not 0xE000 <= ord(c) <= 0xF8FF)
        text.append(f'\n===== PDF {i+1}; printed page {i-8} =====\n{clean}')
    (out / 'chapter2_text.txt').write_text(''.join(text), encoding='utf-8')
    # Complete relevant pages, including formula/table context.
    for page in [34, 38, 41, 43, 45, 52, 53, 54, 55, 56, 57, 58, 59, 60]:
        doc[page-1].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(out / f'page_{page:03}.png')
    crops = {15:(54, (82,71,501,286)), 16:(54,(82,294,501,477)),
             17:(54,(82,497,501,708)), 18:(56,(82,325,505,532)),
             19:(56,(82,534,505,754)), 20:(57,(74,74,494,261)),
             21:(57,(74,533,494,752)), 22:(58,(80,74,506,288)),
             23:(58,(94,292,514,484)), 24:(59,(67,150,493,359)),
             25:(59,(80,536,474,747)), 26:(60,(104,337,457,545))}
    for figure, (page, box) in crops.items():
        doc[page-1].get_pixmap(matrix=pymupdf.Matrix(3,3), clip=pymupdf.Rect(box)).save(out / f'original_2-{figure}.png')
    doc[37].get_pixmap(matrix=pymupdf.Matrix(3,3), clip=pymupdf.Rect(117,158,467,598)).save(out / 'original_2-5.png')
    selected = pymupdf.open()
    # This is a verbatim evidence excerpt, not a newly authored PDF.
    selected.insert_pdf(doc, from_page=29, to_page=60)
    selected.save(out / '第二章_原文摘录.pdf')
    meta = {'source': str(SOURCE), 'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'pdf_pages': [30,61], 'printed_pages': [21,52], 'pages_total': len(doc)}
    (out / 'source_manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(meta, ensure_ascii=False))

if __name__ == '__main__':
    main()
