# Development & verification / Geliştirme ve doğrulama

## Source and packaging

The single-file module is [kolay_malzeme_tr.py](../kolay_malzeme_tr.py). FacePilot is the repository brand; the Python module, `kmtr.*` operator identifiers, Turkish labels and add-on name remain stable. Documentation and branding do not change the v1.11.0 implementation.

The installable archive contains **one root entry**, `kolay_malzeme_tr.py`. Rebuild it from the repository root in PowerShell:

```powershell
Compress-Archive -LiteralPath .\kolay_malzeme_tr.py -DestinationPath .\dist\FacePilot-1.11.0.zip -Force
```

Eklenti tek Python dosyasıdır. Repo markası FacePilot olsa da modül, operatör adları ve TR/EN arayüz korunur. ZIP'in kökünde yalnız `kolay_malzeme_tr.py` bulunur.

## Run real Blender fixtures

From the repository root, use your installed Blender executable:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python .\tests\test_addon.py
```

On systems where Blender is on PATH:

```sh
blender --background --factory-startup --python-exit-code 1 --python tests/test_addon.py
```

**Keep `--factory-startup`.** The fixtures delete objects from their disposable test scene. They must not run inside an artist's working file. No source character or external assets are required; fixtures create meshes and materials in memory.

**`--factory-startup` seçeneğini koru.** Testler kendi geçici sahnesindeki objeleri siler. Üzerinde çalıştığın gerçek dosyanın içinde çalıştırma. Karakter modeline veya harici dosyaya ihtiyaç yoktur.

## Recorded result

Validated with Blender **5.2.3 LTS**, add-on **1.11.0**:

```text
Ran 71 tests
OK (skipped=1)
70 passed; 1 native GUI brush test skipped in background mode
```

This suite checks material selection/assignment and undo, whole-material removal (hidden faces, duplicate/OBJECT-linked slots, target remapping, shared-mesh rejection and full undo/redo), selected-source transfers, smart-region boundaries, runtime color invariance, red marking/transfer/toggle/lifecycle, hidden state/isolation undo, fresh boundary scans, conservative hole eligibility, existing-surface overlap rejection, current neighbor material checks, patch winding and existing UV preservation, and selected-vertex welding/undo.

The GUI-only test checks native selection-tool configuration. Background success does not validate every GPU, driver, Blender version, modifier combination or interactive gesture. The documentation images exercise real GPU overlays in a separate GUI session; they are visual examples rather than exhaustive automated interaction tests.

Testler seçim/atama, geri alma, akıllı bölge sınırları, önizlemenin gerçek verileri koruması, kırmızı işaretler, gizleme yedeği, tarama, onarım ölçütleri, yüzey çakışması, güncel komşu malzemeleri, yüz yönü, eski UV'ler ve nokta birleştirmeyi kontrol eder. Arka plan sonucu bütün GPU/sürüm/modifier kombinasyonlarının doğrulandığı anlamına gelmez.

## Architecture notes

| Area | Implementation |
|---|---|
| UI / language | Stable-ID native collapsible groups in N → FacePilot; add-on-only TR/EN catalog and cached enum callbacks; AddonPreferences sync |
| Mesh editing | BMesh, one edited mesh at a time |
| Material removal | Native Object Mode slot removal and explicit full-state undo snapshots; returns Edit Mode after removal, Object Mode after undo/redo |
| Preview colors / masks / red marks | Runtime maps and GPU draw handlers; not material or color attributes |
| Selection memory | Mesh identity + topology guard |
| Isolation backup | Temporary integer BMesh layers to follow Blender undo states |
| Boundary scan | Connected groups of edges with one linked face; hidden topology included |
| Polygon repair preview | Copy-only hole fill + triangulation, exact triangle/UV proposal, GPU violet overlay, explicit Apply/Cancel and source-state guard |
| Strict small-hole plan | Read-only eligibility checks, current neighbor materials, world-space dimensions, surface-intersection rejection |
| Patch creation | `bmesh.ops.holes_fill`, adjacent material and winding, existing-face UV preservation |
| Weld | Selected visible vertices, small threshold, connected-only default |

When changing topology, invalidate stale face-index-based runtime state and refresh the scan. Avoid adding material/UV mutations to preview code. New patch UVs still require inspection; do not describe automatic filling as automatic UV layout or retopology.
