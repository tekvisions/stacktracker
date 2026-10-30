import importlib.util
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('deployment',Path(__file__).parents[1]/'deploy.py')
deployment=importlib.util.module_from_spec(spec);spec.loader.exec_module(deployment)
class PrivateBuildInventoryTests(unittest.TestCase):
    def test_build_fonts_and_virtualenv_are_never_uploaded(self):
        calls=[]
        def request(url,data=None,headers=None,method=None):
            calls.append((url,data))
            return (201,json.dumps({'url':'fixture.invalid','readyState':'READY'}).encode()) if '/deployments' in url else (200,b'')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'index.html').write_text('public fixture')
            for name in ['.build-assets','.og-venv','.venv']:
                (root/name).mkdir();(root/name/'private.json').write_text('private fixture')
            with patch.object(deployment,'ROOT',folder),patch.object(deployment,'TOKEN','fixture'),patch.object(deployment,'_preflight_overwrite_guard'),patch.object(deployment,'req',side_effect=request):
                self.assertEqual(deployment.main(),0)
            payload=json.loads(calls[-1][1]);self.assertEqual([x['file'] for x in payload['files']],['index.html'])
            self.assertEqual(len(calls),2)
if __name__=='__main__':unittest.main()
