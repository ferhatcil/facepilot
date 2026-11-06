"""Run in factory-startup background Blender. Real mesh tests; no mocks."""
import importlib.util
from pathlib import Path
import sys
import unittest
import math

import bpy
import bmesh

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / 'kolay_malzeme_tr.py'


class AddonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert ADDON.is_file(), 'Turkish face/material add-on has not been implemented'
        spec = importlib.util.spec_from_file_location('kolay_malzeme_tr', ADDON)
        cls.addon = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.addon
        spec.loader.exec_module(cls.addon)
        cls.addon.register()

    @classmethod
    def tearDownClass(cls):
        cls.addon.unregister()

    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        mesh = bpy.data.meshes.new('FixtureMesh')
        verts = []
        for i in range(4):
            x = float(i * 2)
            verts.extend([(x, 0, 0), (x + 1, 0, 0), (x + 1, 1, 0), (x, 1, 0)])
        mesh.from_pydata(verts, [], [(i*4, i*4+1, i*4+2, i*4+3) for i in range(4)])
        obj = bpy.data.objects.new('Fixture', mesh)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        for name, color in [('MatA', (0.1, 0.2, 0.3, 1)), ('MatB', (0.8, 0.2, 0.1, 1))]:
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = color
            mesh.materials.append(mat)
        for p in mesh.polygons:
            p.material_index = p.index % 2
        mesh.uv_layers.new(name='OriginalUV')
        for i, uv in enumerate(mesh.uv_layers.active.data):
            uv.uv = ((i % 3) * 0.25, (i % 5) * 0.125)
        obj.active_material_index = 0
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.tool_settings.mesh_select_mode = (False, False, True)
        self.obj = obj
        self.bm = bmesh.from_edit_mesh(mesh)
        self.bm.faces.ensure_lookup_table()
        self.select({1})
        self.bm.faces[3].hide_set(True)
        bmesh.update_edit_mesh(mesh)

    def tearDown(self):
        self.addon.clear_runtime()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

    def select(self, ids):
        for f in self.bm.faces:
            f.select_set(False)
        for e in self.bm.edges:
            e.select_set(False)
        for v in self.bm.verts:
            v.select_set(False)
        for i in ids:
            self.bm.faces[i].select_set(True)
        self.bm.select_flush_mode()
        bmesh.update_edit_mesh(self.obj.data)

    def selected(self):
        return {f.index for f in self.bm.faces if f.select}

    def fingerprint(self):
        self.obj.update_from_editmode()
        mesh = self.obj.data
        return (
            tuple(tuple(v.co) for v in mesh.vertices),
            tuple((tuple(p.vertices), p.material_index) for p in mesh.polygons),
            tuple((a.name, a.domain, a.data_type) for a in mesh.attributes),
            tuple((layer.name, tuple(tuple(x.uv) for x in layer.data)) for layer in mesh.uv_layers),
            tuple((m.name, tuple(m.diffuse_color), tuple(m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value)) for m in mesh.materials),
        )

    def test_material_selection_replace_add_subtract_and_hidden(self):
        bpy.ops.kmtr.material_select(action='REPLACE')
        self.assertEqual(self.selected(), {0, 2})
        self.select({1})
        bpy.ops.kmtr.material_select(action='ADD')
        self.assertEqual(self.selected(), {0, 1, 2})
        bpy.ops.kmtr.material_select(action='SUBTRACT')
        self.assertEqual(self.selected(), {1})
        self.obj.active_material_index = 1
        bpy.ops.kmtr.material_select(action='REPLACE')
        self.assertEqual(self.selected(), {1})
        self.assertTrue(self.bm.faces[3].hide)

    def test_material_remove_all_faces_including_hidden_preserves_mesh_and_other_users(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_remove'),'Material removal tool is missing')
        source=self.obj.data.materials[1];target=self.obj.data.materials[0]
        other_mesh=bpy.data.meshes.new('OtherMaterialUser');other_mesh.materials.append(source)
        other=bpy.data.objects.new('OtherMaterialUser',other_mesh);bpy.context.collection.objects.link(other)
        self.obj.active_material_index=1;before=self.fingerprint()
        flags=tuple((f.select,f.hide) for f in self.bm.faces)
        self.assertEqual(bpy.ops.kmtr.material_remove(target='MAIN'),{'FINISHED'})
        self.bm=bmesh.from_edit_mesh(self.obj.data);self.bm.faces.ensure_lookup_table()
        self.assertEqual(list(self.obj.data.materials),[target]);self.assertEqual(len(self.bm.faces),4)
        self.assertTrue(all(f.material_index==0 for f in self.bm.faces))
        self.assertEqual(tuple((f.select,f.hide) for f in self.bm.faces),flags)
        after=self.fingerprint()
        for index in (0,2,3):self.assertEqual(before[index],after[index])
        self.assertEqual(list(other_mesh.materials),[source]);self.assertIsNotNone(bpy.data.materials.get(source.name))

    def test_material_remove_duplicate_slots_and_target_index_shift(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_remove'),'Material removal tool is missing')
        a,b=list(self.obj.data.materials);c=bpy.data.materials.new('Target')
        self.obj.data.materials.append(a);self.obj.data.materials.append(c)
        for f,i in zip(self.bm.faces,(0,1,2,3)):f.material_index=i
        bmesh.update_edit_mesh(self.obj.data);self.obj.active_material_index=0
        self.assertEqual(bpy.ops.kmtr.material_remove(target='SLOT_3'),{'FINISHED'})
        self.bm=bmesh.from_edit_mesh(self.obj.data);self.bm.faces.ensure_lookup_table()
        self.assertEqual(list(self.obj.data.materials),[b,c])
        self.assertEqual([f.material_index for f in self.bm.faces],[1,0,1,1])
        self.assertEqual(self.obj.active_material_index,1)

    def test_material_remove_object_linked_slots_keep_effective_target(self):
        self.obj.data.materials.append(bpy.data.materials.new('DataThird'))
        mats=[bpy.data.materials.new(name) for name in ('ObjectA','ObjectSource','ObjectTarget')]
        for slot,mat in zip(self.obj.material_slots,mats):slot.link='OBJECT';slot.material=mat
        for f,i in zip(self.bm.faces,(0,1,2,1)):f.material_index=i
        bmesh.update_edit_mesh(self.obj.data);self.obj.active_material_index=1
        self.assertEqual(bpy.ops.kmtr.material_remove(target='SLOT_2'),{'FINISHED'})
        self.bm=bmesh.from_edit_mesh(self.obj.data);self.bm.faces.ensure_lookup_table()
        self.assertEqual([s.material for s in self.obj.material_slots],[mats[0],mats[2]])
        self.assertTrue(all(s.link=='OBJECT' for s in self.obj.material_slots))
        self.assertEqual([f.material_index for f in self.bm.faces],[0,1,1,1])

    def test_material_remove_invalid_target_and_shared_mesh_leave_data_and_preview(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_remove'),'Material removal tool is missing')
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL')
        self.obj.active_material_index=1;plan=self.addon._runtime['repair_preview'];before=self.fingerprint()
        for token in ('SLOT_1','SLOT_999','invalid'):
            self.assertEqual(bpy.ops.kmtr.material_remove(target=token),{'CANCELLED'})
            self.assertEqual(self.fingerprint(),before);self.assertIs(self.addon._runtime['repair_preview'],plan)
        other=bpy.data.objects.new('SharedMesh',self.obj.data);bpy.context.collection.objects.link(other)
        self.assertEqual(bpy.ops.kmtr.material_remove(target='MAIN'),{'CANCELLED'})
        self.assertEqual(self.fingerprint(),before);self.assertIs(self.addon._runtime['repair_preview'],plan)
        bpy.data.objects.remove(other,do_unlink=True)
        bpy.ops.kmtr.material_remove(target='MAIN')
        self.assertIsNone(self.addon._runtime['repair_preview'])

    def test_material_remove_empty_slot_and_reject_last_used_slot(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_remove'),'Material removal tool is missing')
        self.obj.data.materials.append(bpy.data.materials.new('EmptySource'));self.obj.active_material_index=2
        self.assertEqual(bpy.ops.kmtr.material_remove(target='MAIN'),{'FINISHED'})
        self.obj.active_material_index=1;bpy.ops.kmtr.material_remove(target='MAIN')
        self.obj.active_material_index=0
        self.assertEqual(bpy.ops.kmtr.material_remove(target='MAIN'),{'CANCELLED'})
        self.assertEqual(len(self.obj.data.materials),1)
        self.bm=bmesh.from_edit_mesh(self.obj.data);self.bm.faces.ensure_lookup_table()
        bmesh.ops.delete(self.bm,geom=list(self.bm.verts),context='VERTS');bmesh.update_edit_mesh(self.obj.data)
        self.assertEqual(bpy.ops.kmtr.material_remove(target='MAIN'),{'FINISHED'})
        self.assertEqual(len(self.obj.data.materials),0)

    def test_material_remove_undo_and_isolation_restore(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_remove'),'Material removal tool is missing')
        self.select({1});bpy.ops.kmtr.isolate(action='HIDE');before=self.fingerprint()
        self.obj.active_material_index=1;bpy.ops.ed.undo_push(message='Before material removal')
        bpy.ops.kmtr.material_remove(target='MAIN')
        self.bm=bmesh.from_edit_mesh(self.obj.data);self.bm.faces.ensure_lookup_table()
        bpy.ops.ed.undo()
        self.assertEqual(bpy.context.object.mode,'OBJECT')
        self.assertEqual(len(bpy.context.object.data.materials),2)
        bpy.ops.ed.redo()
        self.assertEqual(len(bpy.context.object.data.materials),1)
        self.assertTrue(all(f.material_index==0 for f in bpy.context.object.data.polygons))
        bpy.ops.ed.undo()
        bpy.ops.object.mode_set(mode='EDIT');self.obj=bpy.context.edit_object
        self.bm=bmesh.from_edit_mesh(self.obj.data);self.bm.faces.ensure_lookup_table()
        after=self.fingerprint()
        for index in (0,1,3,4):self.assertEqual(after[index],before[index])
        self.assertEqual(sorted(after[2]),sorted(before[2]))
        self.assertEqual(bpy.ops.kmtr.isolate(action='RESTORE'),{'FINISHED'})
        self.assertEqual([f.hide for f in self.bm.faces],[False,False,False,True])

    def test_material_visibility_toggle_preserves_other_materials_and_export_data(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_visibility'),'Material visibility tool is missing')
        before=self.fingerprint();self.obj.active_material_index=1
        self.assertEqual(bpy.ops.kmtr.material_visibility(action='TOGGLE',index=0),{'FINISHED'})
        self.assertEqual([f.hide for f in self.bm.faces],[True,False,True,True])
        self.assertEqual(self.selected(),{1});self.assertEqual(self.obj.active_material_index,1)
        self.assertEqual(bpy.ops.kmtr.material_visibility(action='TOGGLE',index=0),{'FINISHED'})
        self.assertEqual([f.hide for f in self.bm.faces],[False,False,False,True])
        self.assertEqual(self.selected(),{1});self.assertEqual(self.fingerprint(),before)

    def test_material_visibility_show_mixed_material_and_duplicate_slots(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_visibility'),'Material visibility tool is missing')
        self.obj.data.materials.append(self.obj.data.materials[0])
        self.bm.faces[2].material_index=2;bmesh.update_edit_mesh(self.obj.data)
        self.assertEqual(bpy.ops.kmtr.material_visibility(action='HIDE',index=2),{'FINISHED'})
        self.assertTrue(self.bm.faces[0].hide and self.bm.faces[2].hide)
        stats=self.addon.material_visibility_stats(self.obj,self.bm)
        self.assertEqual(stats[0],stats[2]);self.assertEqual(stats[0],(0,2))
        self.assertEqual(bpy.ops.kmtr.material_visibility(action='SHOW',index=1),{'FINISHED'})
        self.assertFalse(self.bm.faces[1].hide or self.bm.faces[3].hide)
        self.assertTrue(self.bm.faces[0].hide and self.bm.faces[2].hide)
        self.assertFalse(self.bm.faces[3].select)

    def test_material_visibility_shared_edges_and_undo(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_visibility'),'Material visibility tool is missing')
        bmesh.ops.delete(self.bm,geom=list(self.bm.verts),context='VERTS')
        bmesh.ops.create_cube(self.bm,size=1);self.bm.faces.ensure_lookup_table()
        for f in self.bm.faces:f.material_index=1
        self.bm.faces[0].material_index=0;self.select(set(range(6)))
        bpy.ops.ed.undo_push(message='Before material hide')
        bpy.ops.kmtr.material_visibility(action='HIDE',index=0)
        self.assertTrue(self.bm.faces[0].hide);self.assertFalse(self.bm.faces[0].select)
        self.assertTrue(all(not f.hide and f.select for f in list(self.bm.faces)[1:]))
        bpy.ops.ed.undo_push(message='After material hide');self.undo_refresh()
        self.assertTrue(all(not f.hide for f in self.bm.faces))
        self.assertEqual(self.selected(),set(range(6)))

    def test_material_visibility_invalidation_noop_and_isolation_restore(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_material_visibility'),'Material visibility tool is missing')
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL')
        plan=self.addon._runtime['repair_preview']
        bpy.ops.kmtr.material_visibility(action='SHOW',index=1)
        self.assertIs(self.addon._runtime['repair_preview'],plan)
        self.assertEqual(bpy.ops.kmtr.material_visibility(action='HIDE',index=999),{'CANCELLED'})
        self.assertIs(self.addon._runtime['repair_preview'],plan)
        bpy.ops.kmtr.material_visibility(action='HIDE',index=1)
        self.assertIsNone(self.addon._runtime['repair_preview'])
        bpy.ops.kmtr.material_visibility(action='SHOW',index=1)
        self.select({0});bpy.ops.kmtr.isolate(action='HIDE')
        bpy.ops.kmtr.material_visibility(action='SHOW',index=1)
        self.assertTrue(self.addon._isolation_layers(self.bm))
        bpy.ops.kmtr.isolate(action='RESTORE')
        self.assertTrue(all(not f.hide for f in self.bm.faces))

    def test_invert_and_clear_visible_faces_only(self):
        self.select({0})
        bpy.ops.kmtr.selection_action(action='INVERT')
        self.assertEqual(self.selected(), {1, 2})
        bpy.ops.kmtr.selection_action(action='CLEAR')
        self.assertEqual(self.selected(), set())
        self.assertTrue(self.bm.faces[3].hide)

    def test_store_restore_selection_and_reject_changed_topology(self):
        self.select({0, 2})
        bpy.ops.kmtr.selection_memory(action='STORE')
        self.select({1})
        bpy.ops.kmtr.selection_memory(action='RESTORE')
        self.assertEqual(self.selected(), {0, 2})
        self.bm.verts.new((40, 40, 40))
        bmesh.update_edit_mesh(self.obj.data)
        self.select({1})
        outcome = bpy.ops.kmtr.selection_memory(action='RESTORE')
        self.assertEqual(outcome, {'CANCELLED'})
        self.assertEqual(self.selected(), {1})

    def test_mask_targets_are_correct_and_change_no_export_data(self):
        self.select({0})
        before = self.fingerprint()
        cases = [('SELECTED', {0}), ('OTHERS', {1, 2}), ('MATERIAL', {0, 2}), ('OTHER_MATERIALS', {1}), ('OFF', set())]
        for mode, want in cases:
            self.assertEqual(set(self.addon.mask_face_indices(self.bm, mode, 0)), want)
            self.assertEqual(bpy.ops.kmtr.preview(mode=mode), {'FINISHED'})
            self.assertEqual(self.fingerprint(), before)
        self.assertEqual(self.selected(), {0})

    def test_material_preview_colors_are_independent_and_change_no_export_data(self):
        before = self.fingerprint()
        settings = bpy.context.window_manager.kmtr_settings
        settings.material_preview_color = (0.2, 0.6, 0.9)
        settings.material_preview_opacity = 0.65
        self.assertEqual(bpy.ops.kmtr.material_color(action='APPLY'), {'FINISHED'})
        self.obj.active_material_index = 1
        settings.material_preview_color = (0.9, 0.6, 0.1)
        self.assertEqual(bpy.ops.kmtr.material_color(action='APPLY'), {'FINISHED'})
        groups = self.addon.material_color_groups(self.obj, self.bm)
        self.assertEqual([set(ids) for color, ids in groups], [{0, 2}, {1}])
        self.assertAlmostEqual(groups[0][0][2], 0.9, places=5)
        self.assertAlmostEqual(groups[1][0][0], 0.9, places=5)
        self.assertAlmostEqual(groups[0][0][3], 0.65, places=5)
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(bpy.ops.kmtr.material_color(action='CLEAR_ACTIVE'), {'FINISHED'})
        self.assertEqual([set(ids) for color, ids in self.addon.material_color_groups(self.obj, self.bm)], [{0, 2}])
        self.assertEqual(bpy.ops.kmtr.material_color(action='CLEAR_ALL'), {'FINISHED'})
        self.assertEqual(self.addon.material_color_groups(self.obj, self.bm), ())
        self.assertEqual(self.fingerprint(), before)

    def test_color_preview_tracks_material_reassignment_and_normal_view_clears_it(self):
        settings = bpy.context.window_manager.kmtr_settings
        settings.material_preview_color = (0.1, 0.8, 0.4)
        bpy.ops.kmtr.material_color(action='APPLY')
        self.bm.faces[2].material_index = 1
        bmesh.update_edit_mesh(self.obj.data)
        self.assertEqual([set(ids) for color, ids in self.addon.material_color_groups(self.obj, self.bm)], [{0}])
        bpy.ops.kmtr.preview(mode='OFF')
        self.assertEqual(self.addon.material_color_groups(self.obj, self.bm), ())

    def test_color_preview_lifecycle_clears_temporary_colors(self):
        bpy.ops.kmtr.material_color(action='APPLY')
        self.assertTrue(self.addon.material_color_groups(self.obj, self.bm))
        self.addon.unregister()
        self.addon.register()
        self.assertEqual(self.addon.material_color_groups(self.obj, self.bm), ())

    def test_random_preview_colors_all_materials_are_distinct_and_export_safe(self):
        before = self.fingerprint()
        self.obj.data.materials.append(self.obj.data.materials[0])
        before = self.fingerprint()
        bpy.ops.kmtr.preview(mode='OTHERS')
        self.assertEqual(bpy.ops.kmtr.material_color(action='RANDOM_ALL', seed=17), {'FINISHED'})
        colors = self.addon._runtime['material_colors']
        self.assertEqual(len(colors), 2)
        self.assertEqual(len(set(colors.values())), 2)
        self.assertEqual(bpy.context.window_manager.kmtr_settings.preview_mode, 'OFF')
        first = dict(colors)
        bpy.ops.kmtr.material_color(action='RANDOM_ALL', seed=23)
        self.assertNotEqual(first, colors)
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(self.selected(), {1})

    def test_isolation_restores_preexisting_hidden_flags(self):
        self.select({0})
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.isolate(action='HIDE'), {'FINISHED'})
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {1, 2, 3})
        self.assertEqual(bpy.ops.kmtr.isolate(action='RESTORE'), {'FINISHED'})
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {3})
        self.assertEqual(self.fingerprint(), before)

    def test_assignment_changes_only_selected_faces(self):
        self.select({1})
        self.assertEqual(bpy.ops.kmtr.assign_material(), {'FINISHED'})
        self.assertEqual([f.material_index for f in self.bm.faces], [0, 0, 0, 1])

    def test_open_boundary_scan_closed_cube_and_single_missing_face(self):
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=2.0)
            self.assertEqual(self.addon.find_open_boundaries(bm), [])
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES_ONLY')
            regions = self.addon.find_open_boundaries(bm)
            self.assertEqual(len(regions), 1)
            self.assertEqual(regions[0]['edge_count'], 4)
            self.assertTrue(regions[0]['closed'])
            self.assertAlmostEqual(regions[0]['perimeter'], 8.0)
        finally:
            bm.free()

    def test_boundary_scan_two_holes_excludes_wire_and_hidden_is_not_a_hole(self):
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=2.0)
            bm.faces.ensure_lookup_table()
            first = bm.faces[0]
            opposite = next(f for f in bm.faces if f != first and not set(f.verts).intersection(first.verts))
            other = next(f for f in bm.faces if f not in {first, opposite})
            other.hide_set(True)
            self.assertEqual(self.addon.find_open_boundaries(bm), [])
            bmesh.ops.delete(bm, geom=[first, opposite], context='FACES_ONLY')
            a = bm.verts.new((20,20,20)); b = bm.verts.new((21,20,20)); bm.edges.new((a,b))
            regions = self.addon.find_open_boundaries(bm)
            self.assertEqual(len(regions), 2)
            self.assertEqual([r['edge_count'] for r in regions], [4,4])
            self.assertTrue(all(r['closed'] for r in regions))
        finally:
            bm.free()

    def test_hole_scan_does_not_modify_mesh_material_uv_or_selection(self):
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_scan(), {'FINISHED'})
        report = self.addon._runtime['hole_scan']
        self.assertEqual(len(report['regions']), 4)
        self.assertEqual(len(bpy.context.window_manager.kmtr_settings.hole_items), 4)
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(self.selected(), {1})

    def test_ignore_hole_is_read_only_survives_rescan_and_restores(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_hole_ignore'),'Ignore-opening tool is missing')
        bpy.ops.kmtr.hole_scan();before=self.fingerprint();selection=self.selected()
        ignored=self.addon._runtime['hole_scan']['regions'][1]['edges']
        bpy.context.window_manager.kmtr_settings.hole_active_index=1
        self.assertEqual(bpy.ops.kmtr.hole_ignore(action='IGNORE'),{'FINISHED'})
        report=self.addon._runtime['hole_scan']
        self.assertEqual(len(report['regions']),3);self.assertEqual(report['ignored_count'],1)
        self.assertNotIn(ignored,[r['edges'] for r in report['regions']])
        bpy.ops.kmtr.hole_scan()
        self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),3)
        self.assertEqual(self.fingerprint(),before);self.assertEqual(self.selected(),selection)
        self.assertEqual(bpy.ops.kmtr.hole_ignore(action='RESTORE'),{'FINISHED'})
        self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),4)
        self.assertEqual(self.addon._runtime['hole_scan']['ignored_count'],0)

    def test_ignore_clears_pending_preview_and_excludes_it_from_repair(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_hole_ignore'),'Ignore-opening tool is missing')
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL')
        before=self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_ignore(action='IGNORE'),{'FINISHED'})
        self.assertIsNone(self.addon._runtime['repair_preview'])
        self.assertEqual(self.addon._runtime['hole_scan']['regions'],[])
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL'),{'CANCELLED'})
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='APPLY'),{'CANCELLED'})
        self.assertEqual(bpy.ops.kmtr.hole_repair(),{'CANCELLED'})
        self.assertEqual(self.fingerprint(),before)

    def test_ignore_survives_material_filter_without_affecting_other_material(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_hole_ignore'),'Ignore-opening tool is missing')
        s=bpy.context.window_manager.kmtr_settings
        self.obj.active_material_index=1;s.hole_active_material_only=True
        try:
            bpy.ops.kmtr.hole_scan()
            self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),2)
            bpy.ops.kmtr.hole_ignore(action='IGNORE')
            self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),1)
            self.obj.active_material_index=0;bpy.ops.kmtr.hole_scan()
            self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),2)
            self.assertEqual(self.addon._runtime['hole_scan']['ignored_count'],0)
            s.hole_active_material_only=False;bpy.ops.kmtr.hole_scan()
            self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),3)
        finally:s.hole_active_material_only=False

    def test_ignore_resets_after_external_topology_edit_and_lifecycle(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_hole_ignore'),'Ignore-opening tool is missing')
        bpy.ops.kmtr.hole_scan();bpy.ops.kmtr.hole_ignore(action='IGNORE')
        self.bm.verts.new((10,10,10));bmesh.update_edit_mesh(self.obj.data)
        bpy.ops.kmtr.hole_scan()
        self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),4)
        bpy.ops.kmtr.hole_ignore(action='IGNORE');self.addon.clear_runtime();bpy.ops.kmtr.hole_scan()
        self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),4)

    def test_ignore_preserved_after_other_hole_repaired(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_hole_ignore'),'Ignore-opening tool is missing')
        self.make_cube_hole(size=.01)
        # Add a separate intentional open surface to ignore.
        verts=[self.bm.verts.new(co) for co in [(1,0,0),(1.01,0,0),(1.01,.01,0),(1,.01,0)]]
        self.bm.faces.new(verts).material_index=0
        self.bm.normal_update();bmesh.update_edit_mesh(self.obj.data);bpy.ops.kmtr.hole_scan()
        regions=self.addon._runtime['hole_scan']['regions']
        index=next(i for i,r in enumerate(regions) if r['materials']==(0,))
        bpy.ops.kmtr.hole_ignore(action='IGNORE',index=index)
        bpy.context.window_manager.kmtr_settings.patch_max_size=.15
        bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL')
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='APPLY'),{'FINISHED'})
        self.assertEqual(len(self.addon._runtime['hole_scan']['regions']),0)
        self.assertEqual(self.addon._runtime['hole_scan']['ignored_count'],1)

    def test_ignore_invalid_index_does_not_clear_existing_preview(self):
        self.assertTrue(hasattr(self.addon,'KMTR_OT_hole_ignore'),'Ignore-opening tool is missing')
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL')
        plan=self.addon._runtime['repair_preview']
        self.assertEqual(bpy.ops.kmtr.hole_ignore(action='IGNORE',index=999),{'CANCELLED'})
        self.assertIs(self.addon._runtime['repair_preview'],plan)

    def test_language_switch_preserves_pending_patch_and_original_data(self):
        self.assertTrue(hasattr(self.addon,'_t'),'UI language support is missing')
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL')
        plan=self.addon._runtime['repair_preview'];before=self.fingerprint();selected=self.selected()
        s=bpy.context.window_manager.kmtr_settings
        try:
            s.language='EN'
            self.assertEqual(self.addon._t('Bu açıklığı yoksay'),'Ignore this opening')
            self.addon._patch_tick()
            self.assertIs(self.addon._runtime['repair_preview'],plan)
            self.assertEqual(self.fingerprint(),before);self.assertEqual(self.selected(),selected)
            s.language='TR'
            self.assertEqual(self.addon._t('Bu açıklığı yoksay'),'Bu açıklığı yoksay')
        finally:s.language='TR'

    def test_language_switch_preserves_isolation_and_enum_identifiers(self):
        self.assertTrue(hasattr(self.addon,'_t'),'UI language support is missing')
        self.select({1});bpy.ops.kmtr.isolate(action='HIDE')
        before=self.fingerprint();hidden=tuple(f.hide for f in self.bm.faces)
        s=bpy.context.window_manager.kmtr_settings
        try:
            s.language='EN'
            items=self.addon._move_target_items(s,bpy.context)
            self.assertEqual(items[0][0],'MAIN');self.assertEqual(items[0][1],'Main material (slot 1)')
            self.assertEqual(items[1][1],self.obj.material_slots[1].name)
            self.assertEqual(s.smart_mode,'AUTO')
            smart=self.addon._smart_mode_items(s,bpy.context)
            self.assertEqual([x[0] for x in smart],['AUTO','MATERIAL','SURFACE'])
            self.assertEqual(smart[0][1],'Automatic')
            self.assertEqual(tuple(f.hide for f in self.bm.faces),hidden)
            self.assertEqual(self.fingerprint(),before)
            self.assertTrue(self.addon._isolation_layers(self.bm))
        finally:s.language='TR'

    def test_empty_mesh_hole_scan_and_overlay_tick_are_safe(self):
        bmesh.ops.delete(self.bm, geom=list(self.bm.verts), context='VERTS')
        bmesh.update_edit_mesh(self.obj.data)
        self.assertEqual(bpy.ops.kmtr.hole_scan(), {'FINISHED'})
        self.assertEqual(self.addon._runtime['hole_scan']['regions'], [])
        self.assertEqual(self.addon._holes_tick(), 0.25)
        self.assertEqual(self.addon._runtime['hole_positions'], [])

    def make_cube_hole(self, size=0.01):
        bmesh.ops.delete(self.bm, geom=list(self.bm.verts), context='VERTS')
        bmesh.ops.create_cube(self.bm, size=size)
        self.bm.faces.ensure_lookup_table()
        for f in self.bm.faces:
            f.material_index = 1
        removed_normal = self.bm.faces[0].normal.copy()
        bmesh.ops.delete(self.bm, geom=[self.bm.faces[0]], context='FACES_ONLY')
        self.bm.normal_update()
        bmesh.update_edit_mesh(self.obj.data)
        return removed_normal

    def test_small_hole_repair_material_normals_uv_preservation_and_undo(self):
        bpy.context.window_manager.kmtr_settings.repair_max_size = 0.02
        normal = self.make_cube_hole()
        uv = self.bm.loops.layers.uv.active
        for f in self.bm.faces:
            for i, loop in enumerate(f.loops): loop[uv].uv = ((i % 2)*0.5, (i//2)*0.5)
        old_faces = list(self.bm.faces)
        old_uvs = {f:tuple(tuple(l[uv].uv) for l in f.loops) for f in old_faces}
        bpy.ops.kmtr.hole_scan()
        bpy.ops.ed.undo_push(message='Before safe repair')
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'FINISHED'})
        self.assertEqual(len(self.bm.faces), 6)
        new_face = next(f for f in self.bm.faces if f not in old_faces)
        self.assertEqual(new_face.material_index, 1)
        self.assertGreater(new_face.normal.dot(normal), 0.99)
        for f in old_faces: self.assertEqual(tuple(tuple(l[uv].uv) for l in f.loops), old_uvs[f])
        self.assertEqual(self.addon.find_open_boundaries(self.bm), [])
        bpy.ops.ed.undo_push(message='After safe repair')
        self.undo_refresh()
        self.assertEqual(len(self.bm.faces), 5)

    def test_safe_repair_skips_large_mixed_hidden_and_existing_surface(self):
        bpy.context.window_manager.kmtr_settings.repair_max_size = 0.02
        self.make_cube_hole(size=2)
        bpy.ops.kmtr.hole_scan()
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'CANCELLED'})
        self.assertEqual(self.fingerprint(), before)
        self.make_cube_hole()
        region = self.addon.find_open_boundaries(self.bm)[0]
        self.bm.edges.ensure_lookup_table()
        self.bm.edges[region['edges'][0]].link_faces[0].material_index = 0
        bpy.ops.kmtr.hole_scan()
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'CANCELLED'})
        self.assertEqual(self.fingerprint(), before)
        self.make_cube_hole()
        self.bm.faces.ensure_lookup_table(); self.bm.faces[0].hide_set(True)
        bpy.ops.kmtr.hole_scan()
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'CANCELLED'})
        self.assertEqual(self.fingerprint(), before)

    def test_repair_does_not_duplicate_existing_open_quad_surface(self):
        bpy.context.window_manager.kmtr_settings.repair_max_size = 10
        bpy.ops.kmtr.hole_scan()
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'CANCELLED'})
        self.assertEqual(self.fingerprint(), before)

    def test_repair_rechecks_material_changes_after_scan(self):
        bpy.context.window_manager.kmtr_settings.repair_max_size = 0.02
        self.make_cube_hole()
        bpy.ops.kmtr.hole_scan()
        self.bm.edges.ensure_lookup_table()
        region = self.addon._runtime['hole_scan']['regions'][0]
        self.bm.edges[region['edges'][0]].link_faces[0].material_index = 0
        bmesh.update_edit_mesh(self.obj.data)
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'CANCELLED'})
        self.assertEqual(self.fingerprint(), before)

    def test_repair_rejects_tiny_existing_face_inside_patch_near_corner(self):
        bpy.context.window_manager.kmtr_settings.repair_max_size = 0.02
        self.make_cube_hole()
        region = self.addon.find_open_boundaries(self.bm)[0]
        self.bm.edges.ensure_lookup_table()
        edge = self.bm.edges[region['edges'][0]]
        a, b = edge.verts
        other = next(self.bm.edges[i].other_vert(a) for i in region['edges']
                     if self.bm.edges[i] != edge and a in self.bm.edges[i].verts)
        origin=a.co.copy();u=b.co-origin;v=other.co-origin
        verts=[self.bm.verts.new(origin+u*x+v*y) for x,y in [(0.06,0.06),(0.10,0.06),(0.06,0.10)]]
        self.bm.faces.new(verts).material_index = 1
        self.bm.normal_update();bmesh.update_edit_mesh(self.obj.data)
        bpy.ops.kmtr.hole_scan()
        before=self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'CANCELLED'})
        self.assertEqual(len(self.bm.faces), 6)
        self.assertEqual(self.fingerprint(), before)

    def test_repair_skips_warped_quad_and_overlapping_outer_border(self):
        bpy.context.window_manager.kmtr_settings.repair_max_size = 10
        bmesh.ops.delete(self.bm, geom=list(self.bm.verts), context='VERTS')
        base=[self.bm.verts.new(co) for co in [(0,0,0),(1,0,0),(1,1,0.5),(0,1,0)]]
        tip=self.bm.verts.new((0.5,0.5,2))
        for i in range(4):self.bm.faces.new((base[i],tip,base[(i+1)%4]))
        self.bm.normal_update();bmesh.update_edit_mesh(self.obj.data)
        bpy.ops.kmtr.hole_scan()
        before=self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'CANCELLED'})
        self.assertEqual(self.fingerprint(), before)
        bmesh.ops.delete(self.bm, geom=list(self.bm.verts), context='VERTS')
        outer=[self.bm.verts.new(co) for co in [(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)]]
        inner=[self.bm.verts.new(co) for co in [(-0.25,-0.25,0),(0.25,-0.25,0),(0.25,0.25,0),(-0.25,0.25,0)]]
        for i in range(4):self.bm.faces.new((outer[i],outer[(i+1)%4],inner[(i+1)%4],inner[i]))
        self.bm.normal_update();bmesh.update_edit_mesh(self.obj.data)
        bpy.ops.kmtr.hole_scan()
        self.assertEqual(bpy.ops.kmtr.hole_repair(), {'FINISHED'})
        self.assertEqual(len(self.bm.faces), 5)
        remaining=self.addon.find_open_boundaries(self.bm)
        self.assertEqual(len(remaining), 1)
        self.assertAlmostEqual(remaining[0]['perimeter'], 8.0)

    def test_selected_merge_by_distance_and_undo(self):
        bmesh.ops.delete(self.bm, geom=list(self.bm.verts), context='VERTS')
        a=self.bm.verts.new((0,0,0));b=self.bm.verts.new((0.000001,0,0))
        c=self.bm.verts.new((1,1,0));d=self.bm.verts.new((0,1,0))
        self.bm.faces.new((a,b,c,d))
        for v in self.bm.verts:v.select_set(v in {a,b})
        bmesh.update_edit_mesh(self.obj.data)
        bpy.ops.ed.undo_push(message='Before local merge')
        self.assertEqual(bpy.ops.kmtr.merge_selected(), {'FINISHED'})
        self.assertEqual(len(self.bm.verts), 3)
        bpy.ops.ed.undo_push(message='After local merge')
        self.undo_refresh()
        self.assertEqual(len(self.bm.verts), 4)

    def make_curved_hex_hole(self):
        bmesh.ops.delete(self.bm, geom=list(self.bm.verts), context='VERTS')
        loop=[self.bm.verts.new((0.04*math.cos(i*math.tau/6),0.04*math.sin(i*math.tau/6),
                               0.007 if i%2 else 0)) for i in range(6)]
        tip=self.bm.verts.new((0,0,0.12))
        for i in range(6):self.bm.faces.new((loop[i],tip,loop[(i+1)%6])).material_index=1
        self.bm.normal_update();bmesh.update_edit_mesh(self.obj.data)
        bpy.ops.kmtr.hole_scan()
        bpy.context.window_manager.kmtr_settings.patch_max_size=0.15

    def test_polygon_preview_is_read_only_and_cancel_clears(self):
        self.assertTrue(hasattr(self.addon,'build_repair_preview'), 'Repair preview is not implemented')
        self.make_curved_hex_hole()
        before=self.fingerprint();selected=self.selected()
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='BUILD',scope='ACTIVE'),{'FINISHED'})
        plan=self.addon._runtime['repair_preview']
        self.assertEqual(len(plan['patches']),1)
        self.assertEqual(len(plan['patches'][0]['triangles']),4)
        self.assertEqual(self.fingerprint(),before);self.assertEqual(self.selected(),selected)
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='CANCEL'),{'FINISHED'})
        self.assertIsNone(self.addon._runtime['repair_preview'])
        self.assertEqual(self.fingerprint(),before)

    def test_polygon_preview_applies_exact_triangles_material_uv_and_undo(self):
        self.assertTrue(hasattr(self.addon,'build_repair_preview'), 'Repair preview is not implemented')
        self.make_curved_hex_hole()
        old=list(self.bm.faces);uv=self.bm.loops.layers.uv.active
        old_uv={f:tuple(tuple(l[uv].uv) for l in f.loops) for f in old}
        bpy.ops.kmtr.repair_preview(action='BUILD',scope='ACTIVE')
        expected={frozenset(t) for t in self.addon._runtime['repair_preview']['patches'][0]['triangles']}
        bpy.ops.ed.undo_push(message='Before preview repair')
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='APPLY'),{'FINISHED'})
        self.bm.verts.index_update()
        added=[f for f in self.bm.faces if f not in old]
        self.assertEqual({frozenset(v.index for v in f.verts) for f in added},expected)
        self.assertTrue(all(f.material_index==1 for f in added))
        for f in old:self.assertEqual(tuple(tuple(l[uv].uv) for l in f.loops),old_uv[f])
        self.assertEqual(self.addon.find_open_boundaries(self.bm),[])
        self.assertIsNone(self.addon._runtime['repair_preview'])
        bpy.ops.ed.undo_push(message='After preview repair');self.undo_refresh()
        self.assertEqual(len(self.bm.faces),6)

    def test_polygon_preview_rejects_moved_vertices_before_apply(self):
        self.assertTrue(hasattr(self.addon,'build_repair_preview'), 'Repair preview is not implemented')
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ACTIVE')
        self.bm.verts.ensure_lookup_table();self.bm.verts[0].co.x+=0.001
        bmesh.update_edit_mesh(self.obj.data);before=self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='APPLY'),{'CANCELLED'})
        self.assertEqual(self.fingerprint(),before)

    def test_polygon_preview_rejects_material_change_but_allows_selection_change(self):
        self.assertTrue(hasattr(self.addon,'build_repair_preview'), 'Repair preview is not implemented')
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ACTIVE')
        self.select(set())
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='APPLY'),{'FINISHED'})
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ACTIVE')
        self.bm.faces.ensure_lookup_table();self.bm.faces[0].material_index=0
        bmesh.update_edit_mesh(self.obj.data);before=self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='APPLY'),{'CANCELLED'})
        self.assertEqual(self.fingerprint(),before)

    def test_polygon_preview_rejects_existing_surface_and_lifecycle_clears(self):
        self.assertTrue(hasattr(self.addon,'build_repair_preview'), 'Repair preview is not implemented')
        bpy.ops.kmtr.hole_scan();bpy.context.window_manager.kmtr_settings.patch_max_size=10
        before=self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL'),{'CANCELLED'})
        self.assertEqual(self.fingerprint(),before)
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ACTIVE')
        self.addon.clear_runtime()
        self.assertIsNone(self.addon._runtime['repair_preview'])

    def test_polygon_preview_rejects_uv_hide_and_transform_edits(self):
        self.assertTrue(hasattr(self.addon,'build_repair_preview'))
        for kind in ('UV','HIDE','TRANSFORM'):
            self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ACTIVE')
            self.bm.faces.ensure_lookup_table()
            if kind=='UV':
                layer=self.bm.loops.layers.uv.active
                self.bm.faces[0].loops[0][layer].uv.x+=.01
            elif kind=='HIDE':self.bm.faces[0].hide_set(True)
            else:self.obj.location.x+=.01
            bmesh.update_edit_mesh(self.obj.data);before=self.fingerprint()
            self.assertEqual(bpy.ops.kmtr.repair_preview(action='APPLY'),{'CANCELLED'},kind)
            self.assertEqual(self.fingerprint(),before)
        self.obj.location.x=0

    def test_polygon_preview_tick_discards_stale_geometry(self):
        self.assertTrue(hasattr(self.addon,'build_repair_preview'))
        self.make_curved_hex_hole();bpy.ops.kmtr.repair_preview(action='BUILD',scope='ACTIVE')
        self.bm.verts.ensure_lookup_table();self.bm.verts[0].co.z+=.001
        bmesh.update_edit_mesh(self.obj.data);self.addon._on_update()
        self.addon._patch_tick()
        self.assertIsNone(self.addon._runtime['repair_preview'])
        self.assertIn('yeniden',self.addon._runtime['patch_error'])

    def test_polygon_preview_does_not_reuse_an_existing_manifold_diagonal(self):
        from mathutils import Vector
        self.make_cube_hole();bpy.ops.kmtr.hole_scan()
        bpy.context.window_manager.kmtr_settings.patch_max_size=.15
        proposal=self.addon.build_repair_preview(self.obj,self.bm,self.addon._runtime['hole_scan']['regions'],.15)
        triangles=proposal['patches'][0]['triangles']
        diagonal=set(triangles[0])&set(triangles[1])
        self.bm.verts.ensure_lookup_table()
        a,c=[self.bm.verts[i] for i in diagonal]
        p,q,r=[self.bm.verts[i].co for i in triangles[0]]
        normal=(q-p).cross(r-p).normalized()
        tangent=(c.co-a.co).cross(normal).normalized()
        midpoint=(a.co+c.co)*.5
        b=self.bm.verts.new(midpoint+normal*.03+tangent*.01)
        d=self.bm.verts.new(midpoint+normal*.03-tangent*.01)
        for verts in ((a,c,b),(a,d,c),(a,b,d),(b,c,d)):
            self.bm.faces.new(verts).material_index=1
        self.bm.normal_update();bmesh.update_edit_mesh(self.obj.data)
        bpy.ops.kmtr.hole_scan();before=self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.repair_preview(action='BUILD',scope='ALL'),{'CANCELLED'})
        self.assertEqual(self.fingerprint(),before)

    def test_hole_focus_selects_boundary_and_rejects_changed_topology(self):
        bpy.ops.kmtr.hole_scan()
        report = self.addon._runtime['hole_scan']
        visible_index = next(i for i,r in enumerate(report['regions']) if not r['hidden_edges'])
        wanted = set(report['regions'][visible_index]['edges'])
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.hole_focus(index=visible_index, focus_view=False), {'FINISHED'})
        self.assertEqual({e.index for e in self.bm.edges if e.select}, wanted)
        self.assertEqual(self.fingerprint(), before)
        self.bm.verts.new((70,70,70));bmesh.update_edit_mesh(self.obj.data)
        self.assertEqual(bpy.ops.kmtr.hole_focus(index=visible_index, focus_view=False), {'CANCELLED'})

    def test_red_marks_preserve_orange_selection_and_export_data(self):
        self.select({0, 1, 2})
        before = self.fingerprint()
        self.assertEqual(self.addon.mark_red_faces(bpy.context, {1, 2, 3}), {1, 2})
        self.assertEqual(self.selected(), {0, 1, 2})
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(self.addon.mark_red_faces(bpy.context, {2}, erase=True), {1})
        self.assertEqual(self.fingerprint(), before)
        self.addon.clear_red_marks()
        self.assertEqual(self.addon.red_face_indices(self.obj, self.bm), set())

    def test_repeated_ctrl_stroke_toggles_red_without_changing_selection_or_material(self):
        self.select({0, 1})
        before = self.fingerprint()
        erase = self.addon.red_stroke_erases(self.obj, self.bm, 1)
        self.assertFalse(erase)
        self.addon.mark_red_faces(bpy.context, {1}, erase=erase)
        self.assertEqual(self.addon.red_face_indices(self.obj, self.bm), {1})
        erase = self.addon.red_stroke_erases(self.obj, self.bm, 1)
        self.assertTrue(erase)
        self.addon.mark_red_faces(bpy.context, {1}, erase=erase)
        self.assertEqual(self.addon.red_face_indices(self.obj, self.bm), set())
        self.assertEqual(self.selected(), {0, 1})
        self.assertEqual(self.fingerprint(), before)
        self.assertTrue(self.addon.red_stroke_erases(self.obj, self.bm, 0, force_erase=True))

    def test_red_transfer_only_marked_faces_to_first_material_and_undo(self):
        self.select({0, 1, 2})
        bpy.ops.ed.undo_push(message='Before red transfer')
        self.addon.mark_red_faces(bpy.context, {1})
        self.assertEqual(bpy.ops.kmtr.red_action(action='TRANSFER'), {'FINISHED'})
        self.assertEqual([f.material_index for f in self.bm.faces], [0, 0, 0, 1])
        self.assertEqual(self.selected(), {0, 2})
        self.assertEqual(self.addon.red_face_indices(self.obj, self.bm), set())
        bpy.ops.ed.undo_push(message='After red transfer')
        self.undo_refresh()
        self.assertEqual([f.material_index for f in self.bm.faces], [0, 1, 0, 1])

    def test_red_rejects_changed_topology_without_changing_materials(self):
        self.select({1})
        self.addon.mark_red_faces(bpy.context, {1})
        self.bm.verts.new((70, 70, 70))
        bmesh.update_edit_mesh(self.obj.data)
        self.assertEqual(bpy.ops.kmtr.red_action(action='TRANSFER'), {'CANCELLED'})
        self.assertEqual([f.material_index for f in self.bm.faces], [0, 1, 0, 1])

    def test_red_rejects_reassigned_faces_without_overwriting_new_material(self):
        self.select({1})
        self.addon.mark_red_faces(bpy.context, {1})
        self.bm.faces[1].material_index = 0
        bmesh.update_edit_mesh(self.obj.data)
        self.assertEqual(bpy.ops.kmtr.red_action(action='TRANSFER'), {'CANCELLED'})
        self.assertEqual([f.material_index for f in self.bm.faces], [0, 0, 0, 1])

    def test_red_unselected_and_hidden_faces_cannot_be_marked(self):
        self.select({1})
        self.assertEqual(self.addon.mark_red_faces(bpy.context, {0, 3}), set())
        self.assertEqual(bpy.ops.kmtr.red_action(action='TRANSFER'), {'CANCELLED'})
        self.assertEqual([f.material_index for f in self.bm.faces], [0, 1, 0, 1])

    def test_native_tool_selection_can_be_marked_and_unmarked_without_assignment(self):
        self.select({0, 1})
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.red_action(action='MARK_SELECTION'), {'FINISHED'})
        self.assertEqual(self.addon.red_face_indices(self.obj, self.bm), {0, 1})
        self.assertEqual(self.selected(), {0, 1})
        self.select({1})
        self.assertEqual(bpy.ops.kmtr.red_action(action='UNMARK_SELECTION'), {'FINISHED'})
        self.assertEqual(self.addon.red_face_indices(self.obj, self.bm), {0})
        self.assertEqual(self.fingerprint(), before)

    def test_red_shortcut_registered_for_box_and_circle_tools(self):
        keyconfig = bpy.context.window_manager.keyconfigs.addon
        if keyconfig is None:
            self.skipTest('No addon key configuration in this environment')
        for name in ['3D View', '3D View Tool: Select Box', '3D View Tool: Select Circle']:
            keymap = keyconfig.keymaps.get(name)
            self.assertIsNotNone(keymap)
            matches = [i for i in keymap.keymap_items if i.idname == 'kmtr.red_paint']
            self.assertEqual({(i.type, i.value, i.ctrl, i.shift) for i in matches},
                             {('LEFTMOUSE', 'PRESS', 1, 0), ('LEFTMOUSE', 'PRESS', 1, 1)})

    def test_remove_from_material_goes_to_main_slot_and_can_be_undone(self):
        self.obj.active_material_index = 1
        self.select({1})
        bpy.ops.ed.undo_push(message='Before material removal')
        self.assertEqual(bpy.ops.kmtr.remove_from_material(target='MAIN'), {'FINISHED'})
        self.assertEqual([f.material_index for f in self.bm.faces], [0, 0, 0, 1])
        self.assertEqual(len(self.obj.data.materials), 2)
        bpy.ops.ed.undo_push(message='After material removal')
        self.undo_refresh()
        self.assertEqual([f.material_index for f in self.bm.faces], [0, 1, 0, 1])

    def test_remove_to_chosen_material_filters_source_and_hidden_faces(self):
        self.select({0, 1, 2})
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.remove_from_material(target='SLOT_1'), {'FINISHED'})
        self.assertEqual([f.material_index for f in self.bm.faces], [1, 1, 1, 1])
        self.assertEqual(self.selected(), {0, 1, 2})
        after = self.fingerprint()
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[2:], after[2:])
        self.assertTrue(self.bm.faces[3].hide)

    def test_remove_invalid_same_target_and_empty_selection_cancel_cleanly(self):
        before = self.fingerprint()
        self.assertEqual(bpy.ops.kmtr.remove_from_material(target='MAIN'), {'CANCELLED'})
        self.assertEqual(self.fingerprint(), before)
        self.obj.active_material_index = 1
        self.select(set())
        self.assertEqual(bpy.ops.kmtr.remove_from_material(target='MAIN'), {'CANCELLED'})
        self.assertEqual(self.fingerprint(), before)

    def test_smart_auto_groups_disconnected_assigned_material(self):
        self.bm.faces[3].hide_set(False)
        before = self.fingerprint()
        self.assertEqual(set(self.addon.smart_face_indices(self.bm, 1, mode='AUTO')), {1, 3})
        self.assertEqual(set(self.addon.smart_face_indices(self.bm, 0, mode='AUTO')), {0})
        self.assertEqual(set(self.addon.smart_face_indices(self.bm, 0, mode='MATERIAL')), {0, 2})
        self.assertEqual(self.fingerprint(), before)

    def test_smart_surface_stops_at_crease_material_and_seam(self):
        bm = bmesh.new()
        try:
            coordinates = {}
            def face(points):
                verts = []
                for point in points:
                    if point not in coordinates:
                        coordinates[point] = bm.verts.new(point)
                    verts.append(coordinates[point])
                return bm.faces.new(verts)
            face([(0,0,0),(1,0,0),(1,1,0),(0,1,0)])
            face([(1,0,0),(2,0,0),(2,1,0),(1,1,0)])
            face([(2,0,0),(2,0,1),(2,1,1),(2,1,0)])
            face([(-1,0,0),(0,0,0),(0,1,0),(-1,1,0)]).material_index = 1
            bm.verts.index_update(); bm.faces.index_update(); bm.faces.ensure_lookup_table(); bm.normal_update()
            self.assertEqual(set(self.addon.smart_face_indices(bm, 0, mode='SURFACE', angle=math.radians(35))), {0, 1})
            self.assertEqual(set(self.addon.smart_face_indices(bm, 0, mode='SURFACE', angle=math.radians(100))), {0, 1, 2})
            edge = next(e for e in bm.edges if {f.index for f in e.link_faces} == {0, 1})
            edge.seam = True
            self.assertEqual(set(self.addon.smart_face_indices(bm, 0, mode='SURFACE', angle=math.radians(100))), {0})
        finally:
            bm.free()

    def test_smart_invalid_hidden_seed_and_visible_ray_picking(self):
        self.assertEqual(tuple(self.addon.smart_face_indices(self.bm, -1)), ())
        self.assertEqual(tuple(self.addon.smart_face_indices(self.bm, 3)), ())
        self.assertEqual(self.addon.raycast_face_index(self.bm, (0.5, 0.5, 1), (0, 0, -1)), 0)
        self.assertIsNone(self.addon.raycast_face_index(self.bm, (6.5, 0.5, 1), (0, 0, -1)))

    def test_smart_operator_replace_add_subtract_does_not_assign_materials(self):
        before = self.fingerprint()
        bpy.ops.kmtr.smart_select(face_index=0, action='REPLACE')
        self.assertEqual(self.selected(), {0})
        bpy.ops.kmtr.smart_select(face_index=2, action='ADD')
        self.assertEqual(self.selected(), {0, 2})
        bpy.ops.kmtr.smart_select(face_index=0, action='SUBTRACT')
        self.assertEqual(self.selected(), {2})
        self.assertEqual(self.fingerprint(), before)

    def test_new_material_name_and_empty_selection(self):
        self.select(set())
        count = len(self.obj.data.materials)
        self.assertEqual(bpy.ops.kmtr.new_material(name='M_Deneme'), {'CANCELLED'})
        self.assertEqual(len(self.obj.data.materials), count)
        self.select({2})
        self.assertEqual(bpy.ops.kmtr.new_material(name='M_Deneme'), {'FINISHED'})
        self.assertEqual(self.obj.data.materials[self.bm.faces[2].material_index].name, 'M_Deneme')
        self.assertEqual([self.bm.faces[i].material_index for i in [0, 1, 3]], [0, 1, 1])

    def test_empty_selection_isolation_has_no_side_effects(self):
        self.select(set())
        self.assertEqual(bpy.ops.kmtr.isolate(action='HIDE'), {'CANCELLED'})
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {3})

    def test_lifecycle_disable_reenable_clears_preview(self):
        bpy.ops.kmtr.preview(mode='OTHERS')
        self.addon.unregister()
        self.addon.register()
        self.assertEqual(bpy.context.window_manager.kmtr_settings.preview_mode, 'OFF')
        self.assertEqual(bpy.ops.kmtr.preview(mode='OFF'), {'FINISHED'})

    def undo_refresh(self):
        bpy.ops.ed.undo()
        self.obj = bpy.context.edit_object
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        self.bm.faces.ensure_lookup_table()

    def test_undo_restore_keeps_original_hidden_faces_recoverable(self):
        self.select({0})
        bpy.ops.ed.undo_push(message='Before isolate')
        bpy.ops.kmtr.isolate(action='HIDE')
        bpy.ops.ed.undo_push(message='Isolated')
        bpy.ops.kmtr.isolate(action='RESTORE')
        bpy.ops.ed.undo_push(message='Restored')
        self.undo_refresh()
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {1, 2, 3})
        self.assertEqual(bpy.ops.kmtr.isolate(action='RESTORE'), {'FINISHED'})
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {3})

    def test_undo_hide_allows_isolating_again(self):
        self.select({0})
        bpy.ops.ed.undo_push(message='Before isolate')
        bpy.ops.kmtr.isolate(action='HIDE')
        bpy.ops.ed.undo_push(message='Isolated')
        self.undo_refresh()
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {3})
        self.assertEqual(bpy.ops.kmtr.isolate(action='HIDE'), {'FINISHED'})
        self.assertEqual(bpy.ops.kmtr.isolate(action='RESTORE'), {'FINISHED'})
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {3})

    def test_undo_different_isolation_baselines_with_identical_hidden_result(self):
        self.select({0})
        bpy.ops.ed.undo_push(message='Original hidden face3')
        bpy.ops.kmtr.isolate(action='HIDE')
        bpy.ops.ed.undo_push(message='First isolate')
        bpy.ops.kmtr.isolate(action='RESTORE')
        bpy.ops.ed.undo_push(message='First restore')
        bpy.ops.kmtr.isolate(action='REVEAL')
        bpy.ops.ed.undo_push(message='No originally hidden faces')
        bpy.ops.kmtr.isolate(action='HIDE')
        bpy.ops.ed.undo_push(message='Second isolate')
        self.undo_refresh(); self.undo_refresh(); self.undo_refresh()
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {1, 2, 3})
        self.assertEqual(bpy.ops.kmtr.isolate(action='RESTORE'), {'FINISHED'})
        self.assertEqual({f.index for f in self.bm.faces if f.hide}, {3})

    def test_disabling_after_object_rename_restores_hidden_flags(self):
        self.select({0})
        bpy.ops.kmtr.isolate(action='HIDE')
        self.obj.name = 'RenamedFixture'
        self.addon.unregister()
        try:
            self.assertEqual({f.index for f in self.bm.faces if f.hide}, {3})
        finally:
            self.addon.register()

    @unittest.skipIf(bpy.app.background, 'Native interactive selection tool requires a GUI; covered by live viewport test')
    def test_brush_uses_native_tool_with_explicit_add_subtract_modes(self):
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            bpy.ops.kmtr.brush(action='SUB')
            tool = bpy.context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=False)
            self.assertEqual(tool.idname, 'builtin.select_circle')
            self.assertEqual(tool.operator_properties('view3d.select_circle').mode, 'SUB')
            bpy.ops.kmtr.brush(action='ADD')
            self.assertEqual(tool.operator_properties('view3d.select_circle').mode, 'ADD')
            bpy.context.window_manager.kmtr_settings.brush_radius = 70
            self.assertEqual(tool.operator_properties('view3d.select_circle').radius, 70)
            bpy.ops.kmtr.brush(action='BOX')
            self.assertEqual(tool.idname, 'builtin.select_box')


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AddonTests)
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    if not outcome.wasSuccessful():
        sys.exit(1)
