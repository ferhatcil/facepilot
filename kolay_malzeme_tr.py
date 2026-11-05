bl_info = {
    'name': 'Kolay Malzeme TR',
    'author': 'Codex',
    'version': (1, 10, 0),
    'blender': (4, 2, 0),
    'location': '3D View > N > FacePilot',
    'description': 'Türkçe yüz seçimi, malzeme atama ve dışa aktarılmayan karartma önizlemesi',
    'category': 'Mesh',
}

import bpy
import bmesh
import math
import random
import colorsys
import re
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty


# Preview and selection memory are deliberately NOT mesh/material attributes.
_runtime = {
    'memory': {}, 'handler': None, 'shader': None,
    'batch': None, 'positions': [], 'signature': None, 'mesh_key': None,
    'geometry_dirty': True, 'gpu_dirty': True, 'error': '',
    'material_colors': {}, 'color_positions': [], 'color_batches': [],
    'target_items': {},
    'material_visibility_rows': None,
    'red_marks': None, 'red_handler': None, 'red_shader': None, 'red_batch': None,
    'red_positions': [], 'red_signature': None, 'red_dirty': True, 'red_error': '',
    'red_geometry_dirty': True,
    'red_line_positions': [], 'red_line_shader': None, 'red_line_batch': None,
    'keymaps': [],
    'hole_scan': None, 'hole_handler': None, 'hole_shader': None, 'hole_batch': None,
    'hole_positions': [], 'hole_dirty': True, 'hole_gpu_dirty': True, 'hole_error': '',
    'repair_report': None,
    'ignored_holes': {},
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


UI_EN = {
    'Göster':'Show','Gizle':'Hide','Göster / gizle':'Show / hide','Malzemeyi göster/gizle':'Show/hide material',
    'Malzeme gizlendi':'Material hidden','Malzeme gösterildi':'Material shown',
    'Geçerli bir malzeme yuvası seçin':'Choose a valid material slot',
    'Bu malzemeye atanmış yüz yok':'No faces are assigned to this material',
    'Göz simgesi: malzemeyi göster/gizle':'Eye icon: show/hide material','Görünür':'Visible',
    'Seçim':'Selection', 'Akıllı seçim':'Smart selection', 'Görsel önizleme':'Visual preview',
    'Kırmızı düzeltme':'Red corrections', 'Malzeme atama':'Material assignment',
    'Açıklıklar ve onarım':'Openings & repair', 'Gelişmiş onarım':'Advanced repair',
    'Geçici görünüm':'Viewport only', 'Gerçek atama':'Changes material assignments',
    'Seçimi yalıt':'Isolate selection', 'Gizlemeyi geri al':'Restore visibility',
    'Tüm gizlileri göster':'Reveal all hidden faces', 'Normal görünüme dön':'Reset visual previews',
    'Malzemeden yüz seç':'Select faces by material', 'Seç':'Select', '+ Ekle':'Add',
    'Seçimden çıkar':'Deselect', 'Temizle':'Clear selection', 'Büyüt':'Grow', 'Küçült':'Shrink',
    'Ters çevir':'Invert', 'Seçimi sakla':'Store selection', 'Geri çağır':'Recall selection',
    'Fırça +':'Brush +', 'Fırça −':'Brush −', 'Kutu seçimine dön':'Box select tool',
    'Fırça boyutu':'Brush radius', 'Yöntem':'Method', 'Açı sınırı':'Angle limit',
    'Otomatik':'Automatic', 'Aynı malzeme':'Same material', 'Yüzey sınırları':'Surface boundaries',
    'Akıllı seçim: bölgeye tıkla':'Pick a region', 'Shift: ekle · Ctrl: çıkar':'Shift: add · Ctrl: subtract',
    'Hepsine farklı rastgele renk':'Randomize all material colors',
    'Tüm malzemelere farklı rastgele renkler':'Random colors for all materials',
    'Önizleme rengi':'Preview color', 'Renk yoğunluğu':'Color opacity',
    'Bu malzemeyi önizlemede boya':'Apply preview color', 'Bu malzemenin rengini kaldır':'Clear active material color',
    'Tüm önizleme renklerini temizle':'Clear all preview colors', 'Yalnız görünüm rengi':'Viewport color',
    'Seçileni karart':'Darken selected', 'Diğer yüzleri karart':'Darken unselected',
    'Bu malzemeyi karart':'Darken active material', 'Diğer malzemeleri karart':'Darken other materials',
    'Karartma':'Dark opacity', 'Kapalı':'Off', 'Geçici siyah önizleme':'Temporary dark preview',
    'Renkler ve işaretler dışa aktarılmaz.':'Colors and marks are not exported.',
    'Seçilileri kırmızı işaretle':'Mark selected faces', 'Seçilileri kırmızıdan çıkar':'Unmark selected faces',
    'İç dolgu':'Fill opacity', 'Ctrl ile kırmızı işaretle':'Ctrl red marking',
    'Ctrl + sol tık: işaretle / kaldır':'Ctrl + left click: toggle mark',
    'Ctrl + Shift + sol tık: işareti sil':'Ctrl + Shift + left click: erase',
    'Clear — tüm kırmızıları iptal et':'Clear all red marks',
    'Kırmızıları 1. ana malzemeye taşı':'Move marked faces to slot 1',
    'Malzemeden yüz çıkar / taşı':'Move faces out of material', 'Hedef':'Target',
    'Seçili yüzleri malzemeden çıkar':'Move selected source faces',
    'Seçime listedeki malzemeyi ata':'Assign active material', 'Ad':'Name',
    'Oluştur ve seçime ata':'Create and assign', 'Yeni malzeme':'New material',
    'Ana malzeme (1. yuva)':'Main material (slot 1)',
    'Yüzleri mesh’in ilk malzeme yuvasına taşı':'Move faces to the first material slot',
    '(boş yuva)':'(empty slot)', '(seçilmedi)':'(none)', '(boş)':'(empty)', '(malzeme yok)':'(no material)',
    'Eksik yüz / açıklık tara':'Scan openings', 'Yalnız listedeki malzemeyi tara':'Active material only',
    'Bu açıklığı yoksay':'Ignore this opening', 'Açıklığı yoksay':'Ignore opening',
    'Yoksayılanları geri getir':'Restore ignored openings',
    'Listedeki açıklığı seç ve yaklaş':'Focus listed opening', 'Açıklığı seç ve yaklaş':'Focus opening',
    'Açıklıkları turkuaz çizgilerle göster':'Show cyan boundaries',
    'Önizlemeli onarım':'Preview repair', 'Önizlemeli onarım (önerilen)':'Preview repair (recommended)',
    'Önizleme açıklık sınırı':'Preview size limit', 'Yama saydamlığı':'Patch opacity',
    'Listedeki açıklığı önizle':'Preview listed opening', 'Tüm uygun açıklıkları önizle':'Preview all eligible openings',
    'Uygula':'Apply', 'İptal':'Cancel', 'Yama önizlemesi':'Repair preview',
    'Henüz geometri değiştirilmedi.':'No geometry changed yet.',
    'Uygula gerçek yüz ekler. Ctrl+Z: geri al.':'Apply adds real faces. Ctrl+Z: undo.',
    'Her açıklık eksik yüz olmayabilir.':'Some openings may be intentional.',
    'Sıkı küçük delik modu':'Strict small-hole mode', 'En büyük açıklık':'Maximum opening size',
    'Onarılabilirleri kontrol et':'Check eligibility', 'Uygun küçük delikleri kapat':'Fill eligible small holes',
    'Yalnız listedeki açıklığı onar':'Repair listed opening',
    'Yalnız uygun 3–4 kenarlı açıklıklar.':'Eligible 3–4-edge loops only.',
    'Seçili noktaları birleştir':'Merge selected vertices',
    'Seçili noktaları mesafeyle birleştir':'Merge selected by distance',
    'Birleştirme mesafesi':'Merge distance', 'Yalnız bağlı geometri':'Connected only',
    'Gerçek geometri değişir. Ctrl+Z: geri al.':'Changes geometry. Ctrl+Z: undo.',
    'Kapalı halka':'Closed loop', 'Dallanan sınır':'Branched boundary', 'Sınır zinciri':'Boundary chain',
    'Geometri değişti; tekrar tarayın.':'Geometry changed; scan again.',
    'Tek bir mesh ile Düzenleme Modu’na geçin.':'Enter Edit Mode on one mesh.',
    'Tek bir mesh ile Düzenleme Modu’na geçin':'Enter Edit Mode on one mesh',
    'Tek bir mesh seçip Düzenleme Modu’na (Tab) geçin':'Select one mesh and enter Edit Mode (Tab)',
    'Model değişti; yeniden önizleyin.':'Model changed; rebuild the preview.',
    'Model veya boyut sınırı değişti; yeniden önizleyin.':'Model or size limit changed; rebuild the preview.',
    'Önce açıklıkları yeniden tarayın':'Scan the openings again first',
    'Önce açıklıkları tekrar tarayın':'Scan the openings again first',
    'Bu sınır için yama önerilemedi; nedenleri panelde':'No patch could be proposed; see the skip reasons',
    'Önce bir yama önizlemesi oluşturun':'Build a repair preview first',
    'Geçerli bir açıklık seçin veya yeniden tarayın':'Select a valid opening or scan again',
    'Açıklık yoksayıldı; geometri değişmedi':'Opening ignored; geometry unchanged',
    'Bu mesh için yoksayılan açıklıklar geri getirildi':'Ignored openings restored for this mesh',
    'Tarama yok veya geometri değişti; önce tekrar tarayın':'No valid scan; scan again',
    'Bu sınır gizli. Önce yüzleri görünür yapıp tekrar deneyin':'This boundary is hidden; reveal it first',
    'Bu sınırlar için uygun küçük delik yok; atlama nedenleri panelde':'No eligible small hole; see the skip reasons',
    'Önce birleştirilecek en az iki noktayı seçin':'Select at least two vertices to merge',
    'Sıfır ölçekli nesnede birleştirme yapılamaz':'Cannot merge an object with zero scale',
    'Önce listeden bir malzeme seçin':'Select a material from the list first',
    'Bu mesh üzerinde malzeme yok':'This mesh has no materials',
    'Geçerli bir hedef malzeme seçin':'Choose a valid target material',
    'Kaynak ve hedef malzeme yuvalarını kontrol edin':'Check source and target material slots',
    'Kaynak ve hedef aynı. Farklı bir hedef malzeme seçin':'Source and target match; choose another target',
    'Seçimde kaynak malzemeye ait yüz yok; kaynak malzemeyi listeden seçin':'No selected source faces; choose the source material',
    'Akıllı seçim düğmesine basıp modelde bir yüz tıklayın':'Start smart selection and click a mesh face',
    'Modelde görünür bir yüz tıklayın; Esc ile iptal edebilirsiniz':'Click a visible face; Esc cancels',
    'Önce seçim aracıyla yüzleri seçin':'Select faces with a selection tool first',
    'Önce Ctrl+sol tık ile turuncu yüzleri kırmızı işaretleyin':'Mark selected faces red first',
    'İşaretlemeden sonra malzeme ataması değişti; işaretleri temizleyip yeniden işaretleyin':'Material assignments changed; clear and rebuild the marks',
    'Kırmızı yüzlerden bazıları gizli. Önce görünür yapın veya işaretleri temizleyin':'Some marked faces are hidden; reveal them or clear the marks',
    'Bu mesh için saklanmış seçim yok':'No stored selection for this mesh',
    'Topoloji değişti; yanlış yüz seçmemek için geri çağırma iptal edildi':'Topology changed; stored selection was not restored',
    'Önce önceki gizlemeyi geri alın':'Restore the previous isolation first',
    'Önce en az bir yüz seçin':'Select at least one face first',
    'Gizlenecek başka görünür yüz yok':'No other visible faces to hide',
    'Geri alınacak gizleme yok':'No isolation to restore',
    'Topoloji değişti. Gerekirse “Tüm gizlileri göster” düğmesini kullanın':'Topology changed; use Reveal all hidden faces if needed',
    'Bir malzeme ve en az bir yüz seçin':'Select a material and at least one face',
    'En az bir yüz seçin ve malzeme adı yazın':'Select at least one face and enter a material name',
    'Üçgen/dörtgen kapalı halka değil':'Not a closed triangle/quad loop',
    'Gizli geometri':'Hidden geometry', 'Birden fazla komşu malzeme':'Mixed adjacent materials',
    'Yakında çok-yüzlü kenar':'Nearby non-manifold edge', 'Bu sınırda zaten yüz var':'A face already fills this boundary',
    'Sınır sıralanamıyor':'Cannot order the boundary', 'Boyut sınırından büyük':'Over size limit',
    'Sıfır boyutlu açıklık':'Zero-size opening', 'Dejenere sınır':'Degenerate boundary',
    'Fazla eğri / düzlemsel değil':'Too warped / nonplanar', 'İçbükey veya dejenere sınır':'Concave or degenerate boundary',
    'Komşu yüz yönleri tutarsız':'Inconsistent adjacent face winding',
    'Mevcut yüzeyle çakışma':'Existing-surface overlap',
    'Kapalı, en fazla 256 kenarlı halka gerekli':'Requires a closed loop with 3–256 edges',
    'Sınır artık açık değil':'Boundary is no longer open',
    'Önizleme boyut sınırından büyük':'Over preview size limit',
    'Çakışık noktalar / dejenere sınır':'Coincident vertices / degenerate boundary',
    'Tek bir yama oluşturulamadı':'Could not create one patch',
    'Üçgenleme sınırı / komşu yüz yönleri tutarsız':'Invalid triangulation boundary / winding',
    'Sıfır alanlı üçgen':'Zero-area triangle',
    'Önerilen yamalar birbiriyle çakışıyor':'Proposed patches overlap',
    'Seçili':'Selected', 'Gizli':'Hidden', 'Malzeme':'Material', 'Kaynak':'Source',
    'Ekle':'Add', 'Çıkar':'Subtract', 'kenar':'edges', 'Uygun':'Eligible', 'Eklenen yüz':'Faces added',
    'Bölgeye tıkla':'Pick region', 'Rastgele renkler':'Random colors for all',
    'Bu malzemeye renk ver':'Color active material', 'Rengi kaldır':'Clear active color',
    'Renkleri temizle':'Clear all colors', 'Karartma modu':'Dark mode',
    'İşaretlileri 1. yuvaya taşı':'Move marked to slot 1',
    'Gerçek atama · Ctrl+Z: geri al':'Changes assignments · Ctrl+Z: undo',
    'Seç ve yaklaş':'Focus opening', 'Yoksay':'Ignore', 'Atlama nedenleri':'Skip reasons',
    'Yalıt':'Isolate','Geri göster':'Restore', 'Diğerlerini gizle':'Hide unselected',
    'Listedeki açıklık':'Listed opening','Taramadaki uygun açıklıklar':'Eligible scanned openings',
    'Önizle':'Preview','Önizlemeyi uygula':'Apply preview','Önizlemeyi iptal et':'Cancel preview',
    'Bu malzemenin önizleme rengini kaldır':'Clear active material preview',
    'Temizle':'Clear', 'Kırmızı yüzler':'Red marks','Seçimi düzenle':'Refine selection',
    'Yüz seçim fırçası':'Face selection brush','Seçim hafızası':'Selection memory',
    'Yüzleri yalıt':'Isolate faces', 'Seçime malzemeyi ata':'Assign material to selection',
    'Akıllı seçim: modele sol tıkla · Shift: ekle · Ctrl: çıkar · Esc: iptal':
        'Smart selection: click mesh · Shift: add · Ctrl: subtract · Esc: cancel',
    'Kırmızı işaret silme · sol tuşu bırak: bitir · Esc: bu çizgiyi iptal et':
        'Erase marks · release left mouse: finish · Esc: cancel stroke',
    'Kırmızı işaret ekleme · sol tuşu bırak: bitir · Esc: bu çizgiyi iptal et':
        'Add marks · release left mouse: finish · Esc: cancel stroke',
    'Atanmış malzemeyi ayrı parçalarıyla seç; ana malzemede yüzey sınırına geç':
        'Use the assigned material including disconnected pieces; use surface boundaries on slot 1',
    'Tıklanan yüzün malzemesine ait tüm görünür yüzleri seç':
        'Select all visible faces sharing the clicked material',
    'Açı, malzeme, dikiş ve keskinlik sınırlarına göre bağlı yüzeyi seç':
        'Follow connected faces within angle, material, seam and sharp-edge boundaries',
    'Normal görünüme dön':'Reset color previews',
}

OP_HELP_EN={
    'kmtr.material_visibility':'Show or hide faces using this material in the current mesh. Other materials stay unchanged. An open eye hides all; a closed eye shows all. Ctrl+Z: undo.',
    'kmtr.hole_scan':'List connected open boundary edges. Intentional openings can appear; no geometry or UV changes.',
    'kmtr.hole_ignore':'Exclude an opening from the list, cyan overlay and repairs. Restore ignored openings brings it back.',
    'kmtr.hole_focus':'Select the listed boundary edges and frame them without adding faces.',
    'kmtr.repair_preview':'Preview proposed triangles in violet. Only Apply changes geometry; Ctrl+Z undoes the repair.',
    'kmtr.hole_repair':'Fill eligible small planar triangle/quad holes. Real geometry changes; Ctrl+Z undoes them.',
    'kmtr.merge_selected':'Weld only nearby selected visible vertices. Real geometry changes; Ctrl+Z undoes them.',
    'kmtr.material_select':'Select, add or subtract the visible faces assigned to the active material.',
    'kmtr.material_color':'Temporary viewport color only. Shaders, UVs, assignments and exported data stay unchanged.',
    'kmtr.remove_from_material':'Move selected visible source faces to the chosen material. Ctrl+Z undoes assignment.',
    'kmtr.smart_select':'Click a face to select its region. Shift adds, Ctrl subtracts. Uses materials or surface boundaries.',
    'kmtr.red_action':'Mark/unmark selected faces, clear marks or transfer marked faces to material slot 1.',
    'kmtr.red_paint':'Ctrl+left click toggles red marks; a drag follows its starting face. Ctrl+Shift always erases.',
    'kmtr.selection_action':'Clear, invert, grow or shrink the visible face selection.',
    'kmtr.brush':'Use native circle selection in add/subtract mode. X-Ray may also select faces behind the surface.',
    'kmtr.selection_memory':'Store or recall a session selection. Topology changes invalidate stored face indices.',
    'kmtr.isolate':'Hide unselected faces or restore previous visibility while preserving previously hidden faces.',
    'kmtr.preview':'Draw a temporary dark viewport mask. No material, texture, UV or export changes.',
    'kmtr.assign_material':'Assign the active material to selected visible faces. Changes real exported assignments.',
    'kmtr.new_material':'Create and assign a material, reusing an existing material with the entered name.',
}

_MESSAGE_EN = [
    (r'Olası delik (\d+)', 'Opening {}'), (r'Açık sınır (\d+)', 'Open boundary {}'),
    (r'(\d+) kenar', '{} edges'), (r'(\d+) sınır kenarı gizli','{} boundary edges hidden'),
    (r'Malzeme: (.*)', 'Material: {}'), (r'Kaynak: (.*)', 'Source: {}'),
    (r'(\d+) olası açıklık bulundu; otomatik onarım yapılmadı','{} openings found; no repair applied'),
    (r'(\d+) olası açıklık bulundu','{} candidate openings'),
    (r'(\d+) açıklık yoksayıldı','{} openings ignored'),
    (r'(\d+) yama · (\d+) önerilen üçgen','{} patches · {} proposed triangles'),
    (r'(\d+) yama / (\d+) üçgen yalnız önizlemede; henüz yüz eklenmedi','{} patches / {} triangles in preview; no faces added'),
    (r'(\d+) önizlenen üçgen eklendi. Yeni UV’leri kontrol edin. Ctrl\+Z: geri al','{} previewed triangles added. Check new UVs. Ctrl+Z: undo'),
    (r'(\d+) uygun küçük açıklık; (\d+) atlanacak','{} eligible small openings; {} skipped'),
    (r'(\d+) yeni yüz eklendi; (\d+) sınır atlandı. Yeni yüzlerin UV’lerini kontrol edin. Ctrl\+Z: geri al','{} faces added; {} boundaries skipped. Check new UVs. Ctrl+Z: undo'),
    (r'(\d+) nokta birleştirildi. Ctrl\+Z: geri al','{} vertices merged. Ctrl+Z: undo'),
    (r'(\d+) yüze (.*) atandı','{} faces assigned to {}'),
    (r'(\d+) yüz (.*) hedefine taşındı','{} faces moved to {}'),
    (r'(\d+) yüz: malzeme grubu','{} faces: material group'),
    (r'(\d+) yüz: yüzey bölgesi','{} faces: surface region'),
    (r'(\d+) kırmızı yüz 1. ana malzemeye taşındı','{} marked faces moved to slot 1'),
    (r'(\d+) yüz hafızaya alındı','{} faces stored'),
    (r'(\d+) kırmızı yüz · renk geçicidir','{} marked faces · temporary color'),
    (r'(\d+) yüz seçili','{} faces selected'),
    (r'Yama uygulanamadı: (.*)','Could not apply patch: {}'),
    (r'Yama önizlemesi çizilemedi: (.*)','Could not draw patch preview: {}'),
    (r'Önizleme çizilemedi: (.*)','Could not draw preview: {}'),
]


def _language(context=None):
    context=context or bpy.context
    settings=getattr(getattr(context,'window_manager',None),'kmtr_settings',None)
    return getattr(settings,'language','TR')


def _t(text,context=None):
    if _language(context)!='EN':return text
    if text in UI_EN:return UI_EN[text]
    for pattern,translation in _MESSAGE_EN:
        match=re.fullmatch(pattern,text)
        if match:return translation.format(*match.groups())
    return text


def _localized_items(items):
    cache={}
    def callback(self,context):
        lang=_language(context)
        if lang not in cache:
            cache[lang]=[(item[0],_t(item[1],context),_t(item[2],context),*item[3:]) for item in items]
        return cache[lang]
    return callback


_smart_mode_items=_localized_items([
    ('AUTO','Otomatik','Atanmış malzemeyi ayrı parçalarıyla seç; ana malzemede yüzey sınırına geç'),
    ('MATERIAL','Aynı malzeme','Tıklanan yüzün malzemesine ait tüm görünür yüzleri seç'),
    ('SURFACE','Yüzey sınırları','Açı, malzeme, dikiş ve keskinlik sınırlarına göre bağlı yüzeyi seç')])


def _language_changed(settings,context):
    addon=context.preferences.addons.get(__name__) if context else None
    if addon and addon.preferences.language!=settings.language:addon.preferences.language=settings.language
    _redraw()


def _preference_language_changed(prefs,context):
    settings=getattr(context.window_manager,'kmtr_settings',None) if context else None
    if settings and settings.language!=prefs.language:settings.language=prefs.language
    _redraw()


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


def _topology_edited(obj, preserve_ignored=False):
    clear_repair_preview()
    clear_red_marks()
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    key=_mesh_key(obj.data)
    ignored=_runtime['ignored_holes'].pop(key,None)
    if preserve_ignored and ignored:
        # These callers only add faces/diagonals; existing vertex/edge indices stay intact.
        bm=bmesh.from_edit_mesh(obj.data)
        existing={r['edges'] for r in find_open_boundaries(bm,obj.matrix_world)}
        retained=ignored['regions'] & existing
        if retained:
            _runtime['ignored_holes'][key]={'topology':_boundary_topology_key(bm),'regions':retained}
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


def _ignored_openings(obj,bm):
    key=_mesh_key(obj.data)
    stored=_runtime['ignored_holes'].get(key)
    if stored and stored['topology']!=_boundary_topology_key(bm):
        _runtime['ignored_holes'].pop(key,None)
        stored=None
    return stored['regions'] if stored else set()


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
    key=(_language(context),names)
    if key not in cache:
        items = [('MAIN', _t('Ana malzeme (1. yuva)',context), _t('Yüzleri mesh’in ilk malzeme yuvasına taşı',context), 0)]
        items.extend(('SLOT_' + str(i), name, ('Move to ' + name if key[0]=='EN' else name + ' malzemesine taşı'), i)
                     for i, name in enumerate(names) if i > 0)
        cache[key] = items
    return cache[key]


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


class KMTR_Preferences(bpy.types.AddonPreferences):
    bl_idname=__name__
    language: EnumProperty(name='Dil / Language',items=[('TR','Türkçe','Türkçe'),('EN','English','English')],
                           default='TR',update=_preference_language_changed)

    def draw(self,context):
        self.layout.prop(self,'language',expand=True)


class KMTR_Settings(bpy.types.PropertyGroup):
    language: EnumProperty(name='Dil / Language',items=[('TR','Türkçe','Türkçe'),('EN','English','English')],
                           default='TR',options={'SKIP_SAVE'},update=_language_changed)
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
    preview_mode: EnumProperty(items=_localized_items(PREVIEW_ITEMS), default=0, options={'SKIP_SAVE'}, update=_preview_changed)
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
    smart_mode: EnumProperty(name='Yöntem', options={'SKIP_SAVE'}, default=0, items=_smart_mode_items)
    smart_angle: FloatProperty(name='Açı sınırı', description='Yüzey seçiminde komşu yüzler arasındaki en büyük açı',
                              default=math.radians(35), min=math.radians(1), max=math.radians(179),
                              subtype='ANGLE', options={'SKIP_SAVE'})


class KMTR_EditOperator:
    @classmethod
    def description(cls,context,properties):
        if _language(context)=='EN' and cls.bl_idname in OP_HELP_EN:return OP_HELP_EN[cls.bl_idname]
        return _t(getattr(cls,'bl_description',''),context)

    @classmethod
    def poll(cls, context):
        if not _single_edit_mesh(context):
            cls.poll_message_set(_t('Tek bir mesh seçip Düzenleme Modu’na (Tab) geçin',context))
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
        ignored=_ignored_openings(obj,bm)
        ignored_count=sum(r['edges'] in ignored for r in regions)
        regions=[r for r in regions if r['edges'] not in ignored]
        _runtime['hole_scan'] = {'mesh': _mesh_key(obj.data), 'topology': _boundary_topology_key(bm),
                                 'regions': regions, 'stale': False, 'ignored_count':ignored_count}
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
        self.report({'INFO'}, _t(str(len(regions)) + ' olası açıklık bulundu; otomatik onarım yapılmadı',context))
        _redraw()
        return {'FINISHED'}


class KMTR_OT_hole_ignore(KMTR_EditOperator,bpy.types.Operator):
    bl_idname='kmtr.hole_ignore'
    bl_label='Açıklığı yoksay'
    bl_description='Önemsiz açıklığı listeden, turkuaz çizgilerden ve onarımdan çıkarır. Geometri değişmez; Yoksayılanları geri getir ile geri alınır'
    action: EnumProperty(items=_localized_items([('IGNORE','Bu açıklığı yoksay',''),('RESTORE','Yoksayılanları geri getir','')]))
    index: IntProperty(default=-1,min=-1,options={'HIDDEN','SKIP_SAVE'})

    def execute(self,context):
        obj,bm=_edit_mesh(context);key=_mesh_key(obj.data)
        settings=context.window_manager.kmtr_settings
        if self.action=='IGNORE':
            report=_hole_report(obj,bm)
            index=settings.hole_active_index if self.index<0 else self.index
            if report is None or not 0<=index<len(report['regions']):
                self.report({'WARNING'},_t('Geçerli bir açıklık seçin veya yeniden tarayın',context));return {'CANCELLED'}
            ignored=set(_ignored_openings(obj,bm))
            ignored.add(report['regions'][index]['edges'])
            _runtime['ignored_holes'][key]={'topology':_boundary_topology_key(bm),'regions':ignored}
            next_index=index
        else:
            _runtime['ignored_holes'].pop(key,None)
            next_index=settings.hole_active_index
        clear_repair_preview()
        bpy.ops.kmtr.hole_scan()
        settings.hole_active_index=min(next_index,max(0,len(settings.hole_items)-1))
        self.report({'INFO'},_t('Açıklık yoksayıldı; geometri değişmedi' if self.action=='IGNORE'
                    else 'Bu mesh için yoksayılan açıklıklar geri getirildi',context))
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
            self.report({'WARNING'}, _t('Tarama yok veya geometri değişti; önce tekrar tarayın',context))
            return {'CANCELLED'}
        region = report['regions'][self.index]
        ids = [i for i in region['edges'] if not bm.edges[i].hide and not any(v.hide for v in bm.edges[i].verts)]
        if not ids:
            self.report({'WARNING'}, _t('Bu sınır gizli. Önce yüzleri görünür yapıp tekrar deneyin',context))
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
    action: EnumProperty(items=_localized_items([('BUILD','Önizle',''),('APPLY','Önizlemeyi uygula',''),('CANCEL','Önizlemeyi iptal et','')]))
    scope: EnumProperty(items=_localized_items([('ACTIVE','Listedeki açıklık',''),('ALL','Taramadaki uygun açıklıklar','')]),default=0)

    def execute(self,context):
        if self.action=='CANCEL':
            clear_repair_preview();return {'FINISHED'}
        obj,bm=_edit_mesh(context);settings=context.window_manager.kmtr_settings
        if self.action=='BUILD':
            clear_repair_preview()
            report=_hole_report(obj,bm)
            if report is None:
                self.report({'WARNING'},_t('Önce açıklıkları yeniden tarayın',context));return {'CANCELLED'}
            regions=report['regions']
            if self.scope=='ACTIVE':regions=regions[settings.hole_active_index:settings.hole_active_index+1]
            plan=build_repair_preview(obj,bm,regions,settings.patch_max_size)
            _runtime['repair_preview']=plan
            _runtime['patch_check']=True
            if not plan['patches']:
                self.report({'WARNING'},_t('Bu sınır için yama önerilemedi; nedenleri panelde',context));_redraw()
                return {'CANCELLED'}
            if not bpy.app.background:
                _runtime['patch_handler']=bpy.types.SpaceView3D.draw_handler_add(_draw_patch,(),'WINDOW','POST_VIEW')
                bpy.app.timers.register(_patch_tick,first_interval=.1)
            count=sum(len(p['triangles']) for p in plan['patches'])
            self.report({'INFO'},_t(str(len(plan['patches']))+' yama / '+str(count)+' üçgen yalnız önizlemede; henüz yüz eklenmedi',context))
            _redraw();return {'FINISHED'}
        plan=_runtime['repair_preview']
        if not plan or not plan['patches']:
            self.report({'WARNING'},_t('Önce bir yama önizlemesi oluşturun',context));return {'CANCELLED'}
        if plan['state']!=_repair_state_key(obj,bm) or plan['max_size']!=settings.patch_max_size:
            clear_repair_preview('Model veya boyut sınırı değişti; yeniden önizleyin.')
            self.report({'WARNING'},_t(_runtime['patch_error'],context));return {'CANCELLED'}
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
            self.report({'ERROR'},_t('Yama uygulanamadı: '+str(exc),context));return {'CANCELLED'}
        count=len(created)
        bm.faces.index_update();bm.faces.ensure_lookup_table()
        _set_faces(context,bm,{f.index for f in created})
        _topology_edited(obj,preserve_ignored=True);bpy.ops.kmtr.hole_scan()
        self.report({'INFO'},_t(str(count)+' önizlenen üçgen eklendi. Yeni UV’leri kontrol edin. Ctrl+Z: geri al',context))
        return {'FINISHED'}


class KMTR_OT_hole_repair(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.hole_repair'
    bl_label = 'Uygun küçük delikleri kapat'
    bl_description = 'Taramadaki küçük, görünür, düzlemsel üçgen/dörtgen açıklıkları kapatır. Büyük, karışık veya çakışan sınırları atlar. Gerçek geometri değişir; Ctrl+Z ile geri alınır'
    bl_options = {'REGISTER', 'UNDO'}
    preview_only: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    scope: EnumProperty(items=_localized_items([('ALL', 'Taramadaki uygun açıklıklar', ''), ('ACTIVE', 'Listedeki açıklık', '')]), default=0)

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        report = _hole_report(obj, bm)
        if report is None:
            self.report({'WARNING'}, _t('Önce açıklıkları tekrar tarayın',context))
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
            self.report({'INFO'}, _t(str(len(eligible))+' uygun küçük açıklık; '+str(len(plans)-len(eligible))+' atlanacak',context))
            _redraw()
            return {'FINISHED'}
        if not eligible:
            self.report({'WARNING'}, _t('Bu sınırlar için uygun küçük delik yok; atlama nedenleri panelde',context))
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
        _topology_edited(obj,preserve_ignored=True)
        bpy.ops.kmtr.hole_scan()
        _runtime['repair_report'] = summary
        self.report({'INFO'}, _t(str(count)+' yeni yüz eklendi; '+str(len(plans)-len(eligible))+' sınır atlandı. Yeni yüzlerin UV’lerini kontrol edin. Ctrl+Z: geri al',context))
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
            self.report({'WARNING'}, _t('Önce birleştirilecek en az iki noktayı seçin',context))
            return {'CANCELLED'}
        settings = context.window_manager.kmtr_settings
        scale = max(abs(v) for v in obj.matrix_world.to_scale())
        if scale <= 1e-12:
            self.report({'WARNING'}, _t('Sıfır ölçekli nesnede birleştirme yapılamaz',context))
            return {'CANCELLED'}
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=verts, use_connected=settings.merge_connected_only,
                                dist=settings.merge_distance/scale)
        removed = before-len(bm.verts)
        if removed:
            _topology_edited(obj); bpy.ops.kmtr.hole_scan()
        self.report({'INFO'}, _t(str(removed)+' nokta birleştirildi. Ctrl+Z: geri al',context))
        return {'FINISHED'}


def _material_slot_group(obj,index):
    material=obj.material_slots[index].material
    return {i for i,slot in enumerate(obj.material_slots) if slot.material==material} if material else {index}


def material_visibility_stats(obj,bm):
    keys=[('MAT',_mesh_key(slot.material)) if slot.material else ('EMPTY',i)
          for i,slot in enumerate(obj.material_slots)]
    counts={key:[0,0] for key in keys}
    for face in bm.faces:
        if 0<=face.material_index<len(keys):
            values=counts[keys[face.material_index]]
            values[0]+=not face.hide;values[1]+=1
    return {i:tuple(counts[key]) for i,key in enumerate(keys)}


class KMTR_OT_material_visibility(KMTR_EditOperator,bpy.types.Operator):
    bl_idname='kmtr.material_visibility'
    bl_label='Malzemeyi göster/gizle'
    bl_description='Bu malzemenin yüzlerini göster veya gizle. Diğer malzemeler değişmez. Açık göz gizler, kapalı göz gösterir. Ctrl+Z: geri al'
    bl_options={'REGISTER','UNDO'}
    action: EnumProperty(items=_localized_items([('TOGGLE','Göster / gizle',''),('SHOW','Göster',''),('HIDE','Gizle','')]),default=0)
    index: IntProperty(default=-1,min=-1,options={'HIDDEN','SKIP_SAVE'})

    def execute(self,context):
        obj,bm=_edit_mesh(context)
        index=obj.active_material_index if self.index<0 else self.index
        if not 0<=index<len(obj.material_slots):
            self.report({'WARNING'},_t('Geçerli bir malzeme yuvası seçin',context));return {'CANCELLED'}
        slots=_material_slot_group(obj,index)
        faces=[f for f in bm.faces if f.material_index in slots]
        if not faces:
            self.report({'WARNING'},_t('Bu malzemeye atanmış yüz yok',context));return {'CANCELLED'}
        hide=self.action=='HIDE' or (self.action=='TOGGLE' and any(not f.hide for f in faces))
        changed=[f for f in faces if f.hide!=hide]
        if changed:
            clear_repair_preview()
            for face in changed:
                face.hide_set(hide)
                if not hide:face.select=False
            _runtime['hole_dirty']=True;_runtime['red_geometry_dirty']=True
            _flush(obj)
        self.report({'INFO'},_t('Malzeme gizlendi' if hide else 'Malzeme gösterildi',context))
        return {'FINISHED'}


class KMTR_OT_material_select(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.material_select'
    bl_label = 'Malzemeden yüz seç'
    bl_description = 'Etkin malzemenin görünen yüzlerini seç, mevcut seçime ekle veya seçimden çıkar'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=_localized_items([('REPLACE', 'Seç', ''), ('ADD', 'Ekle', ''), ('SUBTRACT', 'Çıkar', '')]))

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        if not obj.active_material:
            self.report({'WARNING'}, _t('Önce listeden bir malzeme seçin',context))
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
    action: EnumProperty(items=_localized_items([('APPLY', 'Bu malzemeyi önizlemede boya', ''),
                                ('RANDOM_ALL', 'Tüm malzemelere farklı rastgele renkler', ''),
                                ('CLEAR_ACTIVE', 'Bu malzemenin önizleme rengini kaldır', ''),
                                ('CLEAR_ALL', 'Tüm önizleme renklerini temizle', '')]))
    seed: IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        obj = context.edit_object
        settings = context.window_manager.kmtr_settings
        if self.action == 'RANDOM_ALL':
            materials = {_mesh_key(slot.material):slot.material for slot in obj.material_slots if slot.material}
            if not materials:
                self.report({'WARNING'}, _t('Bu mesh üzerinde malzeme yok',context))
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
                self.report({'WARNING'}, _t('Önce listeden bir malzeme seçin',context))
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
            self.report({'WARNING'}, _t('Geçerli bir hedef malzeme seçin',context))
            return {'CANCELLED'}
        source = obj.active_material_index
        if not (0 <= source < len(obj.data.materials) and 0 <= destination < len(obj.data.materials)):
            self.report({'WARNING'}, _t('Kaynak ve hedef malzeme yuvalarını kontrol edin',context))
            return {'CANCELLED'}
        if destination == source:
            self.report({'WARNING'}, _t('Kaynak ve hedef aynı. Farklı bir hedef malzeme seçin',context))
            return {'CANCELLED'}
        faces = [f for f in bm.faces if f.select and not f.hide and f.material_index == source]
        if not faces:
            self.report({'WARNING'}, _t('Seçimde kaynak malzemeye ait yüz yok; kaynak malzemeyi listeden seçin',context))
            return {'CANCELLED'}
        for face in faces:
            face.material_index = destination
        _flush(obj)
        target_mat = obj.data.materials[destination]
        self.report({'INFO'}, _t(str(len(faces)) + ' yüz ' + (target_mat.name if target_mat else 'boş malzeme yuvası') + ' hedefine taşındı',context))
        return {'FINISHED'}


class KMTR_OT_smart_select(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.smart_select'
    bl_label = 'Akıllı seçim: bölgeye tıkla'
    bl_description = 'Bir yüzü tıklayarak bölgesini seç. Shift: ekle, Ctrl: seçimden çıkar. Atanmış malzemede ayrı parçalar da seçilir; yüzey modunda açı ve malzeme sınırları kullanılır'
    bl_options = {'REGISTER', 'UNDO'}
    face_index: IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})
    action: EnumProperty(items=_localized_items([('REPLACE', 'Seç', ''), ('ADD', 'Ekle', ''), ('SUBTRACT', 'Çıkar', '')]), default=0)

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        if not 0 <= self.face_index < len(bm.faces):
            self.report({'WARNING'}, _t('Akıllı seçim düğmesine basıp modelde bir yüz tıklayın',context))
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
        self.report({'INFO'}, _t(str(len(target)) + ' yüz: ' + ('malzeme grubu' if mode == 'MATERIAL' or mode == 'AUTO' and material_index != 0 else 'yüzey bölgesi'),context))
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.face_index >= 0:
            return self.execute(context)
        if context.area is None or context.area.type != 'VIEW_3D':
            return {'CANCELLED'}
        self._area = context.area
        self._object_key = context.edit_object.as_pointer()
        context.window.cursor_modal_set('CROSSHAIR')
        context.workspace.status_text_set(_t('Akıllı seçim: modele sol tıkla · Shift: ekle · Ctrl: çıkar · Esc: iptal',context))
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
                self.report({'INFO'}, _t('Modelde görünür bir yüz tıklayın; Esc ile iptal edebilirsiniz',context))
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
    action: EnumProperty(items=_localized_items([('TRANSFER', 'Kırmızıları ana malzemeye taşı', ''), ('CLEAR', 'Kırmızıları temizle', ''),
                                ('MARK_SELECTION', 'Seçilileri kırmızı işaretle', 'Normal seçim aracıyla seçilen yüzleri geçici kırmızı işaretlere ekle'),
                                ('UNMARK_SELECTION', 'Seçilileri kırmızıdan çıkar', 'Seçili yüzlerin yalnız kırmızı işaretini kaldır')]))

    def execute(self, context):
        if self.action == 'CLEAR':
            clear_red_marks()
            return {'FINISHED'}
        obj, bm = _edit_mesh(context)
        if self.action in {'MARK_SELECTION', 'UNMARK_SELECTION'}:
            selected = {f.index for f in bm.faces if f.select and not f.hide}
            if not selected:
                self.report({'WARNING'}, _t('Önce seçim aracıyla yüzleri seçin',context))
                return {'CANCELLED'}
            mark_red_faces(context, selected, erase=self.action == 'UNMARK_SELECTION')
            return {'FINISHED'}
        ids = red_face_indices(obj, bm)
        if not ids or not obj.data.materials:
            self.report({'WARNING'}, _t('Önce Ctrl+sol tık ile turuncu yüzleri kırmızı işaretleyin',context))
            return {'CANCELLED'}
        originals = _runtime['red_marks']['faces']
        if any(bm.faces[i].material_index != originals[i] for i in ids):
            self.report({'WARNING'}, _t('İşaretlemeden sonra malzeme ataması değişti; işaretleri temizleyip yeniden işaretleyin',context))
            return {'CANCELLED'}
        if any(bm.faces[i].hide for i in ids):
            self.report({'WARNING'}, _t('Kırmızı yüzlerden bazıları gizli. Önce görünür yapın veya işaretleri temizleyin',context))
            return {'CANCELLED'}
        for i in ids:
            bm.faces[i].material_index = 0
        selected = {f.index for f in bm.faces if f.select and not f.hide} - ids
        _set_faces(context, bm, selected)
        clear_red_marks()
        _flush(obj)
        self.report({'INFO'}, _t(str(len(ids)) + ' kırmızı yüz 1. ana malzemeye taşındı',context))
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
        context.workspace.status_text_set(_t(('Kırmızı işaret silme' if self._erase else 'Kırmızı işaret ekleme') + ' · sol tuşu bırak: bitir · Esc: bu çizgiyi iptal et',context))
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
    action: EnumProperty(items=_localized_items([('CLEAR', 'Temizle', ''), ('INVERT', 'Ters çevir', ''),
                                ('GROW', 'Büyüt', ''), ('SHRINK', 'Küçült', '')]))

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
    action: EnumProperty(items=_localized_items([('ADD', 'Fırça +', 'Yüzleri seçime ekle'), ('SUB', 'Fırça −', 'Yüzleri seçimden çıkar'),
                                ('BOX', 'Kutu seçimine dön', 'Dairesel fırçadan çık ve kutu seçimini etkinleştir')]))

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
    action: EnumProperty(items=_localized_items([('STORE', 'Seçimi sakla', ''), ('RESTORE', 'Geri çağır', '')]))

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        key = _mesh_key(obj.data)
        if self.action == 'STORE':
            ids = {f.index for f in bm.faces if f.select and not f.hide}
            _runtime['memory'][key] = (_topology_key(bm), ids)
            self.report({'INFO'}, _t(str(len(ids)) + ' yüz hafızaya alındı',context))
        else:
            stored = _runtime['memory'].get(key)
            if stored is None:
                self.report({'WARNING'}, _t('Bu mesh için saklanmış seçim yok',context))
                return {'CANCELLED'}
            if stored[0] != _topology_key(bm):
                self.report({'WARNING'}, _t('Topoloji değişti; yanlış yüz seçmemek için geri çağırma iptal edildi',context))
                return {'CANCELLED'}
            _set_faces(context, bm, stored[1])
            _flush(obj)
        return {'FINISHED'}


