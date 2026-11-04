"""Physical drawing settings shared by exported footprints and the Web preview."""


def ref_svg_path():
    """Single-stroke preview glyphs; outlining a system font doubles its strokes."""
    glyphs={
        '#': [[(.3,0),(.1,1)],[(.9,0),(.7,1)],[(0,.35),(1,.35)],[(0,.65),(1,.65)]],
        'R': [[(0,1),(0,0),(.7,0),(1,.2),(.7,.5),(0,.5)],[(.5,.5),(1,1)]],
        'E': [[(1,0),(0,0),(0,1),(1,1)],[(0,.5),(.8,.5)]],
        'F': [[(0,1),(0,0),(1,0)],[(0,.5),(.8,.5)]],
        'D': [[(0,1),(0,0),(.6,0),(1,.25),(1,.75),(.6,1),(0,1)]],
        'S': [[(1,0),(0,0),(0,.5),(1,.5),(1,1),(0,1)]]}
    parts=[]
    for i,char in enumerate('#REFDES'):
        for points in glyphs[char]:
            parts.append(' '.join(('M' if n==0 else 'L')+f'{i*.56+x*.48-1.92:.4f},{y*.8-.4:.4f}'
                                  for n,(x,y) in enumerate(points)))
    return ' '.join(parts)


def center_annotations(spec):
    """Independent leaders keep coincident BGA and optical centers identifiable."""
    import math
    hx=spec['body'][0]/2
    result=[]
    for name,(x,y),side,dy,color in [
        ('BODY',(0,0),1,.55,'#9c6870'),
        ('BGA',spec['centers']['BGA'],-1,-.45,'#8472b1'),
        ('OPTICAL',spec['centers']['OPT'],1,-.65,'#ce8950')]:
        points=[(x,y),(x+side*.36,y+dy),(side*(hx+.28),y+dy)]
        dx1,dy1=points[1][0]-x,points[1][1]-y
        length=math.hypot(dx1,dy1)
        ux,uy=dx1/length,dy1/length
        segments=list(zip(points,points[1:]))
        for wing in (-1,1):
            segments.append(((x,y),(x+.10*ux+wing*.045*uy,y+.10*uy-wing*.045*ux)))
        result.append(dict(name=name,point=[x,y],color=color,
            label=[side*(hx+.4),round(y+dy+.06,4)],justify='right' if side<0 else 'left',
            text=f'{name} ({x:.3f}, {y:.3f}) mm',
            segments=[[[round(v,4) for v in p] for p in segment] for segment in segments]))
    return result


def presentation(spec):
    labels=[r+str(c) for r in spec['rows'] for c in range(1,spec['cols']+1)]
    length=max(map(len,labels),default=2)
    diameter=spec['pad_dia']
    return dict(revision=2,annotations=center_annotations(spec), pin=dict(width=round(diameter*.5/length,4),height=round(diameter*.45,4),
                    char_space=round(diameter*.025,4),stroke=round(diameter*.025,4)),
                ref=dict(width=.48,height=.8,char_space=.08,stroke=.15,svg_path=ref_svg_path()),
                center=dict(radius=.10,body_radius=.12,stroke=0,text_height=.18,text_width=.10),
                place_bound=dict(width=spec['body'][0]+2*spec['courtyard_excess'],
                    height=spec['body'][1]+2*spec['courtyard_excess'],
                    height_min=spec.get('height_min',0),height_max=spec.get('height_max')))
