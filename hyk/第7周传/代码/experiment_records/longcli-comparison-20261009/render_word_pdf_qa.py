"""Use the packaged DOCX renderer's raster stage with a native Word PDF on Windows."""
from pathlib import Path
import importlib.util
import os
import argparse

ROOT = Path(__file__).resolve().parent
SKILL = Path('C:/Users/54177/.codex/plugins/cache/openai-primary-runtime/documents/26.1007.11041/skills/documents')
spec = importlib.util.spec_from_file_location('packaged_docx_renderer', SKILL/'render_docx.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
parser=argparse.ArgumentParser()
parser.add_argument('--document-name',default='LongCLIBench实验汇总_可编辑.docx')
parser.add_argument('--qa-name',default='docx-qa')
args=parser.parse_args()
assert Path(args.document_name).name==args.document_name and Path(args.qa_name).name==args.qa_name
qa=ROOT/args.qa_name
pdf = qa/'word-layout-check.pdf'
assert pdf.exists() and pdf.stat().st_size > 0
poppler = 'C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
os.environ['PATH'] = poppler + os.pathsep + os.environ.get('PATH', '')
renderer.convert_to_pdf = lambda *args, **kwargs: (str(pdf), 'Native Word read-only PDF export; no LibreOffice available in selected Windows runtime')
renderer.rasterize(str(ROOT/args.document_name), str(qa), 140, verbose=False, emit_pdf=False)
print('Rendered page images:', [p.name for p in qa.glob('page-*.png')])