class KMTR_OT_isolate(KMTR_EditOperator, bpy.types.Operator):
    bl_idname = 'kmtr.isolate'
    bl_label = 'Yüzleri yalıt'
    bl_description = 'Seçim dışını gizle veya önceki görünürlüğe dön; önceden gizli yüzler korunur'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=_localized_items([('HIDE', 'Diğerlerini gizle', ''), ('RESTORE', 'Gizlemeyi geri al', ''),
                                ('REVEAL', 'Tüm gizlileri göster', '')]))

    def execute(self, context):
        obj, bm = _edit_mesh(context)
        if self.action == 'HIDE':
            if any(elements.layers.int.get(name) is not None for elements, name in zip((bm.verts, bm.edges, bm.faces), _HIDDEN_LAYERS)):
                self.report({'WARNING'}, _t('Önce önceki gizlemeyi geri alın',context))
                return {'CANCELLED'}
            if not any(f.select and not f.hide for f in bm.faces):
                self.report({'WARNING'}, _t('Önce en az bir yüz seçin',context))
                return {'CANCELLED'}
            if not any(not f.hide and not f.select for f in bm.faces):
                self.report({'INFO'}, _t('Gizlenecek başka görünür yüz yok',context))
                return {'CANCELLED'}
            _store_hidden(bm)
            for face in bm.faces:
                if not face.select:
                    face.hide_set(True)
        elif self.action == 'RESTORE':
            if _isolation_layers(bm) is None:
                self.report({'WARNING'}, _t('Geri alınacak gizleme yok',context))
                return {'CANCELLED'}
            selected = {f.index for f in bm.faces if f.select and not f.hide}
            if not _restore_hidden(bm):
                self.report({'WARNING'}, _t('Topoloji değişti. Gerekirse “Tüm gizlileri göster” düğmesini kullanın',context))
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
            self.report({'WARNING'}, _t('Tek bir mesh ile Düzenleme Modu’na geçin',context))
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
            self.report({'WARNING'}, _t('Bir malzeme ve en az bir yüz seçin',context))
            return {'CANCELLED'}
        for face in selected:
            face.material_index = obj.active_material_index
        _flush(obj)
        self.report({'INFO'}, _t(str(len(selected)) + ' yüze ' + obj.active_material.name + ' atandı',context))
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
            self.report({'WARNING'}, _t('En az bir yüz seçin ve malzeme adı yazın',context))
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
        self.report({'INFO'}, _t(str(len(selected)) + ' yüze ' + mat.name + ' atandı',context))
        return {'FINISHED'}


