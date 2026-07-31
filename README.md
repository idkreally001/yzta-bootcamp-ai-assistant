# Odoo AI Sorgu Asistanı

YZTA Bootcamp 2026 — Yapay Zeka (YZ) kategorisi ürün teslimi.

## Takım Bilgileri

**Takım İsmi:** Takım 146
**Takım Rolleri:** Bu ürün tek kişi tarafından geliştirilmiştir. Tüm Scrum rolleri
(Product Owner, Scrum Master, Developer) tarafımdan yürütülmüştür.

| İsim | Rol |
|---|---|
| Islam Pashazade | Product Owner / Scrum Master / Developer |

## Ürün İle İlgili Bilgiler

**Ürün İsmi:** Odoo AI Sorgu Asistanı

**Ürün Açıklaması:**
Odoo 19 üzerinde çalışan, kullanıcıların hem canlı işletme verileri (satış siparişleri,
ürünler, stok) hem de Odoo kullanım prosedürleri hakkında doğal dilde (Türkçe) soru
sorabildiği bir AI agent. Her soru, hangi araçların kullanılacağına LLM'in kendisinin
karar verdiği agentic bir yönlendirme adımından geçer — sabit bir adım dizisi değil,
gerçek araç seçimi. Chat arayüzü hem Odoo backend'inin sistray'ine (Discuss, Activities
yanına) eklenen bir açılır panel üzerinden hem de bağımsız bir tam sayfa üzerinden
erişilebilir; ikisi de aynı sohbet geçmişini paylaşır.

**Hedef Kitle:**
Odoo kullanan KOBİ'lerdeki operasyon/satış ekipleri — teknik sorgu dili (filtre, rapor
oluşturma) bilmeden "bu ay en çok satan 5 ürün ne?" veya "bir siparişte iade nasıl
yapılır?" gibi sorularla anlık içgörü ve prosedür bilgisi almak isteyen kullanıcılar.

**Ürün Özellikleri:**
- **Agentic araç yönlendirme** — LLM her soru için `query_data` (canlı ORM sorgusu) ve/veya
  `search_docs` (RAG) araçlarından hangisinin/hangilerinin gerekli olduğuna karar verir;
  prosedür sorusu ORM sorgusunu, veri sorusu embedding aramasını hiç tetiklemez
- **RAG bilgi tabanı** — Odoo kullanım SSS'i (6 doküman), Gemini embedding modeliyle
  vektörleştirilip kosinüs benzerliğiyle aranıyor; düşük alaka skorlu eşleşmeler
  (örn. konuyla alakasız ama anahtar kelime içeren sorular) reddediliyor
