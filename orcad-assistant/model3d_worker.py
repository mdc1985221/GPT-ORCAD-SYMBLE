"""Runs only inside the optional CadQuery environment (no Web dependencies)."""
import hashlib
import json
import math
import sys
from pathlib import Path
import cadquery as cq


def generate(folder):
    p=json.loads((folder/'input.json').read_text(encoding='utf8'))
    if p.get('kind')=='standard_smd':
        from standard_smd import generate as standard_generate
        return standard_generate(folder)
    if p.get('kind')=='polygon_smd':
        from polygon_model3d import generate as polygon_generate
        return polygon_generate(folder)
    w,h=p['body'];z=p['total_height'];stand=p['ball_height'];r=p['ball_dia']/2
    body=cq.Solid.makeBox(w,h,z-stand,cq.Vector(-w/2,-h/2,stand))
    shapes=[('BODY',body,[.20,.24,.31])]
    optical=p.get('optical')
    if optical:
        glass=optical['glass_thickness'];base_top=z-optical.get('top_to_wafer',glass)
        # Model optical surfaces as shallow inserts; internal die stack is not inferred.
        body=cq.Solid.makeBox(w,h,base_top-stand,cq.Vector(-w/2,-h/2,stand))
        dw,dh=optical['die_size'];sw,sh=optical['size'];cx,cy=optical['center'];depth=optical['appearance_depth']
        die=cq.Solid.makeBox(dw,dh,depth,cq.Vector(cx-dw/2,cy-dh/2,base_top-depth))
        sensor=cq.Solid.makeBox(sw,sh,depth,cq.Vector(cx-sw/2,cy-sh/2,base_top-depth))
        die=die.cut(sensor)
        body=body.cut(cq.Solid.makeBox(dw,dh,depth,cq.Vector(cx-dw/2,cy-dh/2,base_top-depth)))
        lid=cq.Solid.makeBox(w,h,glass,cq.Vector(-w/2,-h/2,z-glass))
        shapes=[('BODY',body,[.13,.15,.18]),('SENSOR_ARRAY',sensor,[.18,.24,.42]),('COVER_GLASS',lid,[.65,.82,.9])]
        if die.Volume()>1e-10:shapes.append(('DIE_SURFACE',die,[.35,.38,.42]))
        gap=z-glass-base_top
        if gap>1e-6:
            # The former full surround hid all perimeter artwork below glass.
            # With reviewed artwork, use only a narrow illustrative edge support;
            # its width is a display approximation, not a datasheet dimension.
            aperture_w,aperture_h=(w-.03,h-.03) if p.get('appearance_profile') else (dw,dh)
            frame=cq.Solid.makeBox(w,h,gap,cq.Vector(-w/2,-h/2,base_top)).cut(
                cq.Solid.makeBox(aperture_w,aperture_h,gap,
                    cq.Vector(-aperture_w/2 if p.get('appearance_profile') else cx-dw/2,
                              -aperture_h/2 if p.get('appearance_profile') else cy-dh/2,base_top)))
            shapes.append(('SPACER_APPROXIMATION',frame,[.25,.27,.29]))
        appearance=p.get('appearance_profile')
        if appearance:
            # All un-dimensioned details are named APPROX and kept inside the
            # dimensional envelope. No copper pads are added to the PCB model.
            inset=appearance.get('lower_edge_inset_fraction',0)*w
            if inset:
                body=(cq.Workplane('XY',origin=(0,0,stand)).rect(w-2*inset,h-2*inset)
                      .workplane(offset=base_top-stand).rect(w,h).loft(combine=True).val())
                body=body.cut(cq.Solid.makeBox(dw,dh,depth,cq.Vector(cx-dw/2,cy-dh/2,base_top-depth)))
            def xy(u,v):return ((u-.5)*w,(.5-v)*h)
            inserts=[]
            for index,rect in enumerate(appearance.get('edge_features',[]),1):
                x0,y1=xy(rect[0],rect[1]);x1,y0=xy(rect[2],rect[3])
                tile=cq.Solid.makeBox(x1-x0,y1-y0,depth,cq.Vector(x0,y0,base_top-depth))
                inserts.append((f'EDGE_FEATURE_APPROX_{index:02d}',tile,[.76,.64,.38]))
            for index,rect in enumerate(appearance.get('perimeter_frames',[]),1):
                x0,y1=xy(rect[0],rect[1]);x1,y0=xy(rect[2],rect[3]);line=.006
                outer=cq.Solid.makeBox(x1-x0,y1-y0,depth,cq.Vector(x0,y0,base_top-depth))
                inner=cq.Solid.makeBox(x1-x0-2*line,y1-y0-2*line,depth,cq.Vector(x0+line,y0+line,base_top-depth))
                inserts.append((f'PERIMETER_FRAME_APPROX_{index}',outer.cut(inner),[.55,.61,.69]))
            if appearance.get('back_marker'):
                triangle=[xy(*v) for v in appearance['back_marker']]
                mark=cq.Workplane('XY',origin=(0,0,stand)).polyline(triangle).close().extrude(depth).val()
                inserts.append(('BACK_DIRECTION_MARK_APPROX',mark,[.45,.67,.24]))
            # Shallow material inserts preserve Z, and do not create overlapping
            # solids in the saved assembly.
            # Apply disjoint shallow cuts individually: OCCT compound cuts can
            # create invalid coplanar faces with closely spaced raster details.
            for label,insert,_ in inserts:
                body=body.cut(insert).clean()
                if not body.isValid():raise ValueError('Appearance cut topology failed: '+label)
            shapes[0]=('BODY',body,[.13,.15,.18])
            shapes.extend(inserts)
    for pin,x,y in p['pads']:
        sphere=cq.Solid.makeSphere(r,cq.Vector(x,y,r),angleDegrees1=-90,angleDegrees2=90)
        clip=cq.Solid.makeBox(2*r+.02,2*r+.02,stand,cq.Vector(x-r-.01,y-r-.01,0))
        ball=sphere.intersect(clip)
        if not ball.isValid():raise ValueError('Invalid ball '+pin)
        shapes.append((pin,ball,[.76,.79,.84]))
    name=p['name']+'.step';target=folder/name
    assembly=cq.Assembly(name=p['name'])
    for label,shape,color in shapes:assembly.add(shape,name=label,color=cq.Color(*color,.18 if label=='COVER_GLASS' else 1))
    assembly.export(str(target),exportType='STEP')
    loaded=cq.importers.importStep(str(target)).val()
    solids=loaded.Solids()
    if len(solids)!=len(shapes) or not loaded.isValid():raise ValueError(f'STEP solid count or topology mismatch: expected {len(shapes)}, read {len(solids)}, valid {loaded.isValid()}; source '+str([(label,len(shape.Solids()),shape.isValid()) for label,shape,_ in shapes if len(shape.Solids())!=1 or not shape.isValid()]))
    bb=loaded.BoundingBox()
    expected=(-w/2,-h/2,0,w/2,h/2,z)
    actual=(bb.xmin,bb.ymin,bb.zmin,bb.xmax,bb.ymax,bb.zmax)
    if any(abs(a-b)>1e-5 for a,b in zip(actual,expected)):raise ValueError('STEP envelope mismatch')
    # Match balls by centers, independent of STEP entity order.
    remaining=[s for s in solids if s.BoundingBox().zmax<=stand+1e-6]
    if len(remaining)!=len(p['pads']):raise ValueError('Ball count mismatch')
    expected_volume=sum(shape.Volume() for _,shape,_ in shapes)
    if abs(sum(s.Volume() for s in solids)-expected_volume)>1e-5:raise ValueError('Assembly volume mismatch')
    # Independent geometric readback also covers every small appearance insert.
    def bounds(shape):
        b=shape.BoundingBox();return (b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax)
    unmatched=list(solids)
    for label,shape,_ in shapes:
        target_box=bounds(shape)
        candidates=[s for s in unmatched if max(abs(a-b) for a,b in zip(bounds(s),target_box))<1e-5
                    and abs(s.Volume()-shape.Volume())<1e-6]
        if len(candidates)!=1:raise ValueError('Detail solid readback mismatch '+label)
        unmatched.remove(candidates[0])
    if optical:
        sw,sh=optical['size'];cx,cy=optical['center']
        matching=[s for s in solids if abs(s.BoundingBox().xlen-sw)<1e-5 and abs(s.BoundingBox().ylen-sh)<1e-5]
        if len(matching)!=1 or max(abs(matching[0].Center().x-cx),abs(matching[0].Center().y-cy))>1e-5:
            raise ValueError('Sensor area readback mismatch')
        covers=[s for s in solids if abs(s.BoundingBox().zmax-z)<1e-5 and abs(s.BoundingBox().zlen-optical['glass_thickness'])<1e-5]
        if len(covers)!=1:raise ValueError('Cover glass thickness readback mismatch')
        if abs(matching[0].BoundingBox().zmax-(z-optical.get('top_to_wafer',optical['glass_thickness'])))>1e-5:
            raise ValueError('Sensor plane depth readback mismatch')
    cap_volume=math.pi*stand**2*(r-stand/3)
    cap_diameter=2*r if stand>=r else 2*math.sqrt(2*r*stand-stand**2)
    for pin,x,y in p['pads']:
        ball=min(remaining,key=lambda s:(s.Center().x-x)**2+(s.Center().y-y)**2)
        center=ball.Center();b=ball.BoundingBox()
        if max(abs(center.x-x),abs(center.y-y),abs(b.zmin),abs(b.zmax-stand),abs(b.xlen-cap_diameter),abs(b.ylen-cap_diameter),abs(ball.Volume()-cap_volume))>1e-5:
            raise ValueError('Ball readback mismatch '+pin)
        remaining.remove(ball)
    report=dict(status='PASS',revision=1,step=name,plan=p,units='mm',solids=len(solids),balls=len(p['pads']),
        bounds=list(actual),checks=['STEP reimport topology','mm envelope and Z=0','per-ball XY/Z/diameter/volume','assembly volume']+
        (['sensor area XY and center','cover glass thickness'] if optical else [])+
        ['each solid bounding box and volume after STEP reimport'])
    report['appearance_features']=len([label for label,_,_ in shapes if 'APPROX' in label])
    files=[target,folder/'mesh.json']
    if optical:
        inspection=cq.Assembly(name=p['name']+'_INSPECTION_NO_GLASS')
        visible=[(label,shape,color) for label,shape,color in shapes if label!='COVER_GLASS']
        for label,shape,color in visible:inspection.add(shape,name=label,color=cq.Color(*color))
        inspection_path=folder/(p['name']+'_INSPECTION_NO_GLASS.step')
        inspection.export(str(inspection_path),exportType='STEP')
        imported=cq.importers.importStep(str(inspection_path)).val()
        if not imported.isValid() or len(imported.Solids())!=len(visible):raise ValueError('Inspection STEP topology mismatch')
        rest=list(imported.Solids())
        for label,shape,_ in visible:
            found=[s for s in rest if max(abs(a-b) for a,b in zip(bounds(s),bounds(shape)))<1e-5 and abs(s.Volume()-shape.Volume())<1e-6]
            if len(found)!=1:raise ValueError('Inspection STEP readback mismatch '+label)
            rest.remove(found[0])
        files.append(inspection_path)
        report['inspection']=dict(step=inspection_path.name,status='PASS',solids=len(visible),removed=['COVER_GLASS'],
            purpose='Visual inspection only; glass omitted. Use complete STEP for assembly height and collisions.')
        report['display_limitation']='Some CAD importers ignore STEP transparency. Hide COVER_GLASS or set its transparency to 82%; inspection STEP omits it. Web studio materials are preview only.'
    meshes=[]
    for label,shape,color in shapes:
        vertices,triangles=shape.tessellate(.025,.25)
        meshes.append(dict(name=label,color=color,opacity=.18 if label=='COVER_GLASS' else 1,vertices=[[v.x,v.y,v.z] for v in vertices],triangles=triangles))
    (folder/'mesh.json').write_text(json.dumps(dict(bounds=actual,meshes=meshes,
        appearance_notice=p.get('appearance_profile',{}).get('notice',''),
        optical=optical)),encoding='utf8')
    report['file_hashes']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    (folder/'model3d.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':generate(Path(sys.argv[1]).resolve())
