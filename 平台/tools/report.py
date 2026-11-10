from pathlib import Path
import runpy
HERE=Path(__file__).resolve().parent
runpy.run_path(str(HERE/'plot_results.py'),run_name='__main__')
runpy.run_path(str(HERE/'report_document.py'),run_name='__main__')
