import importlib.util
from pathlib import Path
import json
import tempfile
import unittest
from PIL import Image

spec=importlib.util.spec_from_file_location('og',Path(__file__).parents[1]/'gen_og.py')
og=importlib.util.module_from_spec(spec);spec.loader.exec_module(og)

class ShareCardTests(unittest.TestCase):
    def test_card_uses_current_catalog_count_and_canonical_identity(self):
        data=json.loads((og.ROOT/'data.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'card.png';receipt=og.render(data,out)
            with Image.open(out) as image:
                self.assertEqual(image.size,(1200,630))
                self.assertEqual(receipt['count'],len(data[og.CARDS[og.SITE]['key']]))
                self.assertEqual(image.info['CanonicalURL'],'https://'+og.CARDS[og.SITE]['host']+'/')
                self.assertNotIn('vercel.app',json.dumps(image.info))
                self.assertNotRegex(json.dumps(image.info),r'built.*agent|by an agent|generator|token|endpoint')
    def test_empty_catalog_fails_without_replacing_previous_card(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'card.png';out.write_bytes(b'previous')
            with self.assertRaises(ValueError):og.render({},out)
            self.assertEqual(out.read_bytes(),b'previous')

if __name__=='__main__':unittest.main()
