"""A tracked repo that re-enters keeps its generated page over a retained reference."""
import json
from pathlib import Path
import tempfile
import unittest

import gen_details
import url_lifecycle

ROOT = Path(url_lifecycle.__file__).resolve().parent
REAL = json.loads((ROOT / 'url.lifecycle').read_text())


class RepoReentryTests(unittest.TestCase):
    def test_tracked_repo_owns_its_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slug = gen_details.slugify('Acme', 'Widget.js')
            url = 'https://' + REAL['host'] + '/p/' + slug + '/'
            entry = {'slug': slug, 'entity': 'Acme/Widget.js', 'canonical_url': url, 'repository': 'https://github.com/Acme/Widget.js',
                     'summary': 'Fixture.', 'selection_context': 'Fixture.', 'limitations': 'Fixture.',
                     'last_catalog_snapshot': '2026-11-24T08:00:00-08:00', 'reviewed_on': '2026-11-25',
                     'primary_sources': [{'url': 'https://github.com/Acme/Widget.js', 'title': 'Publisher README'}]}
            (root / 'url.lifecycle').write_text(json.dumps({'host': REAL['host'], 'captured_public_urls': [url], 'retained_references': [entry]}))
            (root / 'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>' + url + '</loc></url></urlset>')
            page = root / 'p' / slug / 'index.html'
            page.parent.mkdir(parents=True)
            page.write_text('generated tracked page')
            (root / 'data.json').write_text(json.dumps({'repos': [{'owner': 'Acme', 'name': 'Widget.js'}]}))
            self.assertEqual(url_lifecycle.render_retained(root), 0)
            self.assertEqual(page.read_text(), 'generated tracked page')
            (root / 'data.json').write_text(json.dumps({'repos': []}))
            self.assertEqual(url_lifecycle.render_retained(root), 1)
            self.assertIn('outside the current ranked discovery snapshot', page.read_text())


if __name__ == '__main__':
    unittest.main()
