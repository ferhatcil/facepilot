bl_info = {
    'name': 'Kolay Malzeme TR',
    'author': 'Codex',
    'version': (1, 7, 0),
    'blender': (4, 2, 0),
    'location': '3B Görünüm > N > Kolay Malzeme',
    'description': 'Türkçe yüz seçimi, malzeme atama ve dışa aktarılmayan karartma önizlemesi',
    'category': 'Mesh',
}

import bpy
import bmesh
import math
import random
import colorsys
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty


# Preview and selection memory are deliberately NOT mesh/material attributes.
_runtime = {
    'memory': {}, 'handler': None, 'shader': None,
    'batch': None, 'positions': [], 'signature': None, 'mesh_key': None,
    'geometry_dirty': True, 'gpu_dirty': True, 'error': '',
    'material_colors': {}, 'color_positions': [], 'color_batches': [],
    'target_items': {},
    'red_marks': None, 'red_handler': None, 'red_shader': None, 'red_batch': None,
    'red_positions': [], 'red_signature': None, 'red_dirty': True, 'red_error': '',
    'red_geometry_dirty': True,
    'red_line_positions': [], 'red_line_shader': None, 'red_line_batch': None,
    'keymaps': [],
    'hole_scan': None, 'hole_handler': None, 'hole_shader': None, 'hole_batch': None,
    'hole_positions': [], 'hole_dirty': True, 'hole_gpu_dirty': True, 'hole_error': '',
    'repair_report': None,
    'repair_preview': None, 'patch_handler': None, 'patch_shader': None,
    'patch_line_shader': None, 'patch_batch': None, 'patch_line_batch': None,
    'patch_dirty': True, 'patch_check': True, 'patch_error': '',
}

PREVIEW_ITEMS = [
    ('OFF', 'Kapalı', 'Normal görünüme dön'),
    ('SELECTED', 'Seçileni karart', 'Seçili yüzleri geçici olarak siyah göster'),
    ('OTHERS', 'Diğer yüzleri karart', 'Seçili yüzlerin dışında kalan yüzleri karart'),
    ('MATERIAL', 'Bu malzemeyi karart', 'Etkin malzemenin yüzlerini karart'),
    ('OTHER_MATERIALS', 'Diğer malzemeleri karart', 'Yalnız etkin malzemeyi normal görünümde bırak'),
]


def _redraw():
    wm = bpy.context.window_manager
    if wm:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


def _single_edit_mesh(context):
    obj = context.edit_object
    return (context.mode == 'EDIT_MESH' and obj is not None and obj.type == 'MESH'
            and len(context.objects_in_mode_unique_data) == 1)


def _edit_mesh(context):
    obj = context.edit_object
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    return obj, bm


def _topology_key(bm):
    return (len(bm.verts), len(bm.edges), len(bm.faces),
            hash(tuple(tuple(v.index for v in f.verts) for f in bm.faces)))


def _mesh_key(mesh):
    # session_uid survives rename and undo's internal datablock replacement.
    return getattr(mesh, 'session_uid', mesh.as_pointer())


def _boundary_topology_key(bm):
    return (_topology_key(bm), hash(tuple(tuple(v.index for v in e.verts) for e in bm.edges)))


def find_open_boundaries(bm, matrix=None):
    """List actual open boundary components, not guessed/automatically fixed holes.

    Hidden faces still participate in topology, so hiding a face cannot invent a
    hole. A single-face edge can also be an intentional garment opening.
    """
    bm.verts.index_update(); bm.edges.index_update(); bm.faces.index_update()
    boundary = {e for e in bm.edges if len(e.link_faces) == 1}
    seen = set()
    regions = []
    for seed in sorted(boundary, key=lambda e: e.index):
        if seed in seen:
            continue
        stack = [seed]; seen.add(seed); edges = []
        while stack:
            edge = stack.pop(); edges.append(edge)
            for vertex in edge.verts:
                for other in vertex.link_edges:
                    if other in boundary and other not in seen:
                        seen.add(other); stack.append(other)
        vertices = {v for e in edges for v in e.verts}
        degrees = [sum(e in boundary for e in v.link_edges) for v in vertices]
        closed = len(edges) >= 3 and all(d == 2 for d in degrees)
        perimeter = sum(((matrix @ e.verts[1].co) - (matrix @ e.verts[0].co)).length
                        if matrix is not None else e.calc_length() for e in edges)
        regions.append({'edges': tuple(sorted(e.index for e in edges)),
                        'verts': tuple(sorted(v.index for v in vertices)),
                        'edge_count': len(edges), 'closed': closed,
                        'branched': any(d > 2 for d in degrees), 'perimeter': perimeter,
                        'materials': tuple(sorted({f.material_index for e in edges for f in e.link_faces})),
                        'hidden_edges': sum(e.hide or any(v.hide for v in e.verts) for e in edges)})
    return sorted(regions, key=lambda r: (not r['closed'], r['edge_count'], r['perimeter'], r['edges']))


def _cross2(a, b):
    return a[0]*b[1]-a[1]*b[0]


def _sub2(a, b):
    return (a[0]-b[0], a[1]-b[1])


def _clip_polygon_2d(subject, boundary, epsilon):
    result = list(subject)
    for i, a in enumerate(boundary):
        b = boundary[(i+1)%len(boundary)]; edge = _sub2(b,a)
        source, result = result, []
        if not source:
            break
        previous = source[-1]; before = _cross2(edge,_sub2(previous,a))
        for point in source:
            after = _cross2(edge,_sub2(point,a))
            if (before >= -epsilon) != (after >= -epsilon):
                t = before/(before-after)
                result.append((previous[0]+(point[0]-previous[0])*t, previous[1]+(point[1]-previous[1])*t))
            if after >= -epsilon:
                result.append(point)
            previous, before = point, after
    return result


def _segment_inside_convex_2d(a, b, boundary, epsilon):
    lower, upper = 0.0, 1.0
    direction = _sub2(b,a)
    for i, start in enumerate(boundary):
        edge = _sub2(boundary[(i+1)%len(boundary)],start)
        initial = _cross2(edge,_sub2(a,start)); change = _cross2(edge,direction)
        if abs(change) <= epsilon:
            if initial <= epsilon:return False
        else:
            threshold = (epsilon-initial)/change
            if change > 0:lower = max(lower,threshold)
            else:upper = min(upper,threshold)
    return lower < upper and upper >= 0 and lower <= 1


def _patch_overlaps_surface(points, tree, bm, coords, triangle_cache):
    """Area/plane intersection, including tiny coplanar faces missed by ray probes.

    Shared outer-boundary contact is allowed. For slightly warped quads both
    possible diagonals are checked conservatively before choosing an auto patch.
    """
    from mathutils.geometry import tessellate_polygon
    center = sum(points, points[0]*0)/len(points)
    diameter = max((a-b).length for a in points for b in points)
    epsilon_length = max(diameter*1e-7,1e-10)
    epsilon_area = max(diameter*diameter*1e-10,1e-20)
    radius = max((p-center).length for p in points)+epsilon_length
    nearby = {hit[2] for hit in tree.find_nearest_range(center,radius) if hit[2] is not None}
    planes = [(points[0],points[i],points[i+1]) for i in range(1,len(points)-1)]
    if len(points)==4:planes.extend([(points[1],points[2],points[3]),(points[1],points[3],points[0])])
    for plane in planes:
        normal = (plane[1]-plane[0]).cross(plane[2]-plane[0]).normalized()
        drop = max(range(3),key=lambda k:abs(normal[k]));axes = [k for k in range(3) if k!=drop]
        project = lambda p:(p[axes[0]],p[axes[1]])
        boundary = [project(p) for p in points]
        signed_area = sum(_cross2(boundary[i],boundary[(i+1)%len(boundary)]) for i in range(len(boundary)))
        if signed_area < 0:boundary.reverse()
        for index in nearby:
            if index not in triangle_cache:
                face=bm.faces[index]
                polygon=[coords[v.index] for v in face.verts]
                triangles=tessellate_polygon([polygon])
                # Blender 5 returns point indices; older versions returned vectors.
                triangle_cache[index]=[tuple(polygon[p] if isinstance(p,int) else p for p in triangle)
                                       for triangle in triangles]
            for triangle in triangle_cache[index]:
                distances=[(p-plane[0]).dot(normal) for p in triangle]
                if all(d>epsilon_length for d in distances) or all(d<-epsilon_length for d in distances):continue
                if all(abs(d)<=epsilon_length for d in distances):
                    clipped=_clip_polygon_2d([project(p) for p in triangle],boundary,epsilon_area)
                    if len(clipped)>=3:
                        area=abs(sum(_cross2(clipped[i],clipped[(i+1)%len(clipped)]) for i in range(len(clipped))))*0.5
                        if area>epsilon_area:return True
                    continue
                intersections=[]
                for i,point in enumerate(triangle):
                    other=triangle[(i+1)%3];a=distances[i];b=distances[(i+1)%3]
                    if abs(a)<=epsilon_length:intersections.append(point)
                    if a*b<0:intersections.append(point+(other-point)*(a/(a-b)))
                unique=[]
                for point in intersections:
                    if not any((point-q).length<=epsilon_length for q in unique):unique.append(point)
                if unique:
                    pair=max(((a,b) for a in unique for b in unique),key=lambda pair:(pair[0]-pair[1]).length_squared)
                    if _segment_inside_convex_2d(project(pair[0]),project(pair[1]),boundary,epsilon_area):return True
    return False


def plan_small_hole_repairs(obj, bm, regions, max_size):
    """Conservative tri/quad patch eligibility. This function changes no geometry."""
    from mathutils.bvhtree import BVHTree
    bm.normal_update()
    world = obj.matrix_world
    coords = [world @ v.co for v in bm.verts]
    tree = BVHTree.FromPolygons(coords, [tuple(v.index for v in f.verts) for f in bm.faces]) if bm.faces else None
    plans = []
    triangle_cache = {}
    for region in regions:
        reason = ''
        edges = [bm.edges[i] for i in region['edges']]
        vertices = [bm.verts[i] for i in region['verts']]
        materials = tuple(sorted({f.material_index for e in edges for f in e.link_faces}))
        if not region['closed'] or region['edge_count'] not in {3, 4}:
            reason = 'Üçgen/dörtgen kapalı halka değil'
        elif any(e.hide or any(v.hide for v in e.verts) or any(f.hide for f in e.link_faces) for e in edges):
            reason = 'Gizli geometri'
        elif len(materials) != 1:
            reason = 'Birden fazla komşu malzeme'
        elif any(len(e.link_faces) > 2 for v in vertices for e in v.link_edges):
            reason = 'Yakında çok-yüzlü kenar'
        elif any(set(f.verts) == set(vertices) for f in vertices[0].link_faces):
            reason = 'Bu sınırda zaten yüz var'
        ordered = []
        normal = None
        if not reason:
            adjacency = {v: [] for v in vertices}
            for edge in edges:
                a, b = edge.verts
                adjacency[a].append(b); adjacency[b].append(a)
            current = min(vertices, key=lambda v: v.index); previous = None
            for _ in vertices:
                ordered.append(current)
                nxt = min((v for v in adjacency[current] if v != previous), key=lambda v: v.index)
                previous, current = current, nxt
            if current != ordered[0] or len(set(ordered)) != len(vertices):
                reason = 'Sınır sıralanamıyor'
        if not reason:
            points = [coords[v.index] for v in ordered]
            diameter = max((a-b).length for a in points for b in points)
            if diameter > max_size:
                reason = 'Boyut sınırından büyük'
            elif diameter <= 1e-9:
                reason = 'Sıfır boyutlu açıklık'
            else:
                cross = max(((points[i]-points[0]).cross(points[j]-points[0])
                             for i in range(1,len(points)) for j in range(i+1,len(points))), key=lambda n:n.length)
                if cross.length <= diameter*diameter*1e-8:
                    reason = 'Dejenere sınır'
                else:
                    normal = cross.normalized()
                    if any(abs((p-points[0]).dot(normal)) > diameter*0.05 for p in points):
                        reason = 'Fazla eğri / düzlemsel değil'
                    elif any((points[(i+1)%len(points)]-points[i]).cross(points[(i+2)%len(points)]-points[(i+1)%len(points)]).dot(normal)
                             <= diameter*diameter*1e-8 for i in range(len(points))):
                        reason = 'İçbükey veya dejenere sınır'
        if not reason:
            directions = []
            for i, vert in enumerate(ordered):
                other = ordered[(i+1)%len(ordered)]
                edge = next(e for e in edges if vert in e.verts and other in e.verts)
                loop = next(l for l in edge.link_faces[0].loops if l.edge == edge)
                directions.append(loop.vert == vert)
            if any(directions) and not all(directions):
                reason = 'Komşu yüz yönleri tutarsız'
        if not reason and tree and _patch_overlaps_surface(points,tree,bm,coords,triangle_cache):
            reason = 'Mevcut yüzeyle çakışma'
        plans.append({'region': region, 'edges': edges, 'ok': not reason, 'reason': reason,
                      'material_index': materials[0] if len(materials)==1 else None})
    return plans


