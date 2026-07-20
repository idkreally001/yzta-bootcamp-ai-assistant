# Odoo AI Sorgu Asistanı

YZTA Bootcamp 2026 — Yapay Zeka (YZ) kategorisi ürün teslimi.

## Takım Bilgileri

**Takım İsmi:** Takım 146
**Takım Rolleri:** Bu ürün, ekip üyelerine ulaşılamaması nedeniyle (bkz. Akademi'nin
`#bootcamp-2026` kanalındaki 2026-07-05 tarihli duyuru — "ekip arkadaşlarınıza
ulaşamıyor olmanız" istisna koşulu) tek kişi tarafından geliştirilmiştir. Tüm Scrum
rolleri (Product Owner, Scrum Master, Developer) tarafımdan yürütülmüştür.

| İsim | Rol |
|---|---|
| Islam Pashazade | Product Owner / Scrum Master / Developer |

## Ürün İle İlgili Bilgiler

**Ürün İsmi:** Odoo AI Sorgu Asistanı

**Ürün Açıklaması:**
Odoo 19 üzerinde çalışan, kullanıcıların satış siparişleri, ürünler ve stok verileri
hakkında doğal dilde (Türkçe) soru sorabildiği bir AI asistanı. Sorular 4 adımlı bir
agent hattından geçer: niyet tespiti → sorgu planlama → Odoo ORM üzerinden güvenli veri
çekme → doğal dilde özetleme. Chat arayüzü, Odoo backend'inin sistray'ine (Discuss,
Activities gibi) eklenen bir ikon üzerinden erişilebilir.

**Hedef Kitle:**
Odoo kullanan KOBİ'lerdeki operasyon/satış ekipleri — teknik sorgu dili (filtre, rapor
oluşturma) bilmeden "bu ay en çok satan 5 ürün ne?" gibi sorularla anlık içgörü almak
isteyen kullanıcılar.

**Ürün Özellikleri:**
- Doğal dilde soru → otomatik model seçimi (satış siparişi / ürün / stok)
- Çok turlu konuşma hafızası — takip sorularını ("kimlerden?", "fiyatları?") önceki
  sorgunun bağlamında yanıtlar
- Güvenli, salt-okunur ORM erişimi — sabit model/alan allowlist, domain doğrulayıcı,
  hiçbir zaman ham SQL veya yazma işlemi yok
- Öneri soru çipleri ile hızlı başlangıç
- Pluggable LLM backend: Gemini (varsayılan) veya yerel LM Studio
- Gemini kota aşımına karşı otomatik model fallback (3.5 → 3.1 Flash Lite)

