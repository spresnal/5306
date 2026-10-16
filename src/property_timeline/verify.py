"""Run offline Python, Node, browser, and optional existing-PDF verification."""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


def browser_path():
    candidates = [shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser', 'msedge')]
    for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        base = Path(os.environ.get(variable, 'C:/Program Files'))
        candidates.extend([base / 'Google/Chrome/Application/chrome.exe', base / 'Microsoft/Edge/Application/msedge.exe'])
    return next((str(path) for path in candidates if path and Path(path).is_file()), None)


def run_command(command, root, timeout=120):
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout)
    if result.returncode:
        print(result.stdout + result.stderr, file=sys.stderr)
    return result.returncode == 0


def checked(action):
    try:
        return 'passed' if action() else 'failed'
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print('Verification component failed: ' + str(exc), file=sys.stderr)
        return 'failed'


def browser_check(root, browser):
    spec = importlib.util.spec_from_file_location('timeline_browser_fixture', root / 'tests/browser_fixture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='timeline-browser-test-') as directory:
        folder = Path(directory)
        fixture = module.build(folder)
        command = [browser, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                   '--no-pdf-header-footer', '--user-data-dir=' + str(folder / 'profile'),
                   '--virtual-time-budget=10000', '--dump-dom', fixture.as_uri()]
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            command.insert(1, '--no-sandbox')
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=60)
        match = re.search(r'<pre id="browser-test-result">([^<]*)</pre>', result.stdout)
        if result.returncode or not match or match[1] != 'PASS':
            print('Browser fixture: ' + (match[1] if match else 'did not complete'), file=sys.stderr)
            return False
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--strict', action='store_true', help='Fail if required PDF, Node, or browser checks are unavailable')
    parser.add_argument('--browser', help='Chrome/Edge/Chromium executable override')
    parser.add_argument('--pdf', type=Path, metavar='HTML', help='Also verify the existing PDF beside this HTML; no regeneration')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / 'tests').is_dir():
        parser.error('Test sources unavailable; set --root to a repository checkout')
    sys.path.insert(0, str(root))
    # Test subprocesses change directories; preserve an absolute import path.
    os.environ['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent) + os.pathsep + os.environ.get('PYTHONPATH', '')
    checks = {}
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), top_level_dir=str(root))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    checks['python'] = 'passed' if result.wasSuccessful() else 'failed'
    for test, reason in result.skipped:
        print(f'SKIPPED {test.id()}: {reason}')
    pdf_available = all(importlib.util.find_spec(name) is not None for name in ('pymupdf', 'PIL'))
    pdf_skips = any('test_pdf_integration' in test.id() or 'test_document_extraction' in test.id()
                    for test, _ in result.skipped)
    checks['pdf_fixtures'] = 'passed' if pdf_available and not pdf_skips else 'unavailable'
    node = shutil.which('node')
    checks['javascript'] = checked(lambda: run_command([node, str(root / 'tests/review_viewer_test.cjs'),
                            str(root / 'src/property_timeline/resources/review_viewer.js')], root)) if node else 'unavailable'
    browser = args.browser or browser_path()
    checks['browser'] = checked(lambda: browser_check(root, browser)) if browser else 'unavailable'
    if args.pdf:
        checks['existing_pdf'] = checked(lambda: run_command([sys.executable, '-m', 'property_timeline.export_timeline_pdf',
                                  str(args.pdf.resolve()), '--verify-only'], root)) if pdf_available else 'unavailable'
    for name, state in checks.items():
        print(f'{name}: {state}')
    return int(any(state == 'failed' or (args.strict and state == 'unavailable') for state in checks.values()))


if __name__ == '__main__':
    raise SystemExit(main())
