#!/usr/bin/env python3
"""Bake results.json into a standalone page: python3 build_page.py [results.json] [out.html]"""
import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
res = Path(sys.argv[1] if len(sys.argv) > 1 else here / 'results.json')
out = Path(sys.argv[2] if len(sys.argv) > 2 else here / 'compiler-probes.html')
data = json.loads(res.read_text(encoding='utf-8'))
data['baked'] = True   # tells the page this is a local run, not the bundled cloud sample
j = json.dumps(data, separators=(',', ':')).replace('</', '<\\/')
page = (here / 'page' / 'template.html').read_text(encoding='utf-8').replace('__RESULTS__', j)
# the template is a fragment; a standalone file needs its own doctype and charset
head = '<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
out.write_text(head + page, encoding='utf-8')
print('wrote', out)