**Product Backlog:** Bu depo içinde tutulmaktadır — bkz. [Geliştirme Süreci](#geliştirme-süreci) bölümü.

## Kullanılan Teknolojiler

- **Platform:** Odoo 19.0 Community Edition (Docker)
- **Backend:** Python, Odoo ORM, Odoo web controllers (JSON-RPC)
- **Frontend:** OWL (Odoo Web Library) systray bileşeni + vanilla JS chat arayüzü
- **AI:** Google Gemini API (`gemini-3.5-flash-lite`, fallback `gemini-3.1-flash-lite`),
  serbest tier
- **Veritabanı:** PostgreSQL 16 (Odoo demo verisiyle)

## Mimari

```
Kullanıcı sorusu
    │
    ▼
[1] Niyet Tespiti (LLM) ──► hangi model? (sale.order / product.product / stock.quant)
    │
    ▼
[2] Sorgu Planlama (LLM) ──► Odoo domain filtresi + alan listesi + sıralama
    │   (takip sorularında: filter_changed=false ise önceki domain mekanik olarak
    │    yeniden kullanılır — LLM'e güvenilmez, kod seviyesinde garanti edilir)
    ▼
[3] Sorgu Yürütme (Odoo ORM) ──► search_read() — kullanıcının kendi erişim haklarıyla,
    │                             salt-okunur
    ▼
[4] Özetleme (LLM) ──► ham veriyi doğal dilde Türkçe yanıta çevirir
    │
    ▼
Kullanıcıya yanıt
```

Güvenlik sınırları:
- LLM asla ham SQL üretmez — yalnızca Odoo domain sözdizimi (`[[alan, operatör, değer]]`)
- Sorgulanabilir modeller ve alanlar sabit bir allowlist ile sınırlıdır
  (`services/agent.py` → `ALLOWED_MODELS`)
- Tüm veri erişimi `search_read` ile yapılır — create/write/unlink asla açığa çıkmaz
- Domain doğrulayıcı, beklenmeyen şekilde gelen bir domain'i sorgu çalıştırılmadan reddeder

## Geliştirme Süreci

Proje, ekip üyelerine ulaşılamaması nedeniyle tek gecelik (31 Temmuz – 1 Ağustos 2026)
yoğun bir geliştirme sürecinde sıfırdan inşa edilmiştir. Git geçmişi gerçek zaman
damgalarını yansıtır; aşağıda üretim sürecindeki gerçek aşamalar ve karşılaşılan
sorunlar özetlenmiştir.

### Aşama 1 — Ortam Kurulumu
Odoo 19 için mevcut yerel geliştirme aracı ([`odoom`](https://github.com/idkreally001/odoom) —
kendi yazdığım Docker Compose tabanlı Odoo ortam yöneticisi) varsayılan olarak Enterprise
kaynak ağacını mount ediyordu; bootcamp kuralları serbest/ücretsiz araç kullanımını
şart koştuğu için bu proje **Community Edition** ile, elle yazılmış bir
`docker-compose.yml` üzerinden sıfırdan kuruldu (Enterprise mount'u olmadan).
Demo veri, Odoo'nun kendi `sale_management` ve `stock` modüllerinin demo verisiyle
yüklendi.

### Aşama 2 — Agent Çekirdeği
4 adımlı agent hattı ve pluggable LLM client arayüzü (Gemini / LM Studio) yazıldı.
İlk Gemini API denemesinde ücretsiz kota `limit: 0` hatası verdi — araştırma sonucu
API'nin `:generateContent` uç noktasından yeni `/v1beta/interactions` uç noktasına
geçtiği ve model isminin `gemini-3.6-flash` olarak güncellendiği görüldü; istemci buna
göre yeniden yazıldı.

### Aşama 3 — Arayüz ve Sistray
Sohbet arayüzü ve Odoo'nun üst çubuğuna (Discuss, Activities yanına) eklenen sistray
ikonu geliştirildi.

### Aşama 4 — Hata Ayıklama (çok turlu tutarlılık sorunları)
Manuel test sırasında takip sorularının ("kimlerden?", "fiyatlar?") tutarsız/çelişkili
cevaplar ürettiği tespit edildi (örn. bir turda "24 kayıt", sonrakinde "20 kayıt").
Kök nedenler:
1. Planlama adımı, takip sorularında domain'i LLM'e "önceki turu temel al" talimatıyla
   yeniden ürettiriyordu — model bazen alakasız bir filtre uyduruyordu.
2. Özetleme adımına gönderilen ham veri `records[:20]` ile kesiliyordu, ancak modele
   gerçek toplam sayı (20'den büyük olabilen) ayrıca söyleniyordu — model gördüğü
   satır sayısını anlatıyordu.
3. Niyet tespiti adımı, belirsiz takip sorularında ("Fiyatlar?") aynı modelde kalma
   konusunda yeterince güçlü bir varsayılana sahip değildi.

Çözüm: planlayıcıya açık bir `filter_changed` alanı eklendi; bu `false` olduğunda
önceki turun domain/alan/limit/sıralama bilgisi **koddan mekanik olarak** yeniden
kullanılıyor (LLM'in yeniden üretmesine güvenilmiyor). Özetleme payload'ı `MAX_ROWS`
ile sınırlandırılarak görünen satır sayısı her zaman bildirilen sayıyla eşleşiyor.
Niyet promptuna "belirsiz takip sorularında varsayılan olarak aynı modeli seç" kuralı
eklendi. 5 turluk düşmanca (adversarial) bir konuşmayla doğrulandı.

### Aşama 5 — Kota Dayanıklılığı
Demo/değerlendirme sırasında olası rate-limit riskini azaltmak için Gemini istemcisine
otomatik model fallback eklendi (`gemini-3.5-flash-lite` → 429 alınırsa
`gemini-3.1-flash-lite`) — her ikisi de ayrı kota havuzuna sahip ücretsiz katmanlar.

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
# http://localhost:8077/odoo  -> giriş yap -> üst çubukta sihirli değnek ikonu
# veya doğrudan http://localhost:8077/odoo-ai
```

## Lisans

LGPL-3
