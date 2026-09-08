import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from openings import resolve_openings
from cameras import Occluders,front_view

class SourceRules(unittest.TestCase):
 def opening(self,**kw):return dict(id='door',wallId='w',type='door',offset=1,width=1,sill=0,height=2.1,**kw)
 def state(self,o):return resolve_openings({'openings':[o]})['door']
 def test_closed_door(self):
  p=self.state(self.opening(openFraction=0))['panels'][0];self.assertEqual(p['yaw'],0);self.assertAlmostEqual(p['center'][0],1.5)
 def test_left_open(self):
  p=self.state(self.opening(openFraction=1))['panels'][0];self.assertAlmostEqual(p['center'][0],1);self.assertAlmostEqual(p['center'][2],-.5)
 def test_right_open(self):
  p=self.state(self.opening(openFraction=1,hingeSide='right'))['panels'][0];self.assertAlmostEqual(p['center'][0],2);self.assertAlmostEqual(p['center'][2],-.5)
 def test_reverse_swing(self):
  p=self.state(self.opening(openFraction=1,swingSign=-1))['panels'][0];self.assertAlmostEqual(p['center'][2],.5)
 def test_slider_max_half_open(self):
  o=self.opening(openFraction=1);o['type']='sliding-door';s=self.state(o);self.assertEqual(s['clearOpeningFraction'],.5);self.assertEqual(s['panels'][0]['center'][0],s['panels'][1]['center'][0])
 def test_closed_clear_glass(self):self.assertTrue(self.state(self.opening(openFraction=0,infill='clear-glass'))['seeThrough'])
 def test_closed_frosted_glass(self):self.assertFalse(self.state(self.opening(openFraction=0,infill='frosted-glass'))['seeThrough'])
 def test_unknown_is_not_outdoor(self):
  s=self.state(self.opening());self.assertEqual(s['exteriorView']['kind'],'unknown');self.assertIn('not-confirmed',s['sourceStatus'])
 def test_aperture_no_panel(self):
  o=self.opening();o['type']='passage';self.assertEqual(self.state(o)['panels'],[])
 def test_occluder_same_compiled_pose(self):
  o=self.opening(openFraction=1);layout={'walls':[dict(id='w',a=[0,0],b=[4,0],height=2.7,thickness=.1)],'placements':[],'openings':[o]};obs=Occluders(layout);i=list(obs.ids).index('door');self.assertAlmostEqual(obs.centres[i][0],1);self.assertAlmostEqual(obs.centres[i][2],-.5)
 def test_primary_has_room_surfaces(self):
  room=dict(id='r',name='Room',type='living',polygon=[[0,0],[4,0],[4,4],[0,4]],subjectIds=['sofa'])
  walls=[dict(id='w'+str(i),a=a,b=b,height=2.7,thickness=.1)for i,(a,b)in enumerate(zip(room['polygon'],room['polygon'][1:]+room['polygon'][:1]))]
  layout={'rooms':[room],'floor':{'height':2.7},'walls':walls,'openings':[],'openConnections':[],'placements':[dict(id='sofa',roomId='r',componentId='sofa.straight',position=[2,0,.6],rotationY=0,size=[2,.8,.8])]}
  shot=front_view(layout,room,{'width':1280,'height':960});self.assertEqual(shot['visibility']['doorStateMode'],'source');self.assertTrue(shot['metrics']['ceilingAndFloorAnchors']);self.assertGreater(shot['metrics']['surfaceConstruction']['floor'],0);self.assertGreater(shot['metrics']['surfaceConstruction']['ceiling'],0)
 def test_near_plane_ignores_only_foreground(self):
  layout={'walls':[dict(id='front',a=[-2,1],b=[2,1],height=3,thickness=.1),dict(id='back',a=[-2,4],b=[2,4],height=3,thickness=.1)],'placements':[],'openings':[]}
  normal=Occluders(layout);clip=normal.with_near_plane([0,1,0],[0,0,1],1.2)
  self.assertLess(normal.rays([0,1,0],[[0,0,1]])[0],1.1);self.assertGreater(clip.rays([0,1,0],[[0,0,1]])[0],3.8)
 def test_narrow_bed_uses_whole_subject_retreat(self):
  room=dict(id='r',name='Bedroom',type='bedroom',polygon=[[0,0],[2.8,0],[2.8,2.6],[0,2.6]],subjectIds=['bed'])
  walls=[dict(id='w'+str(i),a=a,b=b,height=2.7,thickness=.1)for i,(a,b)in enumerate(zip(room['polygon'],room['polygon'][1:]+room['polygon'][:1]))]
  layout={'rooms':[room],'floor':{'height':2.7},'walls':walls,'openings':[],'openConnections':[],'placements':[dict(id='bed',roomId='r',componentId='bed.upholstered',position=[1.4,0,1.1],rotationY=0,size=[1.8,1.05,2.1])]}
  shot=front_view(layout,room,{'width':1280,'height':960});self.assertTrue(shot['metrics']['fullSubjectProjection']['complete']);self.assertTrue(shot['metrics']['virtualRetreat']);self.assertGreater(shot['near'],.1);self.assertEqual(shot['metrics']['frontAngleDegrees'],0)
if __name__=='__main__':unittest.main()
