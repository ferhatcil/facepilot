# Screenshot notes / Ekran görüntüsü notları

The documentation uses real Blender screenshots of a temporary mesh copy exported from the user's active character. Screenshots were captured in a **separate Blender 5.2.3 GUI process** with a neutral Solid view and the respective v1.6/v1.7 source. The material-color examples use deterministic palette seed 28. The original scene was neither opened in that process nor saved or repaired.

Belgelerde, kullanıcının etkin karakterinden alınan geçici mesh kopyasının gerçek Blender ekran görüntüleri kullanılır. Çekimler **ayrı Blender 5.2.3 GUI oturumunda**, nötr Solid görünüm ve ilgili v1.6/v1.7 kaynakla yapıldı. Malzeme rengi örneklerinde palet tohumu 28 kullanıldı. Asıl sahne o oturumda açılmadı, kaydedilmedi veya onarılmadı.

| Image | Demonstration / Gösterim |
|---|---|
| `01-material-colors.png` | Sixteen unique runtime material previews / 16 ayrı geçici malzeme rengi |
| `02-belt-selection.png` | Existing `M_Kemer` material group selected / Mevcut kemer malzemesinin seçimi |
| `03-black-preview.png` | Other materials darkened / Diğer malzemelerin karartılması |
| `04-red-corrections.png` | Ten visible belt faces marked; ordinary selection then cleared to expose outlines / 10 yüz işaretli, çerçeveyi göstermek için normal seçim sonradan kaldırıldı |
| `05-transfer-result.png` | Those marks transferred to first slot, with preview colors to show groups / İşaretlilerin ilk yuvaya aktarılması ve grupların önizleme renkleri |
| `06-isolate-belt.png` | Non-belt faces hidden / Kemer dışındaki yüzler gizli |
| `07-single-material-color.png` | Turquoise preview applied only to belt / Yalnız kemere turkuaz önizleme |
| `08-open-boundaries.png` | Actual open-boundary cyan overlay; 146 regions / Gerçek açık sınırların turkuaz çizgileri, 146 bölge |
| `09-controlled-hole-before.png` | One triangle deliberately deleted from buckle on copy / Kopyadaki tokadan bir üçgen bilerek silindi |
| `10-controlled-hole-after.png` | One eligible face filled using active-region repair, limit 0.04 / Etkin bölge onarımıyla 0,04 sınırında bir yüz eklendi |
| `12-addon-panel.png` | Actual Turkish selection, preview and correction controls / Gerçek Türkçe seçim, önizleme ve kırmızı işaret araçları |
| `15-hole-tools-panel.png` | Boundary, repair and merge controls / Tarama, onarım ve birleştirme araçları |
| `16-repair-preview-panel.png` | v1.7: 61 patches / 181 triangles proposed without editing / Geometri değişmeden 61 yama ve 181 üçgen önerisi |
| `17-polygon-opening-before.png` | Eight-edge opening deliberately made by removing three shirt quads / Kopyadaki üç atlet dörtgeni silinerek oluşturulan sekiz kenarlı açıklık |
| `18-polygon-opening-preview.png` | Six violet proposed triangles; still 27,696 faces / Altı mor üçgen önerisi; hâlâ 27.696 gerçek yüz |
| `19-polygon-opening-applied.png` | Explicit Apply on disposable copy: 27,702 faces / Yalnız geçici kopyada Uygula: 27.702 yüz |

For cleaner screenshots, floor/axis/relationship lines and seam display were disabled and the camera was adjusted in the disposable session. The red-mark fill remained 0. Material assignments temporarily changed for the transfer example were restored before later examples. The sidebar was scrolled and unrelated panels collapsed/omitted when isolating a tool group; the shipped controls and their draw code were unchanged.

Daha net görüntü için geçici oturumda zemin/eksen/ilişki çizgileri ve dikiş gösterimi kapatıldı, kamera ayarlandı. Kırmızı dolgu 0 kaldı. Taşıma örneğindeki atamalar sonraki örneklerden önce geri yüklendi. Araç gruplarını göstermek için panel kaydırıldı ve ilgisiz paneller daraltıldı/gizlendi; dağıtılan araçların çizim kodu değiştirilmedi.

The v1.6 controlled repair sequence had **27,698 faces before** and **27,699 after**, with one successful patch. Its boundary region count was **147 before / 146 after**. This illustrates an intentional test defect, not proof that automatic filling fixed the original character's existing openings. Under the strict 0.02 limit and conservative criteria, the original scan yielded no eligible automatic patch. The v1.7 images separately show a controlled eight-edge shirt opening, its six candidate triangles and explicit application only on the copy. The detail preview opacity is 0.55 for visibility; the default is 0.35. The live original model was left with a preview only.

v1.6 kontrollü onarımında yüz sayısı **27.698'den 27.699'a**, açıklık sayısı **147'den 146'ya** değişti. Bu, bilerek oluşturulmuş bir test deliğidir; orijinal karakterdeki açıklıkların otomatik düzeltildiği iddiası değildir. Sıkı modun 0,02 sınırında uygun otomatik yama çıkmadı. Ayrı v1.7 görselleri kontrollü sekiz kenarlı atlet açıklığını, altı üçgen önerisini ve yalnız kopyadaki uygulamayı gösterir. Yakın çekimde görünürlük için yoğunluk 0,55 kullanıldı; varsayılan 0,35'tir. Canlı asıl modelde yalnız önizleme bırakıldı.

The source character `.blend`, source mesh snapshot and textures are not included. The FacePilot brand banner was generated for this project; it is separate from the authentic Blender screenshots.

Kaynak karakter `.blend` dosyası, geçici mesh anlık kopyası ve dokular repoya dahil değildir. FacePilot banner'ı bu proje için üretilmiş marka görselidir; gerçek Blender ekran görüntülerinden ayrıdır.
