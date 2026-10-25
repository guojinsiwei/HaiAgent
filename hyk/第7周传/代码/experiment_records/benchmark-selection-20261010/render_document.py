from pathlib import Path
import importlib.util
import os

ROOT = Path(__file__).resolve().parent
SKILL = Path('C:/Users/54177/.codex/plugins/cache/openai-primary-runtime/documents/26.1007.11041/skills/documents')
spec = importlib.util.spec_from_file_location('packaged_docx_renderer', SKILL / 'render_docx.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
qa = ROOT / 'qa2'
pdf = qa / 'word-layout-check.pdf'
assert pdf.exists() and pdf.stat().st_size > 0
poppler = 'C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
os.environ['PATH'] = poppler + os.pathsep + os.environ.get('PATH', '')
renderer.convert_to_pdf = lambda *args, **kwargs: (str(pdf), 'Native Word read-only PDF export; bundled LibreOffice unavailable on Windows')
renderer.rasterize(str(ROOT / '长程Agent基准筛选简表.docx'), str(qa), 140, verbose=False, emit_pdf=False)
print([p.name for p in qa.glob('page-*.png')])
