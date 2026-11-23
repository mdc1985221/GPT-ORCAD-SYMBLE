"""Appearance references from reviewed PDF vector art; never dimensional evidence."""
import math


def sc8238_reference(path):
    import fitz
    with fitz.open(path) as doc:
        candidates=[(i,p) for i,p in enumerate(doc,1) if 'Pixel center' in p.get_text() and 'Top View' in p.get_text()]
        if len(candidates)!=1:return None
        number,page=candidates[0];drawings=page.get_drawings()
    # Reviewed V0.8 p44 top/back view envelopes. Refuse unrelated artwork.
    top=(146.912003,245.664993,279.614014,350.053986)
    back=(330.377991,245.664993,463.101990,350.053986)
    if not any(max(abs(a-b) for a,b in zip(d['rect'],top))<.01 for d in drawings):return None
    def uv(x,y,box=top):return [(x-box[0])/(box[2]-box[0]),(y-box[1])/(box[3]-box[1])]
    features=[]
    for d in drawings:
        r=d['rect']
        if (d['color']==(1.,0.,1.) and len(d['items'])==1 and d['items'][0][0]=='qu'
            and top[0]<r.x0<r.x1<top[2] and top[1]<r.y0<r.y1<top[3]
            and r.width<2 and r.height<2):
            features.append([*uv(r.x0,r.y0),*uv(r.x1,r.y1)])
    features=sorted({tuple(round(v,8) for v in f) for f in features},key=lambda f:(f[1],f[0]))
    if len(features)!=48:return None
    # Solid green triangle belongs to the BACK view. The dashed top-view
    # representation is hidden geometry; do not add a second front mark.
    triangle=next((d for d in drawings if d['color']==(0.,1.,0.) and back[0]<d['rect'].x0<back[2]
                   and back[1]<d['rect'].y0<back[3] and len(d['items'])==3),None)
    if triangle is None:return None
    points=[]
    for item in triangle['items']:
        x,y=item[1];u,v=uv(x,y,back);points.append([1-u,v])
    frames=[]
    for d in drawings:
        r=d['rect']
        if d['color']==(0.,1.,1.) and r.width>120 and r.height>90 and top[0]<r.x0<r.x1<top[2]:
            frames.append([*uv(r.x0,r.y0),*uv(r.x1,r.y1)])
    return dict(revision=1,source_page=number,source='SC8238 V0.8 mechanical drawing; reviewed top/back vector artwork',
        accuracy='appearance_only',dimensions='un dimensioned drawing proportions; not manufacturer dimensions',
        edge_features=[list(f) for f in features],perimeter_frames=frames,back_marker=points,
        lower_edge_inset_fraction=.022,lower_edge_note='Undimensioned side-view slope; appearance approximation',
        notice='边缘小方块、细框及背面三角来自 p44 图示，无尺寸，大小/材质/深度为外观近似；不作为焊盘或装配尺寸依据。')


def gc5613_reference(path):
    """Reviewed raster drawing signature; proportions only, never dimensions."""
    import fitz
    from PIL import Image
    import io
    with fitz.open(path) as doc:
        candidates=[(i,p) for i,p in enumerate(doc,1) if 'Top View Image Size' in p.get_text() and 'Bottom View BGA Size' in p.get_text()]
        if len(candidates)!=1:return None
        number,page=candidates[0]
        images={}
        for info in page.get_images():
            im=Image.open(io.BytesIO(doc.extract_image(info[0])['image'])).convert('RGB')
            images[im.size]=im
    im=images.get((1168,719))
    if im is None or (835,537) not in images:return None
    # Cyan square outlines in the actual top-view raster. Bounding boxes are
    # display proportions; dimensions all come separately from table 7.
    px=im.load();points={(x,y) for y in range(125,692) for x in range(156,1110)
        if px[x,y][0]<160 and px[x,y][1]>160 and px[x,y][2]>180}
    boxes=[]
    while points:
        seed=points.pop();stack=[seed];component=[seed]
        while stack:
            x,y=stack.pop()
            for q in ((x+dx,y+dy) for dx in range(-2,3) for dy in range(-2,3) if dx or dy):
                if q in points:points.remove(q);stack.append(q);component.append(q)
        xs,ys=zip(*component);box=(min(xs),min(ys),max(xs)+1,max(ys)+1)
        if 5<=box[2]-box[0]<=18 and 5<=box[3]-box[1]<=18:boxes.append(box)
    if len(boxes)!=45:return None
    top=(155,119,1110,695)
    def uv(x,y,box=top):return [(x-box[0])/(box[2]-box[0]),(y-box[1])/(box[3]-box[1])]
    features=[[*uv(b[0],b[1]),*uv(b[2],b[3])] for b in sorted(boxes,key=lambda b:(b[1],b[0]))]
    # Bottom-view solid green triangle; reflect to top-view XY convention.
    back=(92,90,747,485)
    marker=[[1-uv(x,y,back)[0],uv(x,y,back)[1]] for x,y in [(500,159),(525,159),(525,183)]]
    return dict(revision=1,source_page=number,source='GC5613-C43YA V1.1 p12 reviewed raster top/back/side drawing',
        accuracy='appearance_only',dimensions='undimensioned drawing proportions, not manufacturer dimensions',
        edge_features=features,perimeter_frames=[[.004,.004,.996,.996]],back_marker=marker,
        lower_edge_inset_fraction=.022,
        notice='边缘小方块、外围细框、背面方向标记和侧面收边来自 p12 图示；无尺寸细节的大小/深度/材质均为外观近似，不作为装配尺寸。')


def validate(profile):
    if profile is None:return None
    if profile.get('revision')!=1 or profile.get('accuracy')!='appearance_only':raise ValueError('3D 外观参考版本或精度标记无效')
    for key,maximum,size in [('edge_features',256,4),('perimeter_frames',8,4),('back_marker',3,2)]:
        values=profile.get(key,[])
        if not isinstance(values,list) or len(values)>maximum:raise ValueError('3D 外观细节数量无效')
        for row in values:
            if len(row)!=size or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in row):
                raise ValueError('3D 外观细节必须是 0–1 的有限相对位置')
            if size==4 and not(row[0]<row[2] and row[1]<row[3]):raise ValueError('3D 外观细节矩形无效')
    inset=profile.get('lower_edge_inset_fraction',0)
    if not isinstance(inset,(int,float)) or not math.isfinite(inset) or not 0<=inset<=.04:raise ValueError('3D 侧面外观收边无效')
    return profile
