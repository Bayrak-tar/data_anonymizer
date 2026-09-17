# Data Anonymizer

Türkçe metinlerdeki kişisel ve hassas bilgileri anonimleştiren FastAPI uygulaması.

Uygulama; regex kuralları ve Türkçe Named Entity Recognition (NER) modeli kullanarak e-posta, telefon, IP adresi, TC kimlik numarası, tarih, isim, kurum ve benzeri bilgileri placeholder değerlerle değiştirir.

## Gereksinimler

- Python 3.10 veya üzeri
- İnternet bağlantısı (NER modeli ilk çalıştırmada indirilebilir)
- `requirements.txt` içindeki Python paketleri

## Kurulum

Proje klasöründe bir PowerShell terminali açın:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

PowerShell sanal ortamı etkinleştirmeyi engellerse:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Uygulamayı Çalıştırma

```powershell
python api.py
```

Model yüklenip şu mesaj göründüğünde uygulama hazırdır:

```text
Application startup complete.
```

Tarayıcıdan web arayüzünü açın:

- Web arayüzü: http://localhost:8001/
- Swagger API dokümantasyonu: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc
- Sağlık kontrolü: http://localhost:8001/health

`index.html` dosyasını doğrudan çift tıklayarak açmayın. Arayüz, anonimleştirme API'sine bağlanabilmek için FastAPI sunucusu üzerinden açılmalıdır.

## Kullanım

1. Web arayüzünü açın.
2. Anonimleştirilecek metni sol panele yazın.
3. `Anonimleştir` butonuna basın. Metin, boşlukları ve satır sonları değiştirilmeden gönderilir; varsayılan katı maskeleme uygulanır.
4. Anonimleştirilmiş metni sağ panelden kopyalayın veya indirin.

Alt bölümde her maskelenen alan ayrı bir kartta gösterilir: veri türü, orijinal değer ve yerine yazılan maske. Kartlar ekran genişliğine göre yan yana dizilir. Orijinal değerler, girdi metninden tarayıcıda alınır; kopyalama ve indirme yalnızca anonimleştirilmiş sonucu içerir.

Örnek giriş:

```text
Bayram BAYRAKTAR ile deneme@example.com adresinden iletişime geçebilirsiniz.
```

Örnek çıktı:

```text
[NAME_1] ile [EMAIL_1] adresinden iletişime geçebilirsiniz.
```

## Hangi bilgiler maskelenir?

Web arayüzü varsayılan **katı maskeleme** profilini kullanır. Aşağıdaki türlerden tespit edilen alanlar `[TÜR_1]`, `[TÜR_2]` gibi yer tutucularla değiştirilir. Örnekler gösterim amaçlıdır; isim, konum ve kurum tespitleri metnin bağlamına ve modelin güven puanına bağlıdır.

### Kişisel bilgiler ve iletişim

| Veri türü | Örnek girdi | Maske örneği |
| --- | --- | --- |
| Kişi adı / ad-soyad | `Ali`, `Ece`, `Ahmet Yılmaz` | `[NAME_1]` |
| Konum | `Ankara`, `İstanbul` | `[LOCATION_1]` |
| Kurum / kuruluş adı | Modelin kurum olarak tanıdığı adlar | `[ORGANIZATION_1]` |
| E-posta adresi | `deneme@example.com` | `[EMAIL_1]` |
| Türkiye telefon numarası | `0532 123 45 67`, `+90 (532) 123 45 67` | `[PHONE_1]` |
| Adres | `Atatürk Mah. Deneme Sok. No: 12` | `[ADDRESS_1]` |
| Araç plakası | `34 ABC 123` | `[PLATE_1]` |

Adres kuralı `Mah.`, `Cad.`, `Sok.`, `Apt.`, `Bul.`, `Cd.` veya `Sk.` kısaltmalarını içeren bir ifadeden satır sonuna kadar eşleşebilir. Bu nedenle aynı satırda adresten sonra gelen açıklamalar da maskelenebilir.

### Kimlik, finans ve kayıt numaraları

