"""Render all pages and verify numerical, preservation and layout assertions."""
from pathlib import Path
import json
import hashlib
import pymupdf
from PIL import Image, ImageDraw

OUT=Path(__file__).resolve().parent
REPO=OUT.parents[3]
data=json.loads((OUT/'figure_data_and_validation.json').read_text(encoding='utf8'))
pdf=Path(data['pdf'])
doc=pymupdf.open(pdf)
renders=OUT/'renders'
renders.mkdir(exist_ok=True)
checks=[]
thumbnails=[]
assert len(doc)==len(data['pages'])
assert all(r['status']=='PASS' for r in data['validation'])
for key,value in data['source_protection']['input_sha256'].items():
    assert hashlib.sha256((REPO/key).read_bytes()).hexdigest()==value,key
reference=Path(data['source_protection']['reference'])/'ATT_S1_S2_S3_Comprehensive_Report.html'
assert hashlib.sha256(reference.read_bytes()).hexdigest()==data['source_protection']['reference_html_sha256']
for i,page in enumerate(doc):
    pix=page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5))
    dest=renders/f'page_{i+1:02}.png'
    pix.save(dest)
    blocks=page.get_text('dict')['blocks']
    spans=[s for b in blocks if 'lines' in b for line in b['lines'] for s in line['spans']]
    outside=[s['text'] for s in spans if not page.rect.contains(pymupdf.Rect(s['bbox']))]
    assert not outside, (i+1,outside)
    # Main-page text must remain above the footer rule. Exact PDF text boxes
    # are checked in addition to the manual review of every rasterized page.
    intrusion=[s['text'] for s in spans if s['bbox'][1]<page.rect.height*.929
        and s['bbox'][3]>page.rect.height*.931]
    assert not intrusion,(i+1,'footer overlap',intrusion)
    drawings=len(page.get_drawings())
    assert drawings>0
    checks.append(dict(page=i+1,title=data['pages'][i],out_of_bounds_text=outside,
        text_spans=len(spans),vector_drawings=drawings,embedded_raster_images=len(page.get_images()),
        links=len(page.get_links())))
    im=Image.open(dest).convert('RGB')
    im.thumbnail((936,612))
    canvas=Image.new('RGB',(960,650),'#dbe0e4')
    canvas.paste(im,((960-im.width)//2,24))
    ImageDraw.Draw(canvas).text((12,5),f'PAGE {i+1}',fill='black')
    thumbnails.append(canvas)
for start in range(0,len(thumbnails),4):
    contact=Image.new('RGB',(1920,1300),'white')
    for j,im in enumerate(thumbnails[start:start+4]):
        contact.paste(im,((j%2)*960,(j//2)*650))
    contact.save(renders/f'contact_{start//4+1:02}.png')
result=dict(status='PASS',pages=len(doc),numerical_checks=len(data['validation']),
    source_and_reference_protection='PASS',pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),pages_detail=checks)
(OUT/'render_checks.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