def _repair_state_key(obj, bm):
    """Selection/view may change; a proposal must not outlive source-data edits."""
    return (_mesh_key(obj), _mesh_key(obj.data), _boundary_topology_key(bm),
            hash(tuple((tuple(v.co), v.hide) for v in bm.verts)),
            hash(tuple((e.hide, e.seam, e.smooth) for e in bm.edges)),
            hash(tuple((f.material_index, f.hide) for f in bm.faces)),
            tuple((_mesh_key(s.material) if s.material else None) for s in obj.material_slots),
            tuple(tuple(row) for row in obj.matrix_world),
            tuple((layer.name, hash(tuple(tuple(l[layer].uv) for f in bm.faces for l in f.loops)))
                  for layer in bm.loops.layers.uv.values()))


def _ordered_boundary(bm, region):
    edges=[bm.edges[i] for i in region['edges']]
    adjacency={v:[] for e in edges for v in e.verts}
    for edge in edges:
        a,b=edge.verts;adjacency[a].append(b);adjacency[b].append(a)
    if not adjacency or any(len(links)!=2 for links in adjacency.values()):return []
    ordered=[];current=min(adjacency,key=lambda v:v.index);previous=None
    for _ in adjacency:
        ordered.append(current)
        nxt=min((v for v in adjacency[current] if v!=previous),key=lambda v:v.index)
        previous,current=current,nxt
    return ordered if current==ordered[0] and len(set(ordered))==len(adjacency) else []


def _patch_boundary_matches(bm, region, triangles):
    """Every boundary used once against its neighbor; internal edges twice/opposite."""
    uses={}
    for triangle in triangles:
        for a,b in zip(triangle,triangle[1:]+triangle[:1]):
            uses.setdefault(tuple(sorted((a,b))),[]).append((a,b))
    border={tuple(sorted(v.index for v in bm.edges[i].verts)):bm.edges[i] for i in region['edges']}
    for key,directions in uses.items():
        if key in border:
            if len(directions)!=1:return False
            edge=border[key];loop=next(l for l in edge.link_faces[0].loops if l.edge==edge)
            if directions[0]!=(loop.link_loop_next.vert.index,loop.vert.index):return False
        else:
            if len(directions)!=2 or directions[0]!=tuple(reversed(directions[1])):return False
            existing=bm.edges.get((bm.verts[key[0]],bm.verts[key[1]]))
            if existing is not None and existing.link_faces:return False
    return set(border).issubset(uses)


def build_repair_preview(obj, bm, regions, max_size):
    """Build exact candidate triangles/UVs on copies, without touching the edit mesh."""
    from mathutils.bvhtree import BVHTree
    bm.normal_update()
    coords=[obj.matrix_world@v.co for v in bm.verts]
    tree=BVHTree.FromPolygons(coords,[tuple(v.index for v in f.verts) for f in bm.faces]) if bm.faces else None
    cache={};patches=[];skipped={};previous_triangles=[]
    for region in regions:
        reason='';ordered=[]
        edges=[bm.edges[i] for i in region['edges']]
        materials={f.material_index for e in edges for f in e.link_faces}
        if not region['closed'] or not 3<=region['edge_count']<=256:reason='Kapalı, en fazla 256 kenarlı halka gerekli'
        elif any(len(e.link_faces)!=1 for e in edges):reason='Sınır artık açık değil'
        elif any(e.hide or any(v.hide for v in e.verts) or any(f.hide for f in e.link_faces) for e in edges):reason='Gizli geometri'
        elif len(materials)!=1:reason='Birden fazla komşu malzeme'
        elif any(len(e.link_faces)>2 for edge in edges for v in edge.verts for e in v.link_edges):reason='Yakında çok-yüzlü kenar'
        else:
            ordered=_ordered_boundary(bm,region)
            if not ordered:reason='Sınır sıralanamıyor'
        if not reason:
            points=[coords[v.index] for v in ordered]
            diameter=max((a-b).length for a in points for b in points)
            if diameter>max_size:reason='Önizleme boyut sınırından büyük'
            elif diameter<=1e-9 or any((points[i]-points[(i+1)%len(points)]).length<diameter*1e-7 for i in range(len(points))):reason='Çakışık noktalar / dejenere sınır'
        if not reason:
            temp=bm.copy()
            try:
                temp.edges.ensure_lookup_table();temp.verts.ensure_lookup_table()
                fill=bmesh.ops.holes_fill(temp,edges=[temp.edges[i] for i in region['edges']],sides=0)['faces']
                if len(fill)!=1:
                    reason='Tek bir yama oluşturulamadı';triangles=[]
                else:
                    face=fill[0]
                    same=opposite=0
                    for loop in face.loops:
                        old=next(f for f in loop.edge.link_faces if f!=face)
                        other=next(l for l in old.loops if l.edge==loop.edge)
                        if other.vert==loop.vert:same+=1
                        else:opposite+=1
                    if same>opposite:face.normal_flip()
                    filled=bmesh.ops.triangulate(temp,faces=fill,quad_method='BEAUTY',ngon_method='BEAUTY')['faces']
                    triangles=[tuple(v.index for v in f.verts) for f in filled]
                    uv_data=[{layer.name:tuple(tuple(l[layer].uv) for l in f.loops)
                              for layer in temp.loops.layers.uv.values()} for f in filled]
                    if len(triangles)!=len(ordered)-2 or not _patch_boundary_matches(bm,region,triangles):
                        reason='Üçgenleme sınırı / komşu yüz yönleri tutarsız'
                    else:
                        for triangle in triangles:
                            p=[coords[i] for i in triangle]
                            if (p[1]-p[0]).cross(p[2]-p[0]).length<=diameter*diameter*1e-10:
                                reason='Sıfır alanlı üçgen';break
                            if tree and _patch_overlaps_surface(p,tree,bm,coords,cache):
                                reason='Mevcut yüzeyle çakışma';break
                        if not reason:
                            all_triangles=previous_triangles+triangles
                            for index,triangle in enumerate(triangles):
                                other=all_triangles[:len(previous_triangles)+index]
                                if other:
                                    other_tree=BVHTree.FromPolygons(coords,other)
                                    # A compact read-only BMesh gives the overlap helper stable face indices.
                                    other_bm=bmesh.new()
                                    try:
                                        verts={i:other_bm.verts.new(coords[i]) for t in other for i in t}
                                        for t in other:other_bm.faces.new([verts[i] for i in t])
                                        other_bm.faces.ensure_lookup_table();other_bm.verts.index_update()
                                        oc=[v.co.copy() for v in other_bm.verts]
                                        if _patch_overlaps_surface([coords[i] for i in triangle],other_tree,other_bm,oc,{}):
                                            reason='Önerilen yamalar birbiriyle çakışıyor';break
                                    finally:other_bm.free()
                    if not reason:
                        patches.append({'triangles':triangles,'uv_data':uv_data,
                                        'material_index':next(iter(materials)), 'boundary':region['edges']})
                        previous_triangles.extend(triangles)
            finally:temp.free()
        if reason:skipped[reason]=skipped.get(reason,0)+1
    return {'state':_repair_state_key(obj,bm),'mesh':_mesh_key(obj.data),'max_size':max_size,
            'patches':patches,'skipped':skipped,'coords':[tuple(v.co) for v in bm.verts]}


def clear_repair_preview(message=''):
    if _runtime['patch_handler'] is not None:
        try:bpy.types.SpaceView3D.draw_handler_remove(_runtime['patch_handler'],'WINDOW')
        except (ValueError,ReferenceError):pass
    if bpy.app.timers.is_registered(_patch_tick):bpy.app.timers.unregister(_patch_tick)
    _runtime.update(repair_preview=None,patch_handler=None,patch_shader=None,patch_line_shader=None,
                    patch_batch=None,patch_line_batch=None,patch_dirty=True,patch_error=message)
    _redraw()


def _patch_tick():
    plan=_runtime['repair_preview']
    if not plan:return None
    if _single_edit_mesh(bpy.context) and _runtime['patch_check']:
        obj,bm=_edit_mesh(bpy.context)
        if plan['mesh']==_mesh_key(obj.data):
            if plan['state']!=_repair_state_key(obj,bm):
                clear_repair_preview('Model değişti; yeniden önizleyin.');return None
            _runtime['patch_check']=False
    return 0.35


def _draw_patch():
    plan=_runtime['repair_preview']
    if not plan or not _single_edit_mesh(bpy.context):return
    obj=bpy.context.edit_object
    if plan['mesh']!=_mesh_key(obj.data) or plan['state'][0]!=_mesh_key(obj) or not obj.visible_get():return
    import gpu
    from gpu_extras.batch import batch_for_shader
    blend,depth,write=gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()
    try:
        if _runtime['patch_shader'] is None:
            _runtime['patch_shader']=gpu.shader.from_builtin('UNIFORM_COLOR')
            _runtime['patch_line_shader']=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        shader=_runtime['patch_shader'];line=_runtime['patch_line_shader']
        if _runtime['patch_dirty']:
            from mathutils import Vector
            positions=[];lines=[]
            for patch in plan['patches']:
                for tri in patch['triangles']:
                    points=[Vector(plan['coords'][i]) for i in tri]
                    normal=(points[1]-points[0]).cross(points[2]-points[0]).normalized()
                    points=[p+normal*0.00001 for p in points]
                    positions.extend(points)
                    for i in range(3):lines.extend((points[i],points[(i+1)%3]))
            _runtime['patch_batch']=batch_for_shader(shader,'TRIS',{'pos':positions})
            _runtime['patch_line_batch']=batch_for_shader(line,'LINES',{'pos':lines})
            _runtime['patch_dirty']=False
        gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('LESS_EQUAL');gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(obj.matrix_world)
            shader.bind();shader.uniform_float('color',(.65,.35,1.0,bpy.context.window_manager.kmtr_settings.patch_opacity))
            _runtime['patch_batch'].draw(shader)
            line.bind();line.uniform_float('viewportSize',gpu.state.viewport_get()[2:])
            line.uniform_float('lineWidth',2.0);line.uniform_float('color',(.8,.5,1.0,1.0))
            _runtime['patch_line_batch'].draw(line)
    except Exception as exc:_runtime['patch_error']='Yama önizlemesi çizilemedi: '+str(exc)
    finally:
        gpu.state.blend_set(blend);gpu.state.depth_test_set(depth);gpu.state.depth_mask_set(write)


def _topology_edited(obj):
    clear_repair_preview()
    clear_red_marks()
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    _runtime.update(signature=None, geometry_dirty=True, red_geometry_dirty=True, hole_dirty=True)
    if _runtime['hole_scan']:
        _runtime['hole_scan']['stale'] = True
    _redraw()


def _stop_hole_overlay():
    if _runtime['hole_handler'] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_runtime['hole_handler'], 'WINDOW')
        except (ValueError, ReferenceError):
            pass
    if bpy.app.timers.is_registered(_holes_tick):
        bpy.app.timers.unregister(_holes_tick)
    _runtime.update(hole_handler=None, hole_shader=None, hole_batch=None, hole_positions=[], hole_gpu_dirty=True)
    _redraw()


def _hole_report(obj, bm):
    report = _runtime['hole_scan']
    if report is None or report['mesh'] != _mesh_key(obj.data):
        return None
    if report['topology'] != _boundary_topology_key(bm):
        report['stale'] = True
        return None
    return report