- **Çok turlu, kalıcı konuşma hafızası** — `odoo.ai.conversation` modelinde saklanır,
  sunucu yeniden başlasa veya sayfa yenilense bile korunur; takip sorularını
  ("kimlerden?", "fiyatları?") önceki sorgunun bağlamında mekanik olarak yanıtlar
  (LLM'in bağlamı yeniden üretmesine güvenilmez, kod seviyesinde garanti edilir)
- **Akan (streaming) yanıtlar** — SSE üzerinden, yanıt üretilirken anlık görüntülenir
- **Deterministik grafik** — sayısal/karşılaştırmalı sonuçlar için LLM'e değil doğrudan
  sorgu sonucuna dayanan bar grafik (yanlış/uydurma grafik verisi riski yok)
- **Güvenli, salt-okunur ORM erişimi** — sabit model/alan allowlist, domain doğrulayıcı,
  hiçbir zaman ham SQL veya yazma işlemi yok
- **Sistray paneli + tam sayfa** — panelde hızlı erişim, "tam sayfada aç" ikonuyla
  standalone sayfaya geçiş, "sohbeti temizle" ile geçmişi sıfırlama
- **Pluggable LLM backend** — Gemini (varsayılan) veya yerel LM Studio
- **Kota dayanıklılığı** — Gemini modelleri arası otomatik fallback (3.5 → 3.1 Flash Lite),
  ayrı kota havuzları sayesinde etkin limiti ikiye katlıyor

**Product Backlog:** Bu depo içinde tutulmaktadır — bkz. [Geliştirme Süreci](#geliştirme-süreci) bölümü.

## Kullanılan Teknolojiler

- **Platform:** Odoo 19.0 Community Edition (Docker)
- **Backend:** Python, Odoo ORM, Odoo web controllers (JSON-RPC + SSE)
- **Frontend:** OWL (Odoo Web Library) systray bileşeni + vanilla JS standalone sayfa,
  ikisi de aynı SSE uç noktasını tüketiyor
- **AI:** Google Gemini API — sohbet için `gemini-3.5-flash-lite` (fallback
  `gemini-3.1-flash-lite`), embedding için `gemini-embedding-001`; hepsi serbest tier
- **Veritabanı:** PostgreSQL 16 (Odoo demo verisiyle)

## Mimari

```
Kullanıcı sorusu
    │
    ▼
[1] Araç Yönlendirme (LLM) ──► query_data mi, search_docs mi, ikisi de mi, yoksa
    │                          kapsam dışı mı? (son turlarla bağlam sürekliliği)
    │
    ├── query_data seçildiyse ──────────────────────────────┐
    │   [2a] Sorgu Planlama (LLM) ──► Odoo domain filtresi   │
    │        (takip sorularında: filter_changed=false ise    │
    │         önceki domain koddan mekanik olarak yeniden    │
    │         kullanılır — LLM'e güvenilmez)                 │
    │   [3a] Sorgu Yürütme (ORM) ──► search_read(), salt-okunur│
    │                                                          │
    ├── search_docs seçildiyse ─────────────────────────────┐│
    │   [2b] Embedding + kosinüs benzerliği ──► en alakalı   ││
    │        SSS dokümanları (min_score altındakiler elenir) ││
    │                                                          ││
    ▼                                                          ▼
[4] Özetleme (LLM, akan) ──► canlı veri ve/veya SSS içeriğini doğal
    │                        dilde Türkçe yanıta çevirir
    ▼
Kullanıcıya akan (streaming) yanıt + (varsa) deterministik grafik
```

Güvenlik sınırları:
- LLM asla ham SQL üretmez — yalnızca Odoo domain sözdizimi (`[[alan, operatör, değer]]`)
- Sorgulanabilir modeller ve alanlar sabit bir allowlist ile sınırlıdır
  (`services/agent.py` → `ALLOWED_MODELS`)
- Tüm veri erişimi `search_read` ile yapılır — create/write/unlink asla açığa çıkmaz
- Domain doğrulayıcı, beklenmeyen şekilde gelen bir domain'i sorgu çalıştırılmadan reddeder
- Sohbet geçmişi kullanıcı başına `ir.rule` ile izole edilir — bir kullanıcı başka bir
  kullanıcının konuşmasını göremez

## Geliştirme Süreci

### Aşama 1 — Ortam Kurulumu
Mevcut yerel geliştirme aracı ([`odoom`](https://github.com/idkreally001/odoom) — kendi
yazdığım Docker Compose tabanlı Odoo ortam yöneticisi) varsayılan olarak Enterprise kaynak
ağacını mount ediyordu; bootcamp kuralları serbest/ücretsiz araç kullanımını şart koştuğu
için proje **Community Edition** ile, elle yazılmış bir `docker-compose.yml` üzerinden
sıfırdan kuruldu (Enterprise mount'u olmadan, doğrulandı). Demo veri, Odoo'nun kendi
`sale_management` ve `stock` modüllerinin demo verisiyle yüklendi.

### Aşama 2 — Agent Çekirdeği
İlk sürüm: sabit 4 adımlı bir hat (niyet tespiti → sorgu planlama → yürütme → özetleme)
ve pluggable LLM client arayüzü (Gemini / LM Studio). İlk Gemini API denemesinde ücretsiz
kota `limit: 0` hatası verdi — araştırma sonucu API'nin `:generateContent` uç noktasından
yeni `/v1beta/interactions` uç noktasına geçtiği görüldü; istemci buna göre yeniden yazıldı.

### Aşama 3 — Arayüz ve Sistray (v1: yeni sekme)
Sohbet arayüzü ve sistray ikonu geliştirildi; ikon tıklandığında `/odoo-ai` yeni sekmede
açılıyordu.

### Aşama 4 — Çok Turlu Tutarlılık Hataları
Manuel test sırasında takip sorularının ("kimlerden?", "fiyatlar?") tutarsız/çelişkili
cevaplar ürettiği tespit edildi (örn. bir turda "24 kayıt", sonrakinde "20 kayıt"). Kök
nedenler: (1) planlama adımı takip sorularında domain'i LLM'e serbestçe yeniden
ürettiriyordu, bazen alakasız bir filtre uyduruyordu; (2) özetleme adımına gönderilen ham
veri `records[:20]` ile kesiliyordu ama modele gerçek toplam sayı ayrıca söyleniyordu —
model gördüğü satır sayısını anlatıyordu; (3) niyet tespiti belirsiz takip sorularında
aynı modelde kalma konusunda yeterince güçlü bir varsayılana sahip değildi. Çözüm: plana
açık bir `filter_changed` alanı eklendi, `false` olduğunda önceki turun domain/alan/
limit/sıralaması **koddan mekanik olarak** yeniden kullanılıyor (LLM'e güvenilmiyor);
özetleme payload'ı `MAX_ROWS` ile sınırlandırılıp görünen satır sayısı bildirilen sayıyla
her zaman eşleştirildi. 5 turluk adversarial bir konuşmayla doğrulandı.

### Aşama 5 — RAG + Agentic Araç Yönlendirme
Kapsam genişletildi: Odoo kullanım SSS'i (6 doküman) Gemini embedding modeliyle
vektörleştirilip kosinüs benzerliğiyle aranan bir RAG katmanı eklendi. Sabit "niyet
tespiti" adımı, LLM'in her soru için `query_data`/`search_docs` araçlarından hangisini
(veya ikisini) kullanacağına karar verdiği bir yönlendiriciye dönüştürüldü — prosedür
sorusu ORM sorgusunu, veri sorusu embedding aramasını hiç tetiklemiyor.

### Aşama 6 — Kalıcı Konuşma Modeli
Bellek içi (`_SESSION_HISTORY` dict) sohbet geçmişi, `odoo.ai.conversation` /
`odoo.ai.conversation.line` modellerine taşındı; kullanıcı başına `ir.rule` ile izole
edildi. Sunucu yeniden başlatıldığında bağlamın hâlâ korunduğu doğrulandı.

### Aşama 7 — Akan Yanıtlar (SSE)
Gemini'nin `stream: true` uç noktası entegre edildi. Karşılaşılan iki hata: (1) Odoo'nun
istek-scope'lu veritabanı cursor'ı, streaming HTTP yanıtının generator'ı WSGI katmanı
tarafından tüketilmeden önce kapanıyordu ("Cursor already closed") — çözüm: tüm ORM/RAG
işini generator başlamadan önce senkron olarak bitirip, generator içinde yalnızca saf
ağ/LLM akışı çalıştırmak, son veritabanı yazımı için ise `registry.cursor()` ile taze bir
cursor açmak. (2) `requests`'in `decode_unicode=True`'sı SSE akışının kodlamasını yanlış
tahmin edip Türkçe karakterleri bozuyordu — çözüm: baytları elle UTF-8 olarak çözmek.

### Aşama 8 — Gömülü Panel + Grafik + Genişletme/Temizleme
Sistray tıklaması yeni-sekme yerine gerçek bir OWL `Dropdown`-tabanlı panele dönüştürüldü
(Discuss'ın kendi sistray desenini takip ederek). İlk denemede `Dropdown`'ın slot API'si
yanlış kullanıldı (toggler ve content ters), panel bozuk bir metin linki + boş kutu olarak
render oldu; canlı tarayıcı testiyle bulunup düzeltildi. Aynı oturumda ikinci gerçek hata
bulundu: `chat.js`, her frontend sayfasında (login dahil) yüklenen `web.assets_frontend`
paketinde çalışıyordu ve `/odoo-ai`'a özgü DOM elemanlarını koşulsuz arıyordu — login
sayfasında bu elemanlar `null` olduğundan `addEventListener` patlıyor, bu da Owl modül
yükleyicisinin tamamını çöktürüp **login sayfasını tamamen boş** bırakıyordu (birkaç
"Missing template" hatasıyla birlikte). Erken `return` koruması eklenip canlı doğrulandı.
Ardından deterministik (LLM'siz) bar grafik, "tam sayfada aç" ikonu ve "sohbeti temizle"
butonu eklendi.

### Aşama 9 — Ek Adversarial Bulgular
Manuel testte "pasta yapmam lazım bir satış siparişi için hemen" gibi konu dışı ama
anahtar kelime içeren bir soru, `search_docs`'a yanlışlıkla yönlendirilip yanlış bağlamda
kendinden emin bir yanıt üretti. Ölçülen embedding skorları: gerçek eşleşmeler ~0.90,
saf gürültü ~0.50, bu yanlış-pozitif ~0.71 — RAG eşik değeri 0.5'ten 0.72'ye çıkarıldı ve
yönlendirme promptuna "anahtar kelime değil gerçek niyeti değerlendir" talimatı eklendi.

Ayrıca: standalone sayfanın `chat.css`/`chat.js`'i Odoo'nun varsayılan uzun `max-age`
cache header'ıyla ham statik dosya olarak servis ediliyordu ve URL'lerde cache-busting
yoktu — normal bir sayfa yenileme (sert yenileme değil) herhangi bir kod değişikliğinden
sonra eski kopyayı servis etmeye devam ediyordu (bozuk layout + ölü "temizle" butonu
olarak ortaya çıktı). Çözüm: modülün `write_date`'ini `?v=` query param'ı olarak asset
URL'lerine ekleyip her modül yükseltmesinde otomatik geçersiz kılmak.

### Aşama 10 — Kota Dayanıklılığı
Demo/değerlendirme sırasında rate-limit riskini azaltmak için Gemini istemcisine otomatik
model fallback eklendi (`gemini-3.5-flash-lite` → 429 alınırsa `gemini-3.1-flash-lite`).

## Kurulum ve Çalıştırma

```bash
# 1. Ortam değişkenlerini ayarla
cp .env.example .env
# .env içine GEMINI_API_KEY doldur (ücretsiz: https://aistudio.google.com/apikey)

# 2. Odoo + PostgreSQL'i başlat
docker compose up -d

# 3. Demo veritabanı oluştur (bkz. Odoo web arayüzü, http://localhost:8077)
#    db adı: bootcamp_ai, demo verisi dahil

# 4. Modülü yükle
docker exec odoo-web-bootcamp-ai odoo -d bootcamp_ai -i odoo_ai_query --stop-after-init

# 5. Kullan
# http://localhost:8077/odoo  -> giriş yap -> üst çubukta sihirli değnek ikonu (panel)
# veya doğrudan http://localhost:8077/odoo-ai (tam sayfa)
```

## Lisans

LGPL-3