| Veri türü | Örnek girdi | Maske örneği |
| --- | --- | --- |
| TC kimlik numarası | `10000000146` | `[TC_1]` |
| Türkiye IBAN numarası | `TR33 0006 1005 1978 6457 8413 26` | `[IBAN_1]` |
| Kart numarası | `4111 1111 1111 1111`, `4111111111111111` | `[CREDIT_CARD_1]` |
| Kartın son hanelerini belirten ifade | `sonu 1234 ile biten` | `[CARD_END_1]` |
| Müşteri numarası | `Müşteri Numaram: 987654`, `Müşteri No: 987654` | `Müşteri Numaram: [CUSTOMER_ID_1]` |
| Sicil numarası | `123456 sicil` | `[REGISTRY_NO_1] sicil` |
| Sipariş numarası | `#AB-123456` | `[ORDER_NO_1]` |
| Mesaj numarası | `Message ID: ABC123XYZ` | `Message ID: [MESSAGE_ID_1]` |

TC kimlik numaraları 11 haneli ve ilk hanesi sıfır olmayan değerlerdir. IBAN kuralı `TR` ile başlayan numaraları, kart kuralı ise boşluk/tire içerebilen 13–19 haneli dizileri kapsar. Katı profilde bu biçimlere uyan şüpheli numaralar, kontrol basamağı doğrulaması başarısız olsa da maskelenir. Müşteri, sicil ve mesaj numaraları tabloda gösterilen bağlam/biçimlerle aranır; her rastgele numara bu türlerden biri olarak tanınmaz.

### Teknik bilgiler, tarih ve saat

| Veri türü | Örnek girdi | Maske örneği |
| --- | --- | --- |
| Web bağlantısı | `https://example.com/ticket?id=98765` | `[URL_1]` |
| Hostname / alt alan adı | `app01.internal.example.com` | `[HOSTNAME_1]` |
| IPv4 adresi | `192.168.1.25` | `[IP_ADDRESS_1]` |
| Sunucu adı | `APPDB01` | `[SERVER_1]` |
| Belirli cihaz adı biçimleri | `abc def ghi12` | `[DEVICE_1]` |
| Tanımlı markalar | `VMware`, `Veeam`, `IBM`, `Dell EMC` | `[BRAND_1]` |
| Sayısal tarih | `12.03.2025`, `12/03/2025`, `12-03-2025` | `[DATE_1]` |
| İngilizce ay kısaltmalı tarih | `Mar 12, 2025` | `[DATE_1]` |
| AM/PM içeren saat | `10:30 AM`, `10:30:45 PM` | `[TIME_1]` |

Marka listesi: VxRail, VMware, SolarWinds, Cohesity, Veeam, Huawei/Huawei Cloud, Dell/Dell EMC ve IBM. Marka, cihaz, sunucu ve mesaj numarası regex kuralları büyük/küçük harfe duyarlıdır. Sunucu kuralı en az altı karakterlik, büyük harfle başlayan, büyük harf ve rakam içeren adları arar. Cihaz kuralı genel bir cihaz tanıyıcısı değildir; örnekteki gibi üç küçük harf grubundan oluşan ve rakamla biten biçimleri arar.

Hostname kuralı en az üç noktayla ayrılmış bölümden oluşan adları kapsar. URL kuralı `http://` veya `https://` ile başlayan bağlantıları arar. IPv6, yalnızca `14:30` şeklindeki saatler ve `12 Mart 2025` gibi Türkçe ay adı içeren tarihler için özel regex kuralı yoktur. Tarih/saat kuralları biçim eşleştirir; takvim geçerliliği denetlemez.

### Özel kayıt biçimi ve ek maskeler

Katı profilde aşağıdaki altı alanlı özel kayıt biçimi de işlenir:

```text
Ab123,"transfer","public","today","done","42"
```

Özel kayıt kuralının ürettiği çıktı:

```text
[ID_1],[TRANSACTION_1],"public",[DATE_1],[STATUS_1],[VALUE_1]
```

Sırasıyla kayıt numarası, işlem, tarih, durum ve değer alanları maskelenir. Üçüncü alan bu özel kuralla maskelenmez; diğer tespit kuralları burada da çalışır. Bu destek genel amaçlı bir CSV ayrıştırıcısı değildir.

- `[MANUAL_1]`: API üzerinden `manual_spans` ile açıkça seçilen alanlar.
- `[SENSITIVE_1]`: Farklı türlerdeki kısmi tespitler örtüştüğünde oluşabilen birleşik hassas alan.

Aynı istek içinde aynı türde ve aynı normalleştirilmiş değerde tekrarlanan tespitler aynı yer tutucuyu kullanır. Örtüşen kurallar nedeniyle çıktı etiketi tablodaki örnekten farklı olabilir; kapsanan hassas bölge tamamen maskelenir.

## API Kullanımı

