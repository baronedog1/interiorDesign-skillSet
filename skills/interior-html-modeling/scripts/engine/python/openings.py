"""Compile source opening facts once into wall-local panels shared by HTML and cameras.
Missing historical choices are explicit preview defaults, never surveyed facts.
"""
import math

def resolve_openings(layout):
    result={}
    for o in layout['openings']:
        kind=o['type']; moving=kind in ('door','sliding-door')
        fraction=float(o.get('openFraction',0)) if moving else 0.
        infill=o.get('infill','solid' if kind=='door' else 'clear-glass')
        c=o['offset']+o['width']/2; w=o['width'];h=o['height'];panels=[]
        def panel(x,width,yaw=0,z=0):
            panels.append(dict(center=[x,o['sill']+h/2,z],size=[width,h-.035,.044 if infill=='solid' else .014],yaw=yaw,infill=infill))
        if kind=='door':
            right=o.get('hingeSide','left')=='right'; side=-1 if right else 1
            angle=float(o.get('swingSign',1))*side*math.pi/2*fraction
            hinge=c+(-side)*w/2
            panel(hinge+side*math.cos(angle)*w/2,w-.035,angle,-side*math.sin(angle)*w/2)
        elif kind=='sliding-door':
            # Two-track/two-leaf slider: fraction=1 opens half the aperture, not all of it.
            toward=-1 if o.get('slideTo','left')=='left' else 1
            panel(c+toward*w/4,w/2,0,-.022)
            panel(c-toward*w/4+toward*w/2*fraction,w/2,0,.022)
        elif kind in ('window','fixed-glazing'):
            count=max(2,round(w/.95))
            for i in range(count):panel(c-w/2+(i+.5)*w/count,w/count-.025)
        result[o['id']]={**o,'openFraction':fraction,'infill':infill,'state':'open' if kind=='passage' else 'closed' if fraction==0 else 'maximum-open' if fraction==1 else 'part-open','panels':panels,'seeThrough':kind=='passage' or infill=='clear-glass' or fraction>0,'sourceStatus':'explicit' if not moving or 'openFraction' in o else 'preview-default-closed-not-confirmed','clearOpeningFraction':1 if kind=='passage' else fraction/2 if kind=='sliding-door' else None,'exteriorView':o.get('exteriorView',{'kind':'unknown','description':'外部目标未确认，不能擅自当作户外实景或另一间房'})}
    return result