def _holes_tick():
    if not _runtime['hole_scan']:
        return None
    if not _single_edit_mesh(bpy.context):
        _runtime['hole_positions'] = []
        _runtime['hole_dirty'] = True
        return 0.25
    if _runtime['hole_dirty']:
        obj, bm = _edit_mesh(bpy.context)
        report = _hole_report(obj, bm)
        if report is None:
            _runtime['hole_positions'] = []
            _runtime['hole_batch'] = None
            return 0.25
        ids = {i for r in report['regions'] for i in r['edges']}
        if not ids or not bm.verts:
            _runtime.update(hole_positions=[], hole_batch=None, hole_dirty=False, hole_gpu_dirty=True)
            return 0.25
        span = max((max(v.co[k] for v in bm.verts) - min(v.co[k] for v in bm.verts) for k in range(3)), default=1.0)
        offset = max(span * 0.000025, 0.00000025)
        positions = []
        for i in sorted(ids):
            edge = bm.edges[i]
            if edge.hide or any(v.hide for v in edge.verts):
                continue
            shift = edge.link_faces[0].normal * offset
            positions.extend(tuple(v.co + shift) for v in edge.verts)
        _runtime.update(hole_positions=positions, hole_dirty=False, hole_gpu_dirty=True)
        _redraw()
    return 0.25


def _draw_holes():
    report = _runtime['hole_scan']
    if not report or report['stale'] or not _runtime['hole_positions'] or not _single_edit_mesh(bpy.context):
        return
    obj = bpy.context.edit_object
    if report['mesh'] != _mesh_key(obj.data) or not obj.visible_get():
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    blend, depth, write = gpu.state.blend_get(), gpu.state.depth_test_get(), gpu.state.depth_mask_get()
    try:
        if _runtime['hole_shader'] is None:
            _runtime['hole_shader'] = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        shader = _runtime['hole_shader']
        if _runtime['hole_gpu_dirty']:
            _runtime['hole_batch'] = batch_for_shader(shader, 'LINES', {'pos': _runtime['hole_positions']})
            _runtime['hole_gpu_dirty'] = False
        gpu.state.blend_set('ALPHA'); gpu.state.depth_test_set('LESS_EQUAL'); gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(obj.matrix_world)
            shader.bind(); shader.uniform_float('viewportSize', gpu.state.viewport_get()[2:])
            shader.uniform_float('lineWidth', 2.5); shader.uniform_float('color', (0.1, 1.0, 0.9, 1.0))
            _runtime['hole_batch'].draw(shader)
        _runtime['hole_error'] = ''
    except Exception as exc:
        _runtime['hole_error'] = str(exc)
    finally:
        gpu.state.blend_set(blend); gpu.state.depth_test_set(depth); gpu.state.depth_mask_set(write)


def _holes_overlay_changed(settings, context):
    if not settings.hole_overlay or not _runtime['hole_scan']:
        _stop_hole_overlay()
    elif not bpy.app.background:
        if _runtime['hole_handler'] is None:
            _runtime['hole_handler'] = bpy.types.SpaceView3D.draw_handler_add(_draw_holes, (), 'WINDOW', 'POST_VIEW')
        if not bpy.app.timers.is_registered(_holes_tick):
            bpy.app.timers.register(_holes_tick, first_interval=0.01)
        _runtime['hole_dirty'] = True
        _redraw()


_HIDDEN_LAYERS = ('.kmtr_v1_hidden_verts_92b', '.kmtr_v1_hidden_edges_92b', '.kmtr_v1_hidden_faces_92b')
_TOPOLOGY_LAYER = '.kmtr_v1_topology_92b'


def _isolation_layers(bm):
    layers = tuple(elements.layers.int.get(name) for elements, name in zip((bm.verts, bm.edges, bm.faces), _HIDDEN_LAYERS))
    topology = bm.faces.layers.int.get(_TOPOLOGY_LAYER)
    return (layers, topology) if all(layer is not None for layer in layers) and topology is not None else None


def _drop_isolation_layers(bm):
    for elements, name in zip((bm.verts, bm.edges, bm.faces), _HIDDEN_LAYERS):
        layer = elements.layers.int.get(name)
        if layer is not None:
            elements.layers.int.remove(layer)
    layer = bm.faces.layers.int.get(_TOPOLOGY_LAYER)
    if layer is not None:
        bm.faces.layers.int.remove(layer)


def _store_hidden(bm):
    # Edit-mode undo serializes BMesh custom data. Ordinary Python dictionaries
    # cannot distinguish identical visible states at different undo positions.
    # These temporary INTEGER layers are only used by explicit isolation, never
    # by black preview. They are removed on restore and are not color attributes.
    for elements, name in zip((bm.verts, bm.edges, bm.faces), _HIDDEN_LAYERS):
        layer = elements.layers.int.new(name)
        for e in elements:
            ordinal = len(elements) if e.index == 0 else e.index + 1
            e[layer] = (ordinal << 1) | int(e.hide)
    signature = bm.faces.layers.int.new(_TOPOLOGY_LAYER)
    bm.faces[0][signature] = _topology_key(bm)[3] & 0x7fffffff


def _restore_hidden(bm):
    stored = _isolation_layers(bm)
    if stored is None or not bm.faces:
        return False
    layers, signature = stored
    if bm.faces[0][signature] != (_topology_key(bm)[3] & 0x7fffffff):
        return False
    for elements, layer in zip((bm.verts, bm.edges, bm.faces), layers):
        if not elements or (elements[0][layer] >> 1) != len(elements):
            return False
        if any((e[layer] >> 1) != e.index + 1 for e in list(elements)[1:]):
            return False
    for elements, layer in zip((bm.verts, bm.edges, bm.faces), layers):
        for element in elements:
            element.hide = bool(element[layer] & 1)
    _drop_isolation_layers(bm)
    return True


def _flush(obj):
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    _runtime['signature'] = None
    _redraw()


def _set_faces(context, bm, indices):
    context.tool_settings.mesh_select_mode = (False, False, True)
    for face in bm.faces:
        face.select_set(False)
    for edge in bm.edges:
        edge.select_set(False)
    for vert in bm.verts:
        vert.select_set(False)
    for i in indices:
        if 0 <= i < len(bm.faces) and not bm.faces[i].hide:
            bm.faces[i].select_set(True)
    bm.select_flush_mode()


def smart_face_indices(bm, seed_index, mode='AUTO', main_material=0, angle=math.radians(35)):
    """Material-aware grouping, with a crease-bounded flood for unlabelled faces.

    This is geometric selection, not semantic/AI object recognition.
    """
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    if not 0 <= seed_index < len(bm.faces) or bm.faces[seed_index].hide:
        return ()
    seed = bm.faces[seed_index]
    if mode == 'AUTO':
        mode = 'MATERIAL' if seed.material_index != main_material else 'SURFACE'
    if mode == 'MATERIAL':
        return tuple(f.index for f in bm.faces if not f.hide and f.material_index == seed.material_index)
    found = {seed_index}
    stack = [seed]
    while stack:
        face = stack.pop()
        for edge in face.edges:
            if len(edge.link_faces) != 2 or edge.seam or not edge.smooth:
                continue
            other = edge.link_faces[0] if edge.link_faces[1] == face else edge.link_faces[1]
            if (other.index in found or other.hide or other.material_index != seed.material_index
                    or face.normal.angle(other.normal, math.pi) > angle):
                continue
            found.add(other.index)
            stack.append(other)
    return tuple(sorted(found))