`POST /anonymize` endpointi JSON gövdesinde `text` alanı bekler:

```powershell
$body = '{"text":"Bayram BAYRAKTAR email deneme@example.com"}'
Invoke-RestMethod `
  -Uri http://localhost:8001/anonymize `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

İstek gövdesi:

```json
{
  "text": "Bayram BAYRAKTAR email deneme@example.com",
  "threshold": 0.4,
  "profile": "strict",
  "include_originals": false,
  "manual_spans": []
}
```

Yanıt gövdesi:

```json
{
  "masked_text": "[NAME_1] email [EMAIL_1]",
  "entities": [
    {"start": 0, "end": 16, "label": "NAME", "score": 0.95, "placeholder": "[NAME_1]"},
    {"start": 23, "end": 41, "label": "EMAIL", "score": 0.85, "placeholder": "[EMAIL_1]"}
  ],
  "entities_count": 2,
  "counts_by_label": {"NAME": 1, "EMAIL": 1},
  "profile": "strict"
}
```

Bu yanıt temsilidir; NER tespitleri ve puanları modele göre değişebilir. `score` model güveni veya kural puanıdır; anonimleştirme doğruluğunun garantisi değildir.

## API için gelişmiş seçenekler

Web arayüzü ek ayar gerektirmeden çalışır. Aşağıdaki profil, inceleme ve elle seçim seçenekleri doğrudan API kullanımı içindir.

| Profil | Kapsam |
| --- | --- |
| `personal` | Kişi, konum, kurum, e-posta, telefon, kimlik, banka/kart, müşteri/sicil numarası, plaka ve adres |
| `technical` | Kişisel verilere ek olarak URL, hostname, IP, sipariş/mesaj numarası, marka, cihaz ve sunucu |
| `strict` (varsayılan) | Tüm kurallar; tarih/saat, mevcut özel kayıt biçimi ve kontrol basamağı geçersiz şüpheli numaralar dahil |

`personal` ve `technical` profillerinde mevcut kurum istisna listesi yalnızca NER kurum tespitlerine uygulanır. Kişi adlarına uygulanmaz. Katı modda bu istisnalar kullanılmaz. TCKN, TR IBAN ve kart numaraları kontrol basamaklarıyla doğrulanır. Diğer profillerde doğrulanamayan değerler açık `kimlik`, `TC`, `IBAN` veya `kart` bağlamı varsa yine maskelenir. Katı mod daha fazla yanlış maskeleme yapabilir.

API varsayılan olarak orijinal değerleri döndürmez. API isteğinde `include_originals: true` her varlığa `text` ekler. Bu mod yanıtı hassas veri içerir; paylaşılacak çıktı `masked_text` alanıdır. Yer tutucu eşleştirmeleri yalnızca bir istek içinde tutulur.

API üzerinden elle seçim örneği: `{"text":"😀 sır", "manual_spans":[{"start":2,"end":5}]}` → `😀 [MANUAL_1]`. Konumlar özgün metinde sıfırdan başlayan Unicode kod noktalarıdır; `end` hariçtir. Web arayüzünde metni düzenlemek eski sonucu temizler.

Uzun metinler 512 token sınırına sahip mevcut modelde 64 token örtüşmeyle işlenir. Daha farklı bir yerel model seçildiğinde pencere sınırı modele göre ayarlanır. Örtüşen tespitlerin kapsadığı bölge tamamen maskelenir; kısmi ve farklı türdeki çakışmalar `SENSITIVE` olarak gösterilebilir.

## Servis ayarları

Varsayılan dinleme adresi `127.0.0.1:8001`'dir. Aynı kaynaktan çalışan arayüz CORS gerektirmez; dış kaynaklara varsayılan izin verilmez.

```powershell
# Paylaşılan sunucuda çalıştırmadan önce kendi anahtarınızı belirleyin.
$env:ANONYMIZER_API_KEY = 'kendi-uzun-rastgele-anahtariniz'
# Gerekiyorsa LAN erişimi ve ayrı arayüz kaynağı:
$env:ANONYMIZER_HOST = '0.0.0.0'
$env:ANONYMIZER_CORS_ORIGINS = 'https://arayuz.example.com'
python api.py
```

Anahtar tanımlıysa `/anonymize` için `X-API-Key` başlığı gerekir; arayüzde anahtar alanı açılır. Anahtar tarayıcı depolamasına yazılmaz; Temizle butonu alanı da siler. Ağ üzerinden kullanımda HTTPS sağlayan ters proxy kullanın. Ortam değişkenleri değiştiğinde servisi yeniden başlatın.

