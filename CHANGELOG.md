# Changelog / Sürüm geçmişi

## 1.7.0 · Preview-first polygon repair

- Translucent violet repair proposals for 3–256-edge closed loops, including concave/curved boundaries.
- Separate active-region/all-scan preview, size limit, opacity, explicit Apply and Cancel.
- Apply creates exactly the previewed triangles and patch UV data; existing faces are kept intact.
- Reject stale coordinates/topology/visibility/materials/UVs/transforms, surface collisions and reused manifold diagonals.
- 53 Blender fixture tests: 52 pass, 1 GUI-only skip. Updated EN/TR guides and actual character screenshots.

3–256 kenarlı kapalı sınırlar için saydam mor yama önerisi; tek açıklık/tüm tarama, boyut sınırı ve saydamlık ayarı. Yalnız Uygula gerçek üçgen ekler; İptal geometriyi değiştirmez. Eski sıkı küçük delik modu ayrı korunur. Değişmiş model ve yüzey/köşegen çakışma kontrolleri eklendi.

## 1.6.0 · FacePilot repository edition

- One-click distinct random viewport colors for every unique material on the active mesh.
- Conservative small-hole eligibility check and explicit all/active-region repair.
- Selected-visible-vertex Merge by Distance with connected-only default.
- Current neighbor-material validation and geometric existing-surface overlap rejection.
- FacePilot branding, full English/Turkish guides and real character workflow screenshots.

Tüm malzemeleri tek tıkla farklı geçici renklendirme, uygun küçük delik kontrolü/onarımı ve seçili nokta birleştirme. Güncel komşu malzeme ve yüzey çakışması kontrolleri. FacePilot markası, iki dilde tam rehber ve gerçek kullanım görselleri.

## 1.5.0

- Read-only open-boundary list, material filtering, cyan overlay and focus/select.
- Gizli topolojiyi de hesaba katan açıklık listesi, malzeme filtresi ve bölgeye yaklaşma.

## 1.4.0

- Independent material-specific GPU preview colors with per-material/all clear controls.
- Gerçek malzemeyi değiştirmeden malzeme başına ayrı önizleme renkleri.

## 1.3.0

- Transparent red outlines, ordinary selection marking/unmarking, Ctrl toggle/erase and Clear.
- Saydam kırmızı çerçeveler, normal seçimle işaretleme, Ctrl ile aç/kapat/sil ve Clear.

## Earlier workflow foundation

- Turkish material selection, native add/subtract brushes, grow/shrink/invert, selection memory.
- Material/angle/seam/sharp-aware smart region selection.
- Selected-source reassignment to first or chosen target material.
- Four temporary black previews; hide/restore isolation; material assignment/creation.
- Türkçe seçim ve ince düzeltme, akıllı bölge seçimi, hedef malzemeye taşıma, siyah önizleme, izolasyon ve gerçek atama araçları.