def raycast_face_index(bm, origin, direction):
    """Pick the base edit mesh, excluding hidden faces from the BVH entirely."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bm.verts.index_update()
    bm.faces.index_update()
    faces = [f for f in bm.faces if not f.hide]
    if not faces:
        return None
    tree = BVHTree.FromPolygons([v.co.copy() for v in bm.verts],
                               [tuple(v.index for v in f.verts) for f in faces])
    location, normal, index, distance = tree.ray_cast(Vector(origin), Vector(direction).normalized())
    return faces[index].index if index is not None else None


def red_face_indices(obj, bm):
    stored = _runtime['red_marks']
    if not stored or stored['mesh'] != _mesh_key(obj.data):
        return set()
    if stored['topology'] != _topology_key(bm):
        clear_red_marks()
        return set()
    return set(stored['faces'])


def red_stroke_erases(obj, bm, first_face, force_erase=False):
    """Choose once per stroke, so revisiting a face during a drag cannot flicker."""
    return bool(force_erase or first_face in red_face_indices(obj, bm))


def clear_red_marks():
    if _runtime['red_handler'] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_runtime['red_handler'], 'WINDOW')
        except (ValueError, ReferenceError):
            pass
    if bpy.app.timers.is_registered(_red_tick):
        bpy.app.timers.unregister(_red_tick)
    _runtime.update(red_marks=None, red_handler=None, red_shader=None, red_batch=None,
                    red_positions=[], red_line_positions=[], red_line_shader=None, red_line_batch=None,
                    red_signature=None, red_dirty=True, red_error='', signature=None)
    _redraw()


def mark_red_faces(context, indices, erase=False):
    obj, bm = _edit_mesh(context)
    red_face_indices(obj, bm)  # Discard stale topology before accepting new marks.
    stored = _runtime['red_marks']
    if not stored or stored['mesh'] != _mesh_key(obj.data):
        stored = {'mesh': _mesh_key(obj.data), 'topology': _topology_key(bm), 'faces': {}}
        _runtime['red_marks'] = stored
    for i in indices:
        if erase:
            stored['faces'].pop(i, None)
        elif 0 <= i < len(bm.faces) and bm.faces[i].select and not bm.faces[i].hide:
            stored['faces'].setdefault(i, bm.faces[i].material_index)
    result = set(stored['faces'])
    _runtime['red_signature'] = None
    _runtime['signature'] = None
    if not result:
        clear_red_marks()
    elif not bpy.app.background:
        if _runtime['red_handler'] is None:
            _runtime['red_handler'] = bpy.types.SpaceView3D.draw_handler_add(_draw_red, (), 'WINDOW', 'POST_VIEW')
        if not bpy.app.timers.is_registered(_red_tick):
            bpy.app.timers.register(_red_tick, first_interval=0.01)
    _redraw()
    return result


def _red_tick():
    if not _runtime['red_marks']:
        return None
    if not _single_edit_mesh(bpy.context):
        _runtime['red_positions'] = []
        _runtime['red_signature'] = None
        return 0.1
    obj, bm = _edit_mesh(bpy.context)
    ids = red_face_indices(obj, bm)
    if not _runtime['red_marks']:
        return None
    visible = tuple(sorted(i for i in ids if not bm.faces[i].hide))
    signature = (obj.data.as_pointer(), visible)
    if signature != _runtime['red_signature'] or _runtime['red_geometry_dirty']:
        positions = []
        line_positions = []
        if visible:
            targets = set(visible)
            span = max((max(v.co[k] for v in bm.verts) - min(v.co[k] for v in bm.verts) for k in range(3)), default=1.0)
            offset = max(span * 0.00003, 0.0000003)
            for triangle in bm.calc_loop_triangles():
                face = triangle[0].face
                if face.index in targets:
                    positions.extend(tuple(loop.vert.co + face.normal * offset) for loop in triangle)
            seen_edges = set()
            for i in visible:
                face = bm.faces[i]
                for edge in face.edges:
                    if edge not in seen_edges:
                        seen_edges.add(edge)
                        line_positions.extend(tuple(v.co + face.normal * offset) for v in edge.verts)
        _runtime.update(red_positions=positions, red_line_positions=line_positions,
                        red_signature=signature, red_dirty=True, red_geometry_dirty=False)
        _redraw()
    return 0.1


def _draw_red():
    if not _single_edit_mesh(bpy.context) or not _runtime['red_positions'] or not _runtime['red_marks']:
        return
    obj = bpy.context.edit_object
    if _mesh_key(obj.data) != _runtime['red_marks']['mesh'] or not obj.visible_get():
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    blend, depth, write = gpu.state.blend_get(), gpu.state.depth_test_get(), gpu.state.depth_mask_get()
    try:
        if _runtime['red_shader'] is None:
            _runtime['red_shader'] = gpu.shader.from_builtin('UNIFORM_COLOR')
        if _runtime['red_line_shader'] is None:
            _runtime['red_line_shader'] = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        shader = _runtime['red_shader']
        line_shader = _runtime['red_line_shader']
        if _runtime['red_dirty']:
            _runtime['red_batch'] = batch_for_shader(shader, 'TRIS', {'pos': _runtime['red_positions']})
            _runtime['red_line_batch'] = batch_for_shader(line_shader, 'LINES', {'pos': _runtime['red_line_positions']})
            _runtime['red_dirty'] = False
        gpu.state.blend_set('ALPHA'); gpu.state.depth_test_set('LESS_EQUAL'); gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(obj.matrix_world)
            opacity = bpy.context.window_manager.kmtr_settings.red_fill_opacity
            if opacity > 0.0:
                shader.bind(); shader.uniform_float('color', (1.0, 0.15, 0.1, opacity))
                _runtime['red_batch'].draw(shader)
            line_shader.bind()
            line_shader.uniform_float('viewportSize', gpu.state.viewport_get()[2:])
            line_shader.uniform_float('lineWidth', 2.0)
            line_shader.uniform_float('color', (1.0, 0.15, 0.1, 1.0))
            _runtime['red_line_batch'].draw(line_shader)
        _runtime['red_error'] = ''
    except Exception as exc:
        _runtime['red_error'] = str(exc)
    finally:
        gpu.state.blend_set(blend); gpu.state.depth_test_set(depth); gpu.state.depth_mask_set(write)


def _move_target_items(self, context):
    obj = (context.edit_object or context.active_object) if context else None
    names = tuple(m.name if m else '(boş yuva)' for m in obj.data.materials) if obj and obj.type == 'MESH' else ()
    # Keep Python strings alive: Blender's dynamic enum UI retains references.
    cache = _runtime['target_items']
    if names not in cache:
        items = [('MAIN', 'Ana malzeme (1. yuva)', 'Yüzleri mesh’in ilk malzeme yuvasına taşı', 0)]
        items.extend(('SLOT_' + str(i), name, name + ' malzemesine taşı', i)
                     for i, name in enumerate(names) if i > 0)
        cache[names] = items
    return cache[names]


def mask_face_indices(bm, mode, material_index):
    """Return only draw targets; this function never mutates any scene data."""
    if mode == 'OFF':
        return ()
    if mode == 'SELECTED':
        return tuple(f.index for f in bm.faces if not f.hide and f.select)
    if mode == 'OTHERS':
        return tuple(f.index for f in bm.faces if not f.hide and not f.select)
    if mode == 'MATERIAL':
        return tuple(f.index for f in bm.faces if not f.hide and f.material_index == material_index)
    if mode == 'OTHER_MATERIALS':
        return tuple(f.index for f in bm.faces if not f.hide and f.material_index != material_index)
    return ()


def material_color_groups(obj, bm):
    """Read-only mapping of current material slots to temporary viewport colors."""
    colors = _runtime['material_colors']
    groups = {}
    for i, slot in enumerate(obj.material_slots):
        mat = slot.material
        color = colors.get(_mesh_key(mat)) if mat else None
        if color is not None:
            groups.setdefault(color, []).extend(f.index for f in bm.faces if not f.hide and f.material_index == i)
    return tuple((color, tuple(ids)) for color, ids in groups.items() if ids)


def _preview_tick():
    try:
        context = bpy.context
        settings = getattr(context.window_manager, 'kmtr_settings', None)
        if settings is None or settings.preview_mode == 'OFF' and not _runtime['material_colors']:
            return None
        if not _single_edit_mesh(context):
            _runtime['positions'] = []
            _runtime['signature'] = None
            _runtime['batch'] = None
            _runtime['color_positions'] = []
            _runtime['color_batches'] = []
            return 0.15
        obj, bm = _edit_mesh(context)
        ids = mask_face_indices(bm, settings.preview_mode, obj.active_material_index)
        marked = set()
        if _runtime['red_marks']:
            marked = red_face_indices(obj, bm)
            ids = tuple(i for i in ids if i not in marked)
        groups = material_color_groups(obj, bm)
        signature = (obj.as_pointer(), obj.data.as_pointer(), len(bm.verts),
                     len(bm.faces), settings.preview_mode, ids, groups)
        if signature != _runtime['signature'] or _runtime['geometry_dirty']:
            targets = set(ids)
            blocked = targets | marked
            color_targets = {i: color for color, faces in groups for i in faces if i not in blocked}
            color_positions = {color: [] for color in color_targets.values()}
            positions = []
            if targets or color_targets:
                span = max((max(v.co[k] for v in bm.verts) - min(v.co[k] for v in bm.verts)
                            for k in range(3)), default=1.0)
                offset = max(span * 0.00001, 0.0000001)
                for triangle in bm.calc_loop_triangles():
                    face = triangle[0].face
                    if face.index in targets:
                        shift = face.normal * offset
                        positions.extend(tuple(loop.vert.co + shift) for loop in triangle)
                    elif face.index in color_targets:
                        shift = face.normal * offset
                        color_positions[color_targets[face.index]].extend(tuple(loop.vert.co + shift) for loop in triangle)
            _runtime.update(positions=positions, signature=signature,
                            color_positions=list(color_positions.items()),
                            mesh_key=obj.data.as_pointer(), geometry_dirty=False, gpu_dirty=True)
            _redraw()
    except (ReferenceError, RuntimeError, ValueError) as exc:
        _runtime.update(positions=[], batch=None, color_positions=[], color_batches=[], signature=None, error=str(exc))
    return 0.15


def _draw_preview():
    context = bpy.context
    settings = getattr(context.window_manager, 'kmtr_settings', None)
    if (settings is None or not _single_edit_mesh(context)
            or not (_runtime['positions'] or _runtime['color_positions'])):
        return
    obj = context.edit_object
    if obj.data.as_pointer() != _runtime['mesh_key'] or not obj.visible_get():
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    old_write = gpu.state.depth_mask_get()
    try:
        if _runtime['shader'] is None:
            _runtime['shader'] = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader = _runtime['shader']
        if _runtime['gpu_dirty']:
            _runtime['batch'] = batch_for_shader(shader, 'TRIS', {'pos': _runtime['positions']}) if _runtime['positions'] else None
            _runtime['color_batches'] = [(color, batch_for_shader(shader, 'TRIS', {'pos': positions}))
                                         for color, positions in _runtime['color_positions'] if positions]
            _runtime['gpu_dirty'] = False
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(obj.matrix_world)
            shader.bind()
            for color, batch in _runtime['color_batches']:
                shader.uniform_float('color', color)
                batch.draw(shader)
            if _runtime['batch'] is not None:
                shader.uniform_float('color', (0.0, 0.0, 0.0, settings.opacity))
                _runtime['batch'].draw(shader)
        _runtime['error'] = ''
    except Exception as exc:
        _runtime['error'] = 'Önizleme çizilemedi: ' + str(exc)
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
        gpu.state.depth_mask_set(old_write)


def _stop_preview():
    if _runtime['handler'] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_runtime['handler'], 'WINDOW')
        except (ValueError, ReferenceError):
            pass
    if bpy.app.timers.is_registered(_preview_tick):
        bpy.app.timers.unregister(_preview_tick)
    _runtime.update(handler=None, shader=None, batch=None, positions=[],
                    color_positions=[], color_batches=[],
                    signature=None, mesh_key=None, gpu_dirty=True, error='')
    _redraw()


def _preview_changed(settings, context):
    if settings.preview_mode == 'OFF' and not _runtime['material_colors']:
        _stop_preview()
    elif not bpy.app.background:
        if _runtime['handler'] is None:
            _runtime['handler'] = bpy.types.SpaceView3D.draw_handler_add(_draw_preview, (), 'WINDOW', 'POST_VIEW')
        if not bpy.app.timers.is_registered(_preview_tick):
            bpy.app.timers.register(_preview_tick, first_interval=0.01)
        _runtime['signature'] = None
        if _runtime['hole_handler'] is not None:
            bpy.types.SpaceView3D.draw_handler_remove(_runtime['hole_handler'], 'WINDOW')
            _runtime['hole_handler'] = bpy.types.SpaceView3D.draw_handler_add(_draw_holes, (), 'WINDOW', 'POST_VIEW')
        _redraw()


def _brush_radius_changed(settings, context):
    if context.workspace and context.mode == 'EDIT_MESH':
        tool = context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=False)
        if tool and tool.idname == 'builtin.select_circle':
            tool.operator_properties('view3d.select_circle').radius = settings.brush_radius
            _redraw()


class KMTR_HoleItem(bpy.types.PropertyGroup):
    name: StringProperty()
    edge_count: IntProperty()
    kind: StringProperty()
    material_text: StringProperty()


class KMTR_Settings(bpy.types.PropertyGroup):
    patch_max_size: FloatProperty(name='Önizleme açıklık sınırı',default=.15,min=.000001,soft_max=1.0,subtype='DISTANCE',unit='LENGTH')
    patch_opacity: FloatProperty(name='Yama saydamlığı',default=.35,min=.05,max=.85,update=lambda s,c:_redraw())
    hole_items: CollectionProperty(type=KMTR_HoleItem, options={'SKIP_SAVE'})
    hole_active_index: IntProperty(default=0, min=0, options={'SKIP_SAVE'})
    hole_active_material_only: BoolProperty(name='Yalnız listedeki malzemeyi tara', default=False, options={'SKIP_SAVE'})
    hole_overlay: BoolProperty(name='Açıklıkları turkuaz çizgilerle göster', default=True, options={'SKIP_SAVE'}, update=_holes_overlay_changed)
    repair_max_size: FloatProperty(name='En büyük açıklık', default=0.02, min=0.000001, soft_max=1.0,
                                  subtype='DISTANCE', unit='LENGTH', options={'SKIP_SAVE'},
                                  description='Otomatik kapatma için dünya birimlerinde en büyük açıklık çapı; yalnız 3/4 kenarlı uygun halkalar işlenir')
    merge_distance: FloatProperty(name='Birleştirme mesafesi', default=0.00001, min=0.00000001, soft_max=0.01,
                                 subtype='DISTANCE', unit='LENGTH', options={'SKIP_SAVE'})
    merge_connected_only: BoolProperty(name='Yalnız bağlı geometri', default=True, options={'SKIP_SAVE'},
                                      description='Ayrı parçaları kaynaklamamak için birleştirmeyi bağlı geometriyle sınırla')
    preview_mode: EnumProperty(items=PREVIEW_ITEMS, default='OFF', options={'SKIP_SAVE'}, update=_preview_changed)
    opacity: FloatProperty(name='Karartma', description='Yalnız ekrandaki siyah katmanın opaklığı',
                           min=0.05, max=1.0, default=1.0, subtype='FACTOR', options={'SKIP_SAVE'},
                           update=lambda self, context: _redraw())
    material_preview_color: FloatVectorProperty(name='Önizleme rengi', subtype='COLOR', size=3,
                                                default=(0.1, 0.55, 1.0), min=0.0, max=1.0, options={'SKIP_SAVE'})
    material_preview_opacity: FloatProperty(name='Renk yoğunluğu', default=0.6, min=0.05, max=1.0,
                                           subtype='FACTOR', options={'SKIP_SAVE'})
    new_name: StringProperty(name='Ad', default='M_Yeni', options={'SKIP_SAVE'})
    brush_radius: IntProperty(name='Fırça boyutu', description='Dairesel seçim fırçasının piksel cinsinden yarıçapı',
                              min=1, max=500, default=40, options={'SKIP_SAVE'}, update=_brush_radius_changed)
    move_target: EnumProperty(name='Hedef', items=_move_target_items, default=0, options={'SKIP_SAVE'})
    red_mode: BoolProperty(name='Ctrl ile kırmızı işaretle', default=False, options={'SKIP_SAVE'},
                          description='Ctrl+sol tık: kırmızı değilse işaretle, kırmızıysa kaldır. Sürükleme ilk yüze göre ekler veya siler. Ctrl+Shift: daima sil')
    red_fill_opacity: FloatProperty(name='İç dolgu', description='0: tamamen saydam iç ve kırmızı çerçeve. Yalnız çalışma görünümü değişir',
                                   default=0.0, min=0.0, max=0.5, subtype='FACTOR', options={'SKIP_SAVE'},
                                   update=lambda self, context: _redraw())
    smart_mode: EnumProperty(name='Yöntem', options={'SKIP_SAVE'}, default='AUTO', items=[
        ('AUTO', 'Otomatik', 'Atanmış malzemeyi ayrı parçalarıyla seç; ana malzemede yüzey sınırını kullan'),
        ('MATERIAL', 'Aynı malzeme', 'Tıklanan yüzün malzemesini kullanan tüm görünür yüzleri seç'),
        ('SURFACE', 'Yüzey sınırları', 'Bağlı yüzeyde malzeme, dikiş ve keskinlik sınırlarında dur'),
    ])
    smart_angle: FloatProperty(name='Açı sınırı', description='Yüzey seçiminde komşu yüzler arasındaki en büyük açı',
                              default=math.radians(35), min=math.radians(1), max=math.radians(179),
                              subtype='ANGLE', options={'SKIP_SAVE'})


class KMTR_EditOperator:
    @classmethod
    def poll(cls, context):
        if not _single_edit_mesh(context):
            cls.poll_message_set('Tek bir mesh seçip Düzenleme Modu’na (Tab) geçin')
            return False
        return True


class KMTR_OT_hole_scan(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.hole_scan'
    bl_label = 'Eksik yüz / açıklık tara'
    bl_description = 'Tek yüzle bağlantılı açık sınır kenarlarını gruplar. Bilerek açık bırakılmış uçlar da çıkabilir; geometri veya UV değiştirilmez'

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        settings = context.window_manager.kmtr_settings
        regions = find_open_boundaries(bm, obj.matrix_world)
        _runtime['repair_report'] = None
        if settings.hole_active_material_only:
            regions = [r for r in regions if obj.active_material_index in r['materials']]
        _runtime['hole_scan'] = {'mesh': _mesh_key(obj.data), 'topology': _boundary_topology_key(bm),
                                 'regions': regions, 'stale': False}
        _runtime['hole_dirty'] = True; _runtime['hole_error'] = ''
        settings.hole_items.clear()
        for i, region in enumerate(regions):
            item = settings.hole_items.add()
            item.name = ('Olası delik ' if region['closed'] else 'Açık sınır ') + str(i+1)
            item.edge_count = region['edge_count']
            item.kind = 'Kapalı halka' if region['closed'] else 'Dallanan sınır' if region['branched'] else 'Sınır zinciri'
            names = [obj.material_slots[j].material.name if obj.material_slots[j].material else '(boş yuva)'
                     for j in region['materials'] if j < len(obj.material_slots)]
            item.material_text = ', '.join(names) or '(malzeme yok)'
        settings.hole_active_index = 0
        _holes_overlay_changed(settings, context)
        self.report({'INFO'}, str(len(regions)) + ' olası açıklık bulundu; otomatik onarım yapılmadı')
        _redraw()
        return {'FINISHED'}


class KMTR_OT_hole_focus(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.hole_focus'
    bl_label = 'Açıklığı seç ve yaklaş'
    bl_description = 'Listedeki açık sınır kenarlarını seçip görünümü o bölgeye odaklar; yüz oluşturmaz'
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty(default=0, min=0, options={'SKIP_SAVE'})
    focus_view: BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        report = _hole_report(obj, bm)
        if report is None or self.index >= len(report['regions']):
            self.report({'WARNING'}, 'Tarama yok veya geometri değişti; önce tekrar tarayın')
            return {'CANCELLED'}
        region = report['regions'][self.index]
        ids = [i for i in region['edges'] if not bm.edges[i].hide and not any(v.hide for v in bm.edges[i].verts)]
        if not ids:
            self.report({'WARNING'}, 'Bu sınır gizli. Önce yüzleri görünür yapıp tekrar deneyin')
            return {'CANCELLED'}
        context.tool_settings.mesh_select_mode = (False, True, False)
        for face in bm.faces: face.select_set(False)
        for edge in bm.edges: edge.select_set(False)
        for vert in bm.verts: vert.select_set(False)
        for i in ids: bm.edges[i].select_set(True)
        bm.select_flush_mode()
        context.window_manager.kmtr_settings.hole_active_index = self.index
        _flush(obj)
        if self.focus_view and not bpy.app.background and context.area and context.area.type == 'VIEW_3D':
            window_region = next(r for r in context.area.regions if r.type == 'WINDOW')
            with context.temp_override(area=context.area, region=window_region):
                bpy.ops.view3d.view_selected(use_all_regions=False)
        return {'FINISHED'}


class KMTR_OT_repair_preview(KMTR_EditOperator, bpy.types.Operator):
    bl_idname='kmtr.repair_preview'
    bl_label='Yama önizlemesi'
    bl_description='Çok kenarlı/eğri kapalı sınır için mor üçgen önerisi gösterir. Yalnız Uygula gerçek yüz ekler; Ctrl+Z geri alır'
    bl_options={'REGISTER','UNDO'}
    action: EnumProperty(items=[('BUILD','Önizle',''),('APPLY','Önizlemeyi uygula',''),('CANCEL','Önizlemeyi iptal et','')])
    scope: EnumProperty(items=[('ACTIVE','Listedeki açıklık',''),('ALL','Taramadaki uygun açıklıklar','')],default='ACTIVE')

    def execute(self,context):
        if self.action=='CANCEL':
            clear_repair_preview();return {'FINISHED'}
        obj,bm=_edit_mesh(context);settings=context.window_manager.kmtr_settings
        if self.action=='BUILD':
            clear_repair_preview()
            report=_hole_report(obj,bm)
            if report is None:
                self.report({'WARNING'},'Önce açıklıkları yeniden tarayın');return {'CANCELLED'}
            regions=report['regions']
            if self.scope=='ACTIVE':regions=regions[settings.hole_active_index:settings.hole_active_index+1]
            plan=build_repair_preview(obj,bm,regions,settings.patch_max_size)
            _runtime['repair_preview']=plan
            _runtime['patch_check']=True
            if not plan['patches']:
                self.report({'WARNING'},'Bu sınır için yama önerilemedi; nedenleri panelde');_redraw()
                return {'CANCELLED'}
            if not bpy.app.background:
                _runtime['patch_handler']=bpy.types.SpaceView3D.draw_handler_add(_draw_patch,(),'WINDOW','POST_VIEW')
                bpy.app.timers.register(_patch_tick,first_interval=.1)
            count=sum(len(p['triangles']) for p in plan['patches'])
            self.report({'INFO'},str(len(plan['patches']))+' yama / '+str(count)+' üçgen yalnız önizlemede; henüz yüz eklenmedi')
            _redraw();return {'FINISHED'}
        plan=_runtime['repair_preview']
        if not plan or not plan['patches']:
            self.report({'WARNING'},'Önce bir yama önizlemesi oluşturun');return {'CANCELLED'}
        if plan['state']!=_repair_state_key(obj,bm) or plan['max_size']!=settings.patch_max_size:
            clear_repair_preview('Model veya boyut sınırı değişti; yeniden önizleyin.')
            self.report({'WARNING'},_runtime['patch_error']);return {'CANCELLED'}
        created=[];old_edges=set(bm.edges)
        try:
            for patch in plan['patches']:
                for tri,uv_data in zip(patch['triangles'],patch['uv_data']):
                    face=bm.faces.new([bm.verts[i] for i in tri]);created.append(face)
                    face.material_index=patch['material_index']
                    for name,values in uv_data.items():
                        layer=bm.loops.layers.uv.get(name)
                        for loop,value in zip(face.loops,values):loop[layer].uv=value
                    face.normal_update()
        except Exception as exc:
            for face in created:
                if face.is_valid:bm.faces.remove(face)
            for edge in set(bm.edges)-old_edges:
                if not edge.link_faces:bm.edges.remove(edge)
            self.report({'ERROR'},'Yama uygulanamadı: '+str(exc));return {'CANCELLED'}
        count=len(created)
        bm.faces.index_update();bm.faces.ensure_lookup_table()
        _set_faces(context,bm,{f.index for f in created})
        _topology_edited(obj);bpy.ops.kmtr.hole_scan()
        self.report({'INFO'},str(count)+' önizlenen üçgen eklendi. Yeni UV’leri kontrol edin. Ctrl+Z: geri al')
        return {'FINISHED'}


class KMTR_OT_hole_repair(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.hole_repair'
    bl_label = 'Uygun küçük delikleri kapat'
    bl_description = 'Taramadaki küçük, görünür, düzlemsel üçgen/dörtgen açıklıkları kapatır. Büyük, karışık veya çakışan sınırları atlar. Gerçek geometri değişir; Ctrl+Z ile geri alınır'
    bl_options = {'REGISTER', 'UNDO'}
    preview_only: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    scope: EnumProperty(items=[('ALL', 'Taramadaki uygun açıklıklar', ''), ('ACTIVE', 'Listedeki açıklık', '')], default='ALL')

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        report = _hole_report(obj, bm)
        if report is None:
            self.report({'WARNING'}, 'Önce açıklıkları tekrar tarayın')
            return {'CANCELLED'}
        settings = context.window_manager.kmtr_settings
        regions = report['regions']
        if self.scope == 'ACTIVE':
            index = settings.hole_active_index
            regions = regions[index:index+1]
        plans = plan_small_hole_repairs(obj, bm, regions, settings.repair_max_size)
        reasons = {}
        for plan in plans:
            if not plan['ok']:reasons[plan['reason']] = reasons.get(plan['reason'],0)+1
        eligible = [p for p in plans if p['ok']]
        summary = {'mesh': _mesh_key(obj.data), 'eligible':len(eligible), 'filled':0, 'skipped':reasons}
        _runtime['repair_report'] = summary
        if self.preview_only:
            self.report({'INFO'}, str(len(eligible))+' uygun küçük açıklık; '+str(len(plans)-len(eligible))+' atlanacak')
            _redraw()
            return {'FINISHED'}
        if not eligible:
            self.report({'WARNING'}, 'Bu sınırlar için uygun küçük delik yok; atlama nedenleri panelde')
            _redraw()
            return {'CANCELLED'}
        count = 0
        new_faces = []
        for plan in eligible:
            created = bmesh.ops.holes_fill(bm, edges=plan['edges'], sides=4)['faces']
            new_faces.extend(created)
            for face in created:
                face.material_index = plan['material_index']
                same = opposite = 0
                for loop in face.loops:
                    for old in loop.edge.link_faces:
                        if old != face and old not in created:
                            other = next(l for l in old.loops if l.edge == loop.edge)
                            if other.vert == loop.vert:same += 1
                            else:opposite += 1
                if same > opposite:face.normal_flip()
                face.normal_update()
                face.select_set(True)
            count += len(created)
        summary['filled'] = count
        bm.faces.index_update(); bm.faces.ensure_lookup_table()
        _set_faces(context, bm, {f.index for f in new_faces if f.is_valid})
        _topology_edited(obj)
        bpy.ops.kmtr.hole_scan()
        _runtime['repair_report'] = summary
        self.report({'INFO'}, str(count)+' yeni yüz eklendi; '+str(len(plans)-len(eligible))+' sınır atlandı. Yeni yüzlerin UV’lerini kontrol edin. Ctrl+Z: geri al')
        return {'FINISHED'}


class KMTR_OT_merge_selected(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.merge_selected'
    bl_label = 'Seçili noktaları mesafeyle birleştir'
    bl_description = 'Yalnız seçili, görünür noktalar arasında çok yakın olanları kaynaklar; tüm modeli otomatik kaynaklamaz. Gerçek geometri değişir; Ctrl+Z ile geri alınır'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        verts = [v for v in bm.verts if v.select and not v.hide]
        if len(verts) < 2:
            self.report({'WARNING'}, 'Önce birleştirilecek en az iki noktayı seçin')
            return {'CANCELLED'}
        settings = context.window_manager.kmtr_settings
        scale = max(abs(v) for v in obj.matrix_world.to_scale())
        if scale <= 1e-12:
            self.report({'WARNING'}, 'Sıfır ölçekli nesnede birleştirme yapılamaz')
            return {'CANCELLED'}
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=verts, use_connected=settings.merge_connected_only,
                                dist=settings.merge_distance/scale)
        removed = before-len(bm.verts)
        if removed:
            _topology_edited(obj); bpy.ops.kmtr.hole_scan()
        self.report({'INFO'}, str(removed)+' nokta birleştirildi. Ctrl+Z: geri al')
        return {'FINISHED'}


class KMTR_OT_material_select(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.material_select'
    bl_label = 'Malzemeden yüz seç'
    bl_description = 'Etkin malzemenin görünen yüzlerini seç, mevcut seçime ekle veya seçimden çıkar'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('REPLACE', 'Seç', ''), ('ADD', 'Ekle', ''), ('SUBTRACT', 'Çıkar', '')])

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        if not obj.active_material:
            self.report({'WARNING'}, 'Önce listeden bir malzeme seçin')
            return {'CANCELLED'}
        target = {f.index for f in bm.faces if not f.hide and f.material_index == obj.active_material_index}
        current = {f.index for f in bm.faces if f.select and not f.hide}
        ids = target if self.action == 'REPLACE' else (current | target if self.action == 'ADD' else current - target)
        _set_faces(context, bm, ids)
        _flush(obj)
        return {'FINISHED'}


class KMTR_OT_material_color(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.material_color'
    bl_label = 'Yalnız görünüm rengi'
    bl_description = 'Malzemeye yalnız çalışma ekranında renk verir veya önizleme rengini kaldırır. Gerçek renk, shader, UV ve dışa aktarım değişmez'
    action: EnumProperty(items=[('APPLY', 'Bu malzemeyi önizlemede boya', ''),
                                ('RANDOM_ALL', 'Tüm malzemelere farklı rastgele renkler', ''),
                                ('CLEAR_ACTIVE', 'Bu malzemenin önizleme rengini kaldır', ''),
                                ('CLEAR_ALL', 'Tüm önizleme renklerini temizle', '')])
    seed: IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        obj = context.edit_object
        settings = context.window_manager.kmtr_settings
        if self.action == 'RANDOM_ALL':
            materials = {_mesh_key(slot.material):slot.material for slot in obj.material_slots if slot.material}
            if not materials:
                self.report({'WARNING'}, 'Bu mesh üzerinde malzeme yok')
                return {'CANCELLED'}
            rng = random.Random(None if self.seed < 0 else self.seed)
            hues = list(range(len(materials)));rng.shuffle(hues);base = rng.random()
            for key, hue in zip(materials, hues):
                rgb = colorsys.hsv_to_rgb((base+hue/len(materials))%1.0, rng.uniform(0.55,0.8), rng.uniform(0.8,1.0))
                _runtime['material_colors'][key] = rgb+(settings.material_preview_opacity,)
            settings.preview_mode = 'OFF'
        elif self.action == 'CLEAR_ALL':
            _runtime['material_colors'].clear()
        else:
            mat = obj.active_material
            if mat is None:
                self.report({'WARNING'}, 'Önce listeden bir malzeme seçin')
                return {'CANCELLED'}
            key = _mesh_key(mat)
            if self.action == 'APPLY':
                _runtime['material_colors'][key] = tuple(settings.material_preview_color) + (settings.material_preview_opacity,)
            else:
                _runtime['material_colors'].pop(key, None)
        _runtime['signature'] = None
        _preview_changed(settings, context)
        _redraw()
        return {'FINISHED'}


class KMTR_OT_remove_from_material(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.remove_from_material'
    bl_label = 'Seçili yüzleri malzemeden çıkar'
    bl_description = 'Seçili yüzlerden yalnız etkin kaynak malzemeye ait olanları hedef malzemeye taşır. Kaynak malzeme silinmez; Ctrl+Z ile geri alınır'
    bl_options = {'REGISTER', 'UNDO'}
    target: StringProperty(default='', options={'HIDDEN'})

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        token = self.target or context.window_manager.kmtr_settings.move_target
        try:
            destination = 0 if token == 'MAIN' else int(token.removeprefix('SLOT_'))
        except ValueError:
            self.report({'WARNING'}, 'Geçerli bir hedef malzeme seçin')
            return {'CANCELLED'}
        source = obj.active_material_index
        if not (0 <= source < len(obj.data.materials) and 0 <= destination < len(obj.data.materials)):
            self.report({'WARNING'}, 'Kaynak ve hedef malzeme yuvalarını kontrol edin')
            return {'CANCELLED'}
        if destination == source:
            self.report({'WARNING'}, 'Kaynak ve hedef aynı. Farklı bir hedef malzeme seçin')
            return {'CANCELLED'}
        faces = [f for f in bm.faces if f.select and not f.hide and f.material_index == source]
        if not faces:
            self.report({'WARNING'}, 'Seçimde kaynak malzemeye ait yüz yok; kaynak malzemeyi listeden seçin')
            return {'CANCELLED'}
        for face in faces:
            face.material_index = destination
        _flush(obj)
        target_mat = obj.data.materials[destination]
        self.report({'INFO'}, str(len(faces)) + ' yüz ' + (target_mat.name if target_mat else 'boş malzeme yuvası') + ' hedefine taşındı')
        return {'FINISHED'}


class KMTR_OT_smart_select(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.smart_select'
    bl_label = 'Akıllı seçim: bölgeye tıkla'
    bl_description = 'Bir yüzü tıklayarak bölgesini seç. Shift: ekle, Ctrl: seçimden çıkar. Atanmış malzemede ayrı parçalar da seçilir; yüzey modunda açı ve malzeme sınırları kullanılır'
    bl_options = {'REGISTER', 'UNDO'}
    face_index: IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})
    action: EnumProperty(items=[('REPLACE', 'Seç', ''), ('ADD', 'Ekle', ''), ('SUBTRACT', 'Çıkar', '')], default='REPLACE')

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        if not 0 <= self.face_index < len(bm.faces):
            self.report({'WARNING'}, 'Akıllı seçim düğmesine basıp modelde bir yüz tıklayın')
            return {'CANCELLED'}
        settings = context.window_manager.kmtr_settings
        material_index = bm.faces[self.face_index].material_index
        mode = settings.smart_mode
        if mode == 'AUTO' and (material_index >= len(obj.data.materials) or obj.data.materials[material_index] is None):
            mode = 'SURFACE'
        target = set(smart_face_indices(bm, self.face_index, mode=mode, angle=settings.smart_angle))
        if not target:
            return {'CANCELLED'}
        current = {f.index for f in bm.faces if f.select and not f.hide}
        ids = target if self.action == 'REPLACE' else (current | target if self.action == 'ADD' else current - target)
        _set_faces(context, bm, ids)
        bm.faces.active = bm.faces[self.face_index]
        if material_index < len(obj.data.materials):
            obj.active_material_index = material_index
        _flush(obj)
        self.report({'INFO'}, str(len(target)) + ' yüz: ' + ('malzeme grubu' if mode == 'MATERIAL' or mode == 'AUTO' and material_index != 0 else 'yüzey bölgesi'))
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.face_index >= 0:
            return self.execute(context)
        if context.area is None or context.area.type != 'VIEW_3D':
            return {'CANCELLED'}
        self._area = context.area
        self._object_key = context.edit_object.as_pointer()
        context.window.cursor_modal_set('CROSSHAIR')
        context.workspace.status_text_set('Akıllı seçim: modele sol tıkla · Shift: ekle · Ctrl: çıkar · Esc: iptal')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)

    def cancel(self, context):
        self._finish(context)

    def modal(self, context, event):
        if (event.type in {'ESC', 'RIGHTMOUSE'} or not _single_edit_mesh(context)
                or context.edit_object.as_pointer() != self._object_key):
            self._finish(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = next((r for r in self._area.regions if r.type == 'WINDOW'
                           and r.x <= event.mouse_x < r.x + r.width
                           and r.y <= event.mouse_y < r.y + r.height), None)
            if region is None:
                return {'RUNNING_MODAL'}
            x, y = event.mouse_x - region.x, event.mouse_y - region.y
            from bpy_extras import view3d_utils
            obj, bm = _edit_mesh(context)
            with context.temp_override(area=self._area, region=region):
                region_3d = context.region_data
                origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, (x, y))
                direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, (x, y))
            inverse = obj.matrix_world.inverted_safe()
            index = raycast_face_index(bm, inverse @ origin, inverse.to_3x3() @ direction)
            if index is None:
                self.report({'INFO'}, 'Modelde görünür bir yüz tıklayın; Esc ile iptal edebilirsiniz')
                return {'RUNNING_MODAL'}
            self.face_index = index
            self.action = 'SUBTRACT' if event.ctrl else 'ADD' if event.shift else 'REPLACE'
            self._finish(context)
            return self.execute(context)
        return {'PASS_THROUGH'}


class KMTR_OT_red_action(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.red_action'
    bl_label = 'Kırmızı yüzler'
    bl_description = 'Kırmızı işaretleri temizle veya yalnız kırmızı yüzleri 1. ana malzemeye taşı. İşaret rengi geçicidir; aktarma Ctrl+Z ile geri alınır'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('TRANSFER', 'Kırmızıları ana malzemeye taşı', ''), ('CLEAR', 'Kırmızıları temizle', ''),
                                ('MARK_SELECTION', 'Seçilileri kırmızı işaretle', 'Normal seçim aracıyla seçilen yüzleri geçici kırmızı işaretlere ekle'),
                                ('UNMARK_SELECTION', 'Seçilileri kırmızıdan çıkar', 'Seçili yüzlerin yalnız kırmızı işaretini kaldır')])

    def execute(self, context):
        if self.action == 'CLEAR':
            clear_red_marks()
            return {'FINISHED'}
        obj, bm = _edit_mesh(context)
        if self.action in {'MARK_SELECTION', 'UNMARK_SELECTION'}:
            selected = {f.index for f in bm.faces if f.select and not f.hide}
            if not selected:
                self.report({'WARNING'}, 'Önce seçim aracıyla yüzleri seçin')
                return {'CANCELLED'}
            mark_red_faces(context, selected, erase=self.action == 'UNMARK_SELECTION')
            return {'FINISHED'}
        ids = red_face_indices(obj, bm)
        if not ids or not obj.data.materials:
            self.report({'WARNING'}, 'Önce Ctrl+sol tık ile turuncu yüzleri kırmızı işaretleyin')
            return {'CANCELLED'}
        originals = _runtime['red_marks']['faces']
        if any(bm.faces[i].material_index != originals[i] for i in ids):
            self.report({'WARNING'}, 'İşaretlemeden sonra malzeme ataması değişti; işaretleri temizleyip yeniden işaretleyin')
            return {'CANCELLED'}
        if any(bm.faces[i].hide for i in ids):
            self.report({'WARNING'}, 'Kırmızı yüzlerden bazıları gizli. Önce görünür yapın veya işaretleri temizleyin')
            return {'CANCELLED'}
        for i in ids:
            bm.faces[i].material_index = 0
        selected = {f.index for f in bm.faces if f.select and not f.hide} - ids
        _set_faces(context, bm, selected)
        clear_red_marks()
        _flush(obj)
        self.report({'INFO'}, str(len(ids)) + ' kırmızı yüz 1. ana malzemeye taşındı')
        return {'FINISHED'}


class KMTR_OT_red_paint(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.red_paint'
    bl_label = 'Ctrl ile kırmızı işaretle'
    bl_description = 'Ctrl+sol tık: yüzün kırmızı işaretini aç/kapat. Sürüklerken ilk yüz kırmızıysa sil, değilse ekle. Ctrl+Shift: daima sil'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return (_single_edit_mesh(context) and context.area is not None and context.area.type == 'VIEW_3D'
                and context.region is not None and context.region.type == 'WINDOW'
                and context.window_manager.kmtr_settings.red_mode)

    def _pick(self, context, x, y):
        from bpy_extras import view3d_utils
        region = next((r for r in self._area.regions if r.type == 'WINDOW'
                       and r.x <= x < r.x+r.width and r.y <= y < r.y+r.height), None)
        if region is None:
            return None
        if any(r.type in {'UI', 'TOOLS'} and r.width > 1 and r.x <= x < r.x+r.width
               and r.y <= y < r.y+r.height for r in self._area.regions):
            return None
        with context.temp_override(area=self._area, region=region):
            view = context.region_data
            point = (x-region.x, y-region.y)
            origin = view3d_utils.region_2d_to_origin_3d(region, view, point)
            direction = view3d_utils.region_2d_to_vector_3d(region, view, point)
        hit = self._tree.ray_cast(self._inverse @ origin, (self._inverse.to_3x3() @ direction).normalized())
        return self._face_map[hit[2]] if hit[2] is not None else None

    def _paint(self, context, x, y):
        dx, dy = x-self._last[0], y-self._last[1]
        steps = max(1, math.ceil(math.hypot(dx, dy)/8))
        hits = set()
        for step in range(1, steps+1):
            i = self._pick(context, self._last[0]+dx*step/steps, self._last[1]+dy*step/steps)
            if i is not None:
                hits.add(i)
        if hits:
            mark_red_faces(context, hits, erase=self._erase)
        self._last = (x, y)

    def invoke(self, context, event):
        from copy import deepcopy
        from mathutils.bvhtree import BVHTree
        obj, bm = _edit_mesh(context)
        faces = [f for f in bm.faces if not f.hide]
        if not faces:
            return {'CANCELLED'}
        self._area = context.area
        self._object_key = obj.as_pointer()
        self._inverse = obj.matrix_world.inverted_safe()
        self._face_map = [f.index for f in faces]
        self._tree = BVHTree.FromPolygons([v.co.copy() for v in bm.verts], [tuple(v.index for v in f.verts) for f in faces])
        self._before = deepcopy(_runtime['red_marks'])
        first_face = self._pick(context, event.mouse_x, event.mouse_y)
        self._erase = red_stroke_erases(obj, bm, first_face, force_erase=event.shift)
        self._last = (event.mouse_x, event.mouse_y)
        self._paint(context, event.mouse_x, event.mouse_y)
        context.workspace.status_text_set(('Kırmızı işaret silme' if self._erase else 'Kırmızı işaret ekleme') + ' · sol tuşu bırak: bitir · Esc: bu çizgiyi iptal et')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _single_edit_mesh(context) or context.edit_object.as_pointer() != self._object_key:
            clear_red_marks()
            context.workspace.status_text_set(None)
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            from copy import deepcopy
            _runtime['red_marks'] = deepcopy(self._before)
            mark_red_faces(context, ())
            context.workspace.status_text_set(None)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE' or event.type in {'LEFT_CTRL', 'RIGHT_CTRL'} and event.value == 'RELEASE':
            context.workspace.status_text_set(None)
            return {'FINISHED'}
        if event.type == 'MOUSEMOVE':
            self._paint(context, event.mouse_x, event.mouse_y)
        return {'RUNNING_MODAL'}


class KMTR_OT_selection_action(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.selection_action'
    bl_label = 'Seçimi düzenle'
    bl_description = 'Yüz seçimini temizle, tersine çevir, bir halka büyüt veya küçült'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('CLEAR', 'Temizle', ''), ('INVERT', 'Ters çevir', ''),
                                ('GROW', 'Büyüt', ''), ('SHRINK', 'Küçült', '')])

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        context.tool_settings.mesh_select_mode = (False, False, True)
        if self.action in {'CLEAR', 'INVERT'}:
            ids = {f.index for f in bm.faces if not f.hide and not f.select} if self.action == 'INVERT' else set()
            _set_faces(context, bm, ids)
        elif self.action == 'GROW':
            bpy.ops.mesh.select_more(use_face_step=True)
        else:
            bpy.ops.mesh.select_less(use_face_step=True)
        _flush(obj)
        return {'FINISHED'}


class KMTR_OT_brush(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.brush'
    bl_label = 'Yüz seçim fırçası'
    bl_description = 'Sol tuşla sürükleyerek seçime ekle veya çıkar. Boyutu panelden değiştirin. X-Ray açıksa arkadaki yüzler de seçilebilir'
    action: EnumProperty(items=[('ADD', 'Fırça +', 'Yüzleri seçime ekle'), ('SUB', 'Fırça −', 'Yüzleri seçimden çıkar'),
                                ('BOX', 'Kutu seçimine dön', 'Dairesel fırçadan çık ve kutu seçimini etkinleştir')])

    def execute(self, context):
        context.tool_settings.mesh_select_mode = (False, False, True)
        area = context.area
        if area is None or area.type != 'VIEW_3D':
            return {'CANCELLED'}
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with context.temp_override(area=area, region=region):
            if self.action == 'BOX':
                bpy.ops.wm.tool_set_by_id(name='builtin.select_box')
            else:
                bpy.ops.wm.tool_set_by_id(name='builtin.select_circle')
                tool = context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=False)
                props = tool.operator_properties('view3d.select_circle')
                props.mode = self.action
                props.radius = context.window_manager.kmtr_settings.brush_radius
        return {'FINISHED'}


class KMTR_OT_selection_memory(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.selection_memory'
    bl_label = 'Seçim hafızası'
    bl_description = 'Seçimi geçici hafızaya al veya geri çağır; topoloji değişirse eski seçim uygulanmaz'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('STORE', 'Seçimi sakla', ''), ('RESTORE', 'Geri çağır', '')])

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        key = _mesh_key(obj.data)
        if self.action == 'STORE':
            ids = {f.index for f in bm.faces if f.select and not f.hide}
            _runtime['memory'][key] = (_topology_key(bm), ids)
            self.report({'INFO'}, str(len(ids)) + ' yüz hafızaya alındı')
        else:
            stored = _runtime['memory'].get(key)
            if stored is None:
                self.report({'WARNING'}, 'Bu mesh için saklanmış seçim yok')
                return {'CANCELLED'}
            if stored[0] != _topology_key(bm):
                self.report({'WARNING'}, 'Topoloji değişti; yanlış yüz seçmemek için geri çağırma iptal edildi')
                return {'CANCELLED'}
            _set_faces(context, bm, stored[1])
            _flush(obj)
        return {'FINISHED'}


class KMTR_OT_isolate(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.isolate'
    bl_label = 'Yüzleri yalıt'
    bl_description = 'Seçim dışını gizle veya önceki görünürlüğe dön; önceden gizli yüzler korunur'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('HIDE', 'Diğerlerini gizle', ''), ('RESTORE', 'Gizlemeyi geri al', ''),
                                ('REVEAL', 'Tüm gizlileri göster', '')])

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        if self.action == 'HIDE':
            if any(elements.layers.int.get(name) is not None for elements, name in zip((bm.verts, bm.edges, bm.faces), _HIDDEN_LAYERS)):
                self.report({'WARNING'}, 'Önce önceki gizlemeyi geri alın')
                return {'CANCELLED'}
            if not any(f.select and not f.hide for f in bm.faces):
                self.report({'WARNING'}, 'Önce en az bir yüz seçin')
                return {'CANCELLED'}
            if not any(not f.hide and not f.select for f in bm.faces):
                self.report({'INFO'}, 'Gizlenecek başka görünür yüz yok')
                return {'CANCELLED'}
            _store_hidden(bm)
            for face in bm.faces:
                if not face.select:
                    face.hide_set(True)
        elif self.action == 'RESTORE':
            if _isolation_layers(bm) is None:
                self.report({'WARNING'}, 'Geri alınacak gizleme yok')
                return {'CANCELLED'}
            selected = {f.index for f in bm.faces if f.select and not f.hide}
            if not _restore_hidden(bm):
                self.report({'WARNING'}, 'Topoloji değişti. Gerekirse “Tüm gizlileri göster” düğmesini kullanın')
                return {'CANCELLED'}
            _set_faces(context, bm, selected)
        else:
            bpy.ops.mesh.reveal(select=False)
            _drop_isolation_layers(bm)
        _flush(obj)
        return {'FINISHED'}


class KMTR_OT_preview(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.preview'
    bl_label = 'Geçici siyah önizleme'
    bl_description = 'Sadece ekrana siyah katman çizer. Malzeme, UV, renk, doku ve dışa aktarılan veri değişmez'
    mode: EnumProperty(items=PREVIEW_ITEMS)

    @classmethod
    def poll(cls, context):
        return context.window_manager is not None

    def execute(self, context):
        if self.mode != 'OFF' and not _single_edit_mesh(context):
            self.report({'WARNING'}, 'Tek bir mesh ile Düzenleme Modu’na geçin')
            return {'CANCELLED'}
        if self.mode == 'OFF':
            _runtime['material_colors'].clear()
        context.window_manager.kmtr_settings.preview_mode = self.mode
        return {'FINISHED'}


class KMTR_OT_assign_material(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.assign_material'
    bl_label = 'Seçime malzemeyi ata'
    bl_description = 'Etkin malzemeyi seçili yüzlere gerçekten atar. Bu işlem dışa aktarılacak malzeme atamasını değiştirir'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        selected = [f for f in bm.faces if f.select and not f.hide]
        if not obj.active_material or not selected:
            self.report({'WARNING'}, 'Bir malzeme ve en az bir yüz seçin')
            return {'CANCELLED'}
        for face in selected:
            face.material_index = obj.active_material_index
        _flush(obj)
        self.report({'INFO'}, str(len(selected)) + ' yüze ' + obj.active_material.name + ' atandı')
        return {'FINISHED'}


class KMTR_OT_new_material(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.new_material'
    bl_label = 'Oluştur ve seçime ata'
    bl_description = 'Yazılan adda malzeme oluşturur ve seçime atar; aynı ad varsa mevcut malzemeyi kullanır'
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty(name='Malzeme adı', default='')

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        selected = [f for f in bm.faces if f.select and not f.hide]
        name = (self.name or context.window_manager.kmtr_settings.new_name).strip()
        if not selected or not name:
            self.report({'WARNING'}, 'En az bir yüz seçin ve malzeme adı yazın')
            return {'CANCELLED'}
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
        slot = next((i for i, item in enumerate(obj.data.materials) if item == mat), None)
        if slot is None:
            obj.data.materials.append(mat)
            slot = len(obj.data.materials) - 1
        obj.active_material_index = slot
        for face in selected:
            face.material_index = slot
        _flush(obj)
        self.report({'INFO'}, str(len(selected)) + ' yüze ' + mat.name + ' atandı')
        return {'FINISHED'}


def _op(layout, operator, text, **props):
    button = layout.operator(operator, text=text)
    for name, value in props.items():
        setattr(button, name, value)
    return button


class KMTR_UL_holes(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name)
        row.label(text=str(item.edge_count) + ' kenar')
        row.operator('kmtr.hole_focus', text='', icon='VIEWZOOM').index = index


class KMTR_PT_holes(bpy.types.Panel):
    bl_label = 'Olası eksik yüzler / açıklıklar'
    bl_idname = 'KMTR_PT_holes'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Kolay Malzeme'
    bl_order = -1

    def draw(self, context):
        layout = self.layout
        if not _single_edit_mesh(context):
            layout.label(text='Tek bir mesh ile Düzenleme Modu’na geçin.')
            return
        obj = context.edit_object
        settings = context.window_manager.kmtr_settings
        layout.label(text='Açık sınırları bulur; yüz oluşturmaz.')
        layout.label(text='Her açıklık eksik yüz olmayabilir.', icon='INFO')
        layout.prop(settings, 'hole_active_material_only')
        if settings.hole_active_material_only:
            layout.label(text='Malzeme: ' + (obj.active_material.name if obj.active_material else '(boş)'))
        layout.operator('kmtr.hole_scan', text='Eksik yüz / açıklık tara', icon='VIEWZOOM')
        report = _runtime['hole_scan']
        if report is None or report['mesh'] != _mesh_key(obj.data):
            return
        if report['stale']:
            layout.label(text='Geometri değişti; tekrar tarayın.', icon='ERROR')
            return
        layout.label(text=str(len(report['regions'])) + ' olası açıklık bulundu')
        if settings.hole_items:
            layout.template_list('KMTR_UL_holes', '', settings, 'hole_items', settings, 'hole_active_index', rows=5)
            index = min(settings.hole_active_index, len(settings.hole_items)-1)
            item = settings.hole_items[index]
            layout.label(text=item.kind + ' · ' + str(item.edge_count) + ' kenar')
            layout.label(text='Malzeme: ' + item.material_text)
            hidden = report['regions'][index]['hidden_edges']
            if hidden:
                layout.label(text=str(hidden) + ' sınır kenarı gizli', icon='INFO')
            op = layout.operator('kmtr.hole_focus', text='Listedeki açıklığı seç ve yaklaş', icon='VIEWZOOM')
            op.index = index
        layout.prop(settings, 'hole_overlay')
        box=layout.box()
        box.label(text='Önizlemeli onarım (önerilen)',icon='HIDE_OFF')
        box.label(text='Çok kenarlı / eğri kapalı açıklıklar')
        box.label(text='Uygulamadan önce açıklığı kontrol edin.')
        box.prop(settings,'patch_max_size')
        op=box.operator('kmtr.repair_preview',text='Listedeki açıklığı önizle')
        op.action='BUILD';op.scope='ACTIVE'
        op=box.operator('kmtr.repair_preview',text='Tüm uygun açıklıkları önizle')
        op.action='BUILD';op.scope='ALL'
        proposal=_runtime['repair_preview']
        if proposal and proposal['mesh']==_mesh_key(obj.data):
            count=sum(len(p['triangles']) for p in proposal['patches'])
            box.label(text=str(len(proposal['patches']))+' yama · '+str(count)+' önerilen üçgen')
            box.label(text='Henüz geometri değiştirilmedi.')
            box.prop(settings,'patch_opacity',slider=True)
            row=box.row(align=True)
            row.operator('kmtr.repair_preview',text='Uygula',icon='CHECKMARK').action='APPLY'
            row.operator('kmtr.repair_preview',text='İptal',icon='X').action='CANCEL'
            for reason,count in proposal['skipped'].items():box.label(text=str(count)+' atlandı: '+reason)
        if _runtime['patch_error']:box.label(text=_runtime['patch_error'],icon='ERROR')
        box.label(text='Uygula gerçek yüz ekler. Ctrl+Z: geri al.')
        box = layout.box()
        box.label(text='Sıkı küçük delik modu · Ctrl+Z')
        box.label(text='Yalnız uygun 3–4 kenarlı açıklıklar.')
        box.prop(settings, 'repair_max_size')
        op = box.operator('kmtr.hole_repair', text='Onarılabilirleri kontrol et')
        op.preview_only = True; op.scope = 'ALL'
        op = box.operator('kmtr.hole_repair', text='Uygun küçük delikleri kapat')
        op.preview_only = False; op.scope = 'ALL'
        if settings.hole_items:
            op = box.operator('kmtr.hole_repair', text='Yalnız listedeki açıklığı onar')
            op.preview_only = False; op.scope = 'ACTIVE'
        box.label(text='Bu düğmeler gerçek yüz oluşturur.')
        summary = _runtime['repair_report']
        if summary and summary['mesh'] == _mesh_key(obj.data):
            box.label(text=str(summary['eligible'])+' uygun · '+str(summary['filled'])+' yüz eklendi')
            for reason, count in summary['skipped'].items():
                box.label(text=str(count)+' atlandı: '+reason)
        box = layout.box()
        box.label(text='Yalnız seçili noktaları birleştir')
        box.prop(settings, 'merge_distance')
        box.prop(settings, 'merge_connected_only')
        box.operator('kmtr.merge_selected')
        box.label(text='Gerçek geometri değişir. Ctrl+Z: geri al.')
        if _runtime['hole_error']:
            layout.label(text=_runtime['hole_error'], icon='ERROR')


class KMTR_PT_panel(bpy.types.Panel):
    bl_label = 'Kolay Malzeme TR'
    bl_idname = 'KMTR_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Kolay Malzeme'

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.kmtr_settings
        layout.label(text='Karartma yalnızca ekrandadır.', icon='INFO')
        layout.label(text='Malzeme ve dışa aktarım değişmez.')
        if not _single_edit_mesh(context):
            layout.separator()
            layout.label(text='Tek bir mesh seçin, Tab ile')
            layout.label(text='Düzenleme Modu’na geçin.')
            _op(layout, 'kmtr.preview', 'Normal görünüme dön', mode='OFF')
            return
        obj, bm = _edit_mesh(context)
        box = layout.box()
        box.label(text='1 · Malzemeden seçim', icon='MATERIAL')
        box.template_list('MATERIAL_UL_matslots', '', obj, 'material_slots', obj, 'active_material_index', rows=4)
        row = box.row(align=True)
        _op(row, 'kmtr.material_select', 'Seç', action='REPLACE')
        _op(row, 'kmtr.material_select', '+ Ekle', action='ADD')
        _op(row, 'kmtr.material_select', 'Seçimden çıkar', action='SUBTRACT')
        box = layout.box()
        box.label(text='Yalnız görünüm için malzeme rengi')
        row = box.row(); row.scale_y = 1.25
        _op(row, 'kmtr.material_color', 'Hepsine farklı rastgele renk', action='RANDOM_ALL', seed=-1)
        box.label(text='Malzeme: ' + (obj.active_material.name if obj.active_material else '(seçilmedi)'))
        box.prop(settings, 'material_preview_color')
        box.prop(settings, 'material_preview_opacity', slider=True)
        _op(box, 'kmtr.material_color', 'Bu malzemeyi önizlemede boya', action='APPLY')
        _op(box, 'kmtr.material_color', 'Bu malzemenin rengini kaldır', action='CLEAR_ACTIVE')
        _op(box, 'kmtr.material_color', 'Tüm önizleme renklerini temizle', action='CLEAR_ALL')
        box.label(text='Gerçek renk değişmez; dışa aktarılmaz.')
        box = layout.box()
        box.label(text='Kırmızı işaretle → ana malzemeye taşı')
        _op(box, 'kmtr.red_action', 'Seçilileri kırmızı işaretle', action='MARK_SELECTION')
        _op(box, 'kmtr.red_action', 'Seçilileri kırmızıdan çıkar', action='UNMARK_SELECTION')
        box.prop(settings, 'red_fill_opacity', slider=True)
        box.prop(settings, 'red_mode')
        box.label(text='Ctrl + sol tık: işaretle / kaldır')
        box.label(text='Ctrl + Shift + sol tık: işareti sil')
        stored = _runtime['red_marks']
        count = len(stored['faces']) if stored and stored['mesh'] == _mesh_key(obj.data) else 0
        box.label(text=str(count) + ' kırmızı yüz · renk geçicidir')
        clear_row = box.row()
        clear_row.scale_y = 1.25
        clear_row.operator('kmtr.red_action', text='Clear — tüm kırmızıları iptal et', icon='X').action = 'CLEAR'
        _op(box, 'kmtr.red_action', 'Kırmızıları 1. ana malzemeye taşı', action='TRANSFER')
        if _runtime['red_error']:
            box.label(text=_runtime['red_error'], icon='ERROR')
        box = layout.box()
        box.label(text='Malzemeden yüz çıkar / taşı')
        box.label(text='Kaynak: ' + (obj.active_material.name if obj.active_material else '(boş yuva)'))
        box.prop(settings, 'move_target')
        _op(box, 'kmtr.remove_from_material', 'Seçili yüzleri malzemeden çıkar', target=settings.move_target)
        box.label(text='Seçili yüzler hedefe taşınır. Ctrl+Z: geri al.')
        box = layout.box()
        box.label(text='Akıllı bölge seçimi')
        box.prop(settings, 'smart_mode')
        if settings.smart_mode != 'MATERIAL':
            box.prop(settings, 'smart_angle')
        _op(box, 'kmtr.smart_select', 'Akıllı seçim: bölgeye tıkla')
        box.label(text='Shift: ekle · Ctrl: seçimden çıkar')
        box = layout.box()
        box.label(text='2 · Seçimi düzelt')
        count = sum(f.select and not f.hide for f in bm.faces)
        box.label(text=str(count) + ' yüz seçili')
        row = box.row(align=True)
        _op(row, 'kmtr.brush', 'Fırça +', action='ADD')
        _op(row, 'kmtr.brush', 'Fırça −', action='SUB')
        box.prop(settings, 'brush_radius', slider=True)
        _op(box, 'kmtr.brush', 'Kutu seçimine dön', action='BOX')
        row = box.row(align=True)
        _op(row, 'kmtr.selection_action', 'Büyüt', action='GROW')
        _op(row, 'kmtr.selection_action', 'Küçült', action='SHRINK')
        row = box.row(align=True)
        _op(row, 'kmtr.selection_action', 'Ters çevir', action='INVERT')
        _op(row, 'kmtr.selection_action', 'Temizle', action='CLEAR')
        row = box.row(align=True)
        _op(row, 'kmtr.selection_memory', 'Seçimi sakla', action='STORE')
        _op(row, 'kmtr.selection_memory', 'Geri çağır', action='RESTORE')
        box = layout.box()
        box.label(text='3 · Geçici siyah önizleme')
        for text, mode in [('Seçileni karart', 'SELECTED'), ('Diğer yüzleri karart', 'OTHERS'),
                           ('Bu malzemeyi karart', 'MATERIAL'), ('Diğer malzemeleri karart', 'OTHER_MATERIALS')]:
            button = box.operator('kmtr.preview', text=text, depress=settings.preview_mode == mode)
            button.mode = mode
        box.prop(settings, 'opacity', slider=True)
        _op(box, 'kmtr.preview', 'Normal görünüme dön', mode='OFF')
        if _runtime['error']:
            box.label(text=_runtime['error'], icon='ERROR')
        box = layout.box()
        box.label(text='4 · İnce çalışma için gizle')
        row = box.row(align=True)
        _op(row, 'kmtr.isolate', 'Diğerlerini gizle', action='HIDE')
        _op(row, 'kmtr.isolate', 'Geri al', action='RESTORE')
        _op(box, 'kmtr.isolate', 'Tüm gizlileri göster', action='REVEAL')
        box = layout.box()
        box.label(text='5 · Gerçek malzeme ataması')
        _op(box, 'kmtr.assign_material', 'Seçime listedeki malzemeyi ata')
        box.prop(settings, 'new_name')
        _op(box, 'kmtr.new_material', 'Oluştur ve seçime ata')
        box.label(text='Atama işlemleri Ctrl+Z ile geri alınır.')


def clear_runtime():
    clear_repair_preview()
    _stop_hole_overlay()
    _runtime['hole_scan'] = None
    _runtime['repair_report'] = None
    _runtime['material_colors'].clear()
    _stop_preview()
    clear_red_marks()
    settings = getattr(bpy.context.window_manager, 'kmtr_settings', None)
    if settings is not None:
        settings.preview_mode = 'OFF'
        settings.hole_items.clear()
    # Visibility backups travel with BMesh undo states, not mutable object names.
    seen = set()
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        key = _mesh_key(obj.data)
        if key in seen:
            continue
        seen.add(key)
        if obj.data.is_editmode:
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
            bm.verts.index_update(); bm.edges.index_update(); bm.faces.index_update()
            selected = {f.index for f in bm.faces if f.select and not f.hide}
            if _restore_hidden(bm):
                _set_faces(bpy.context, bm, selected)
                _flush(obj)
        else:
            bm = bmesh.new()
            try:
                bm.from_mesh(obj.data)
                bm.verts.index_update(); bm.edges.index_update(); bm.faces.index_update()
                bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
                if _restore_hidden(bm):
                    bm.to_mesh(obj.data)
            finally:
                bm.free()
    _runtime['memory'].clear()


@persistent
def _on_load_pre(*args):
    clear_runtime()


@persistent
def _on_load_post(*args):
    _stop_preview()
    settings = getattr(bpy.context.window_manager, 'kmtr_settings', None)
    if settings:
        settings.preview_mode = 'OFF'


@persistent
def _on_update(*args):
    _runtime['patch_check'] = True
    _runtime['geometry_dirty'] = True
    _runtime['red_geometry_dirty'] = True
    _runtime['hole_dirty'] = True


CLASSES = (KMTR_HoleItem, KMTR_Settings, KMTR_OT_hole_scan, KMTR_OT_hole_focus, KMTR_OT_repair_preview, KMTR_OT_hole_repair, KMTR_OT_merge_selected,
           KMTR_OT_material_select, KMTR_OT_material_color, KMTR_OT_remove_from_material, KMTR_OT_smart_select,
           KMTR_OT_red_action, KMTR_OT_red_paint,
           KMTR_OT_selection_action, KMTR_OT_brush,
           KMTR_OT_selection_memory, KMTR_OT_isolate, KMTR_OT_preview,
           KMTR_OT_assign_material, KMTR_OT_new_material, KMTR_UL_holes, KMTR_PT_holes, KMTR_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.kmtr_settings = PointerProperty(type=KMTR_Settings, options={'SKIP_SAVE'})
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig:
        names = ['3D View', '3D View Tool: Select Box', '3D View Tool: Select Circle',
                 '3D View Tool: Select Lasso', '3D View Tool: Tweak']
        for name in names:
            keymap = keyconfig.keymaps.new(name=name, space_type='VIEW_3D', region_type='WINDOW', tool=name != '3D View')
            for shift in (False, True):
                item = keymap.keymap_items.new('kmtr.red_paint', 'LEFTMOUSE', 'PRESS', ctrl=True, shift=shift, head=True)
                _runtime['keymaps'].append((keymap, item))
    for collection, handler in [(bpy.app.handlers.load_pre, _on_load_pre),
                                (bpy.app.handlers.load_post, _on_load_post),
                                (bpy.app.handlers.undo_post, _on_update),
                                (bpy.app.handlers.depsgraph_update_post, _on_update)]:
        if handler not in collection:
            collection.append(handler)


def unregister():
    clear_runtime()
    for keymap, item in _runtime['keymaps']:
        keymap.keymap_items.remove(item)
    _runtime['keymaps'].clear()
    for collection, handler in [(bpy.app.handlers.load_pre, _on_load_pre),
                                (bpy.app.handlers.load_post, _on_load_post),
                                (bpy.app.handlers.undo_post, _on_update),
                                (bpy.app.handlers.depsgraph_update_post, _on_update)]:
        if handler in collection:
            collection.remove(handler)
    if hasattr(bpy.types.WindowManager, 'kmtr_settings'):
        del bpy.types.WindowManager.kmtr_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
