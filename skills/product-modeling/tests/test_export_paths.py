import tempfile,unittest,json,sys
from pathlib import Path
import trimesh
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from build_product import build
class ExportPaths(unittest.TestCase):
 def test_nested_resource_survives_export(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'assets').mkdir();(r/'assets/model.glb').write_bytes(trimesh.creation.box().export(file_type='glb'))
   p=r/'p.product.json';p.write_text(json.dumps({'format':'product-modeling','schemaVersion':1,'id':'nested-test','name':'嵌套资源','mode':'mesh','model':'assets/model.glb','assemblies':[],'parts':[],'materials':{},'source':{'notes':[]}}))
   build(p,r/'out');data=json.loads((r/'out/p.product.json').read_text());self.assertTrue((r/'out'/data['model']).is_file());self.assertIn('assets/model.glb',json.loads((r/'out/PRODUCT_MANIFEST.json').read_text())['files'])
