# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Export the read-only research interface for free static hosting."""
from pathlib import Path
from shutil import copyfile

ROOT = Path(__file__).resolve().parent.parent
FILES = ('current_snapshot.json', 'research_cache.json', 'holdings_cache.json',
         'scenarios.json', 'winner_max_sharpe.json', 'walk_forward.json')


def export():
    site = ROOT / 'site'
    data = site / 'data'
    data.mkdir(parents=True, exist_ok=True)
    html = (ROOT / 'dashboard/explorer.html').read_text(encoding='utf-8')
    html = html.replace('/explore/logo.svg', '/logo.svg')
    html = html.replace('/explore/styles.css', '/styles.css')
    html = html.replace('/explore/app.js?v=4', '/app.js?v=4')
    html = html.replace('href="/explore"', 'href="/"')
    html = html.replace('<script src="/app.js?v=4" defer></script>',
                        '<script>window.ALPHEDGE_STATIC=true</script><script src="/app.js?v=4" defer></script>')
    (site / 'index.html').write_text(html, encoding='utf-8')
    for source, target in [('dashboard/explorer.js','app.js'),
                           ('dashboard/explorer.css','styles.css'),
                           ('dashboard/logo.svg','logo.svg')]:
        copyfile(ROOT / source, site / target)
    for name in FILES:
        copyfile(ROOT / 'state' / name, data / name)
    print(f'Exported static site with {len(FILES)} fallback data files')

if __name__ == '__main__':
    export()