def _op(layout, operator, text, **props):
    button = layout.operator(operator, text=text)
    for name, value in props.items():
        setattr(button, name, value)
    return button


class _UILayout:
    """Translate only UI text; datablock names/values remain untouched."""
    def __init__(self,layout):object.__setattr__(self,'raw',layout)
    def __getattr__(self,key):return getattr(self.raw,key)
    def __setattr__(self,key,value):setattr(self.raw,key,value)
    def row(self,**kwargs):return _UILayout(self.raw.row(**kwargs))
    def column(self,**kwargs):return _UILayout(self.raw.column(**kwargs))
    def box(self):return _UILayout(self.raw.box())
    def label(self,**kwargs):
        if 'text' in kwargs and kwargs.get('translate',True):kwargs['text']=_t(kwargs['text'])
        kwargs['translate']=False
        return self.raw.label(**kwargs)
    def prop(self,data,name,**kwargs):
        kwargs['text']=_t(kwargs.get('text',data.bl_rna.properties[name].name))
        kwargs['translate']=False
        return self.raw.prop(data,name,**kwargs)
    def operator(self,operator,**kwargs):
        text=kwargs.get('text')
        if text is None:
            category,name=operator.split('.')
            text=getattr(getattr(bpy.ops,category),name).get_rna_type().name
        kwargs['text']=_t(text);kwargs['translate']=False
        return self.raw.operator(operator,**kwargs)