- İstek metni en fazla 100.000 Unicode kod noktası; JSON gövdesi en fazla 1.000.000 bayt; elle seçim en fazla 1000 adettir. Tarayıcı metin alanı UTF-16 birimleri saydığından emoji içeren girişlerde daha erken sınır koyabilir.
- Her uygulama süreci aynı anda bir model işlemi çalıştırır. Diğer işlem istekleri `429` ve `Retry-After: 2` alır. Sağlık kontrolü model çalışırken yanıt verebilir.
- Geçersiz giriş `422`, büyük gövde `413`, hatalı anahtar `401`, model hatası/hazır olmaması `503` döndürür. Hata yanıtları orijinal metni içermez.
- Yanıtlar `Cache-Control: no-store` içerir. Uygulama metinleri diske yazmaz; `python api.py` erişim günlüğünü kapatır. Harici proxy/APM kayıtlarını ayrıca yapılandırın.
- Model ilk kullanımda indirilebilir. Önbellekteki modelle çevrimdışı çalışmak için `$env:HF_HUB_OFFLINE = '1'` kullanın. `ANONYMIZER_MODEL` ile yerel model klasörü belirtilebilir.
- Arayüz harici font veya script istemez. `/docs` ve `/redoc`, FastAPI'nin varsayılan CDN kaynaklarını kullanır.

## Test ve kalite ölçümü

```powershell
pip install -r requirements.txt
python -m pytest -q
node --check static/app.js
node --test tests/ui.test.cjs
python evaluate.py --offline --output evaluation-report.json
```

Birim/API testleri deterministik bir NER taklidi kullanır ve model indirmez. `evaluate.py` gerçek NER modelini, `tests/data/synthetic.json` içindeki 20 sentetik örnek üzerinde çalıştırır. Model henüz indirilmediyse ilk çalıştırmada `--offline` seçeneğini kaldırın.

Rapor veri türüne göre tam konum+tür eşleşmesi üzerinden precision, recall, kaçırma oranı ve yanlış tespit oranını verir. Hassas karakter kapsaması ayrıca ölçülür: türü farklı olsa da tamamen maskelenen alan ile gerçekten açık kalan veri böylece ayrılır. `differences` konum/tür farklarını, `overmasked_characters` gereksiz maskelenen karakter sayısını içerir. Bu küçük küme bir regresyon başlangıcıdır; üretim başarısı veya veri anonimliği garantisi değildir. Bozuk yazımlar ve bağlamsal kişi tespiti modelin hata yapabileceği alanlardır.

Uygulama, Hugging Face'in [örtüşmeli token sınıflandırma](https://github.com/huggingface/transformers/blob/main/src/transformers/pipelines/token_classification.py) desteğini ve Starlette'in [thread pool](https://www.starlette.io/threadpool/) mekanizmasını kullanır.

## Port Hatası

Şu hata görülürse:

```text
[WinError 10048] normal olarak her yuva adresi ... yalnızca bir kullanıma izin veriliyor
```

`8001` portu zaten başka bir `api.py` süreci tarafından kullanılıyor demektir. Önce port sahibini bulun:

```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen
```

Çıktıdaki `OwningProcess` değerini kullanarak eski süreci kapatın:

```powershell
Stop-Process -Id PROCESS_ID -Force
```

Ardından uygulamayı yalnızca bir kez başlatın:

```powershell
python api.py
```

Sunucu çalışırken aynı komutu ikinci bir terminalde tekrar çalıştırmayın.

## Proje Yapısı

```text
.
├── api.py                 # HTTP, doğrulama, erişim ve işlem sınırları
├── anonymizer.py          # Tespit, doğrulama, profiller ve maskeleme
├── evaluate.py            # Gerçek modelle kalite ölçümü
├── tests/                 # Motor/API/arayüz testleri ve sentetik veri
├── requirements.txt       # Uygulama ve test bağımlılıkları
├── README.md              # Kurulum ve kullanım dokümantasyonu
└── static/
    ├── index.html         # Web arayüzü
    ├── styles.css         # Arayüz stilleri
    └── app.js             # Arayüz davranışları ve API bağlantısı
```

## Güvenlik Notu

Anonimleştirme sistemi tüm hassas bilgileri yakalayamayabilir. Metni paylaşmadan önce çıktıyı mutlaka kontrol edin.