def _section(layout,key,title,icon='NONE',closed=True):
    raw=layout.raw if isinstance(layout,_UILayout) else layout
    header,body=raw.panel('facepilot_'+key,default_closed=closed)
    _UILayout(header).label(text=title,icon=icon)
    return _UILayout(body) if body else None


class KMTR_UL_materials(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        split=layout.split(factor=.66,align=True)
        split.label(text=item.material.name if item.material else _t('(boş yuva)'),icon='MATERIAL',translate=False)
        tools=split.row(align=True)
        cache=_runtime['material_visibility_rows']
        stats=cache['rows'].get(index,(0,0)) if cache and cache['object']==_mesh_key(data) else (0,0)
        visible,total=stats
        tools.label(text=str(visible),translate=False)
        button=tools.row(align=True);button.enabled=bool(total)
        op=button.operator('kmtr.material_visibility',text='',icon='HIDE_OFF' if visible else 'HIDE_ON')
        op.action='TOGGLE';op.index=index


class KMTR_UL_holes(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=_UILayout(layout).row(align=True)
        row.label(text=item.name)
        row.label(text=str(item.edge_count)+' kenar')
        row.operator('kmtr.hole_focus',text='',icon='VIEWZOOM').index=index
        op=row.operator('kmtr.hole_ignore',text='',icon='X');op.action='IGNORE';op.index=index


def _draw_openings(layout,context,obj,bm,s):
    layout.prop(s,'hole_active_material_only')
    layout.operator('kmtr.hole_scan',text='Eksik yüz / açıklık tara',icon='VIEWZOOM')
    report=_hole_report(obj,bm)
    if report is None:
        if _runtime['hole_scan']:layout.label(text='Geometri değişti; tekrar tarayın.',icon='INFO')
        return
    layout.label(text=str(len(report['regions']))+' olası açıklık bulundu')
    if report.get('ignored_count'):layout.label(text=str(report['ignored_count'])+' açıklık yoksayıldı',icon='HIDE_ON')
    if _runtime['ignored_holes'].get(_mesh_key(obj.data),{}).get('regions'):
        layout.operator('kmtr.hole_ignore',text='Yoksayılanları geri getir',icon='LOOP_BACK').action='RESTORE'
    if s.hole_items:
        layout.template_list('KMTR_UL_holes','',s,'hole_items',s,'hole_active_index',rows=4)
        index=min(s.hole_active_index,len(s.hole_items)-1);item=s.hole_items[index]
        layout.label(text=_t(item.kind)+' · '+str(item.edge_count)+' '+_t('kenar'))
        layout.label(text='Malzeme: '+item.material_text)
        row=layout.row(align=True)
        op=row.operator('kmtr.hole_focus',text='Seç ve yaklaş',icon='VIEWZOOM');op.index=index
        op=row.operator('kmtr.hole_ignore',text='Yoksay',icon='X');op.action='IGNORE';op.index=index
    layout.prop(s,'hole_overlay')
    layout.label(text='Her açıklık eksik yüz olmayabilir.',icon='INFO')
    layout.separator()
    layout.label(text='Önizlemeli onarım',icon='HIDE_OFF')
    layout.prop(s,'patch_max_size')
    op=layout.operator('kmtr.repair_preview',text='Listedeki açıklığı önizle');op.action='BUILD';op.scope='ACTIVE'
    op=layout.operator('kmtr.repair_preview',text='Tüm uygun açıklıkları önizle');op.action='BUILD';op.scope='ALL'
    proposal=_runtime['repair_preview']
    if proposal and proposal['mesh']==_mesh_key(obj.data):
        triangles=sum(len(p['triangles']) for p in proposal['patches'])
        layout.label(text=str(len(proposal['patches']))+' yama · '+str(triangles)+' önerilen üçgen')
        layout.label(text='Henüz geometri değiştirilmedi.')
        layout.prop(s,'patch_opacity',slider=True)
        row=layout.row(align=True)
        apply=row.row();apply.enabled=bool(proposal['patches'])
        apply.operator('kmtr.repair_preview',text='Uygula',icon='CHECKMARK').action='APPLY'
        row.operator('kmtr.repair_preview',text='İptal',icon='X').action='CANCEL'
        if proposal['skipped']:
            details=_section(layout,'skip_reasons','Atlama nedenleri','INFO')
            if details:
                for reason,count in proposal['skipped'].items():
                    details.label(text=str(count)+' · '+_t(reason))
    if _runtime['patch_error']:layout.label(text=_t(_runtime['patch_error']),icon='ERROR')
    layout.label(text='Uygula gerçek yüz ekler. Ctrl+Z: geri al.')


class KMTR_PT_panel(bpy.types.Panel):
    bl_label='FacePilot'
    bl_idname='KMTR_PT_panel'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='FacePilot'

    def draw(self,context):
        layout=_UILayout(self.layout);s=context.window_manager.kmtr_settings
        layout.prop(s,'language',expand=True)
        if not _single_edit_mesh(context):
            layout.label(text='Tek bir mesh ile Düzenleme Modu’na geçin.',icon='INFO')
            layout.operator('kmtr.preview',text='Normal görünüme dön',icon='HIDE_OFF').mode='OFF'
            return
        obj,bm=_edit_mesh(context)
        selected=sum(f.select and not f.hide for f in bm.faces);hidden=sum(f.hide for f in bm.faces)
        status=layout.box()
        row=status.row(align=True)
        row.label(text=_t('Seçili')+': '+str(selected),icon='FACESEL')
        row.label(text=_t('Gizli')+': '+str(hidden),icon='HIDE_ON')
        status.label(text='Malzeme: '+(obj.active_material.name if obj.active_material else _t('(seçilmedi)')))
        isolated=_isolation_layers(bm) is not None
        row=status.row(align=True)
        isolate=row.row();isolate.enabled=not isolated
        isolate.operator('kmtr.isolate',text='Yalıt',icon='HIDE_ON').action='HIDE'
        restore=row.row();restore.enabled=isolated
        restore.operator('kmtr.isolate',text='Geri göster',icon='HIDE_OFF').action='RESTORE'

        body=_section(layout,'selection','Seçim','RESTRICT_SELECT_OFF',closed=False)
        if body:
            _runtime['material_visibility_rows']={'object':_mesh_key(obj),'rows':material_visibility_stats(obj,bm)}
            body.template_list('KMTR_UL_materials','',obj,'material_slots',obj,'active_material_index',rows=5)
            visible,total=_runtime['material_visibility_rows']['rows'].get(obj.active_material_index,(0,0))
            body.label(text=_t('Görünür')+': '+str(visible)+' / '+str(total))
            body.label(text='Göz simgesi: malzemeyi göster/gizle')
            row=body.row(align=True)
            _op(row,'kmtr.material_visibility','Göster',action='SHOW',index=-1)
            _op(row,'kmtr.material_visibility','Gizle',action='HIDE',index=-1)
            row=body.row(align=True)
            _op(row,'kmtr.material_select','Seç',action='REPLACE')
            _op(row,'kmtr.material_select','Ekle',action='ADD')
            _op(row,'kmtr.material_select','Çıkar',action='SUBTRACT')
            row=body.row(align=True)
            _op(row,'kmtr.brush','Fırça +',action='ADD');_op(row,'kmtr.brush','Fırça −',action='SUB')
            body.prop(s,'brush_radius',slider=True)
            body.operator('kmtr.brush',text='Kutu seçimine dön').action='BOX'
            row=body.row(align=True)
            _op(row,'kmtr.selection_action','Büyüt',action='GROW');_op(row,'kmtr.selection_action','Küçült',action='SHRINK')
            row=body.row(align=True)
            _op(row,'kmtr.selection_action','Ters çevir',action='INVERT');_op(row,'kmtr.selection_action','Temizle',action='CLEAR')
            row=body.row(align=True)
            _op(row,'kmtr.selection_memory','Seçimi sakla',action='STORE');_op(row,'kmtr.selection_memory','Geri çağır',action='RESTORE')
            body.operator('kmtr.isolate',text='Tüm gizlileri göster').action='REVEAL'

        body=_section(layout,'smart','Akıllı seçim','VIEWZOOM')
        if body:
            body.prop(s,'smart_mode')
            if s.smart_mode!='MATERIAL':body.prop(s,'smart_angle')
            body.operator('kmtr.smart_select',text='Bölgeye tıkla')
            body.label(text='Shift: ekle · Ctrl: çıkar')

        body=_section(layout,'visual','Görsel önizleme','SHADING_SOLID')
        if body:
            body.label(text='Renkler ve işaretler dışa aktarılmaz.',icon='INFO')
            _op(body,'kmtr.material_color','Rastgele renkler',action='RANDOM_ALL',seed=-1)
            body.prop(s,'material_preview_color');body.prop(s,'material_preview_opacity',slider=True)
            _op(body,'kmtr.material_color','Bu malzemeye renk ver',action='APPLY')
            _op(body,'kmtr.material_color','Rengi kaldır',action='CLEAR_ACTIVE')
            _op(body,'kmtr.material_color','Renkleri temizle',action='CLEAR_ALL')
            body.separator();body.prop(s,'preview_mode',text='Karartma modu')
            body.prop(s,'opacity',slider=True)
            body.operator('kmtr.preview',text='Normal görünüme dön',icon='LOOP_BACK').mode='OFF'
            if _runtime['error']:body.label(text=_t(_runtime['error']),icon='ERROR')

        body=_section(layout,'red','Kırmızı düzeltme','EDITMODE_HLT')
        if body:
            body.label(text='Geçici görünüm',icon='INFO')
            _op(body,'kmtr.red_action','Seçilileri kırmızı işaretle',action='MARK_SELECTION')
            _op(body,'kmtr.red_action','Seçilileri kırmızıdan çıkar',action='UNMARK_SELECTION')
            body.prop(s,'red_fill_opacity',slider=True);body.prop(s,'red_mode')
            body.label(text='Ctrl + sol tık: işaretle / kaldır');body.label(text='Ctrl + Shift + sol tık: işareti sil')
            stored=_runtime['red_marks'];count=len(stored['faces']) if stored and stored['mesh']==_mesh_key(obj.data) else 0
            body.label(text=str(count)+' kırmızı yüz · renk geçicidir')
            _op(body,'kmtr.red_action','Clear — tüm kırmızıları iptal et',action='CLEAR')
            body.separator();body.label(text='Gerçek atama',icon='MATERIAL')
            _op(body,'kmtr.red_action','İşaretlileri 1. yuvaya taşı',action='TRANSFER')
            if _runtime['red_error']:body.label(text=_t(_runtime['red_error']),icon='ERROR')

        body=_section(layout,'assignment','Malzeme atama','MATERIAL')
        if body:
            body.label(text='Gerçek atama · Ctrl+Z: geri al',icon='INFO')
            body.prop(s,'move_target')
            _op(body,'kmtr.remove_from_material','Seçili yüzleri malzemeden çıkar',target=s.move_target)
            body.operator('kmtr.assign_material',text='Seçime listedeki malzemeyi ata')
            body.separator();body.prop(s,'new_name',text='Yeni malzeme')
            body.operator('kmtr.new_material',text='Oluştur ve seçime ata')

        body=_section(layout,'openings','Açıklıklar ve onarım','MOD_TRIANGULATE')
        if body:_draw_openings(body,context,obj,bm,s)

        body=_section(layout,'advanced','Gelişmiş onarım','TOOL_SETTINGS')
        if body:
            body.label(text='Gerçek geometri değişir. Ctrl+Z: geri al.',icon='INFO')
            body.label(text='Sıkı küçük delik modu')
            body.label(text='Yalnız uygun 3–4 kenarlı açıklıklar.')
            body.prop(s,'repair_max_size')
            _op(body,'kmtr.hole_repair','Onarılabilirleri kontrol et',preview_only=True,scope='ALL')
            _op(body,'kmtr.hole_repair','Uygun küçük delikleri kapat',preview_only=False,scope='ALL')
            _op(body,'kmtr.hole_repair','Yalnız listedeki açıklığı onar',preview_only=False,scope='ACTIVE')
            summary=_runtime['repair_report']
            if summary and summary['mesh']==_mesh_key(obj.data):
                body.label(text=_t('Uygun')+': '+str(summary['eligible'])+' · '+_t('Eklenen yüz')+': '+str(summary['filled']))
                for reason,count in summary['skipped'].items():body.label(text=str(count)+' · '+_t(reason))
            body.separator();body.label(text='Seçili noktaları birleştir')
            body.prop(s,'merge_distance');body.prop(s,'merge_connected_only')
            body.operator('kmtr.merge_selected',text='Seçili noktaları mesafeyle birleştir')



def clear_runtime():
    _runtime['material_visibility_rows']=None
    _runtime['ignored_holes'].clear()
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
        addon=bpy.context.preferences.addons.get(__name__)
        if addon:settings.language=addon.preferences.language
        settings.preview_mode = 'OFF'


@persistent
def _on_update(*args):
    _runtime['patch_check'] = True
    _runtime['geometry_dirty'] = True
    _runtime['red_geometry_dirty'] = True
    _runtime['hole_dirty'] = True


CLASSES = (KMTR_Preferences, KMTR_HoleItem, KMTR_Settings, KMTR_OT_hole_scan, KMTR_OT_hole_ignore, KMTR_OT_hole_focus, KMTR_OT_repair_preview, KMTR_OT_hole_repair, KMTR_OT_merge_selected,
           KMTR_OT_material_visibility, KMTR_OT_material_select, KMTR_OT_material_color, KMTR_OT_remove_from_material, KMTR_OT_smart_select,
           KMTR_OT_red_action, KMTR_OT_red_paint,
           KMTR_OT_selection_action, KMTR_OT_brush,
           KMTR_OT_selection_memory, KMTR_OT_isolate, KMTR_OT_preview,
           KMTR_OT_assign_material, KMTR_OT_new_material, KMTR_UL_materials, KMTR_UL_holes, KMTR_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.kmtr_settings = PointerProperty(type=KMTR_Settings, options={'SKIP_SAVE'})
    addon=bpy.context.preferences.addons.get(__name__)
    if addon:bpy.context.window_manager.kmtr_settings.language=addon.preferences.language
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
