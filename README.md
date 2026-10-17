# CepKontrol

Telefonundan Windows bilgisayarını kontrol et. Bir kez QR ile eşleştir; sonraki açılışlarda kod veya bilgisayar onayı istemeden bağlan.

Ücretsiz, açık kaynak Windows uzaktan destek uygulaması. Ekran görüntüsü,
fare, sürükleme, sağ tıklama, kaydırma, klavye ve Türkçe karakter desteği.
AnyDesk ile bağlantısı bulunmayan bağımsız bir ilk sürümdür.

## Kullanım

1. Kontrol edilecek Windows bilgisayarda **CepKontrol.exe** dosyasını açın.
2. **Telefonu eşleştir / QR göster** düğmesine basın.
3. Telefon kamerasıyla QR'ı okutun; açılan bağlantıya dokunun. Android/iPhone tarayıcısı yeterlidir.
4. Telefon kaydedilir ve doğrudan bağlanır. Bilgisayarda ek bir onay penceresi açılmaz.
5. Sonraki girişlerde telefonda aynı tarayıcıyla kontrol adresini açın; kayıtlı bilgisayara otomatik bağlanır.

Telefonda **Telefonun ana ekranına ekle / Telefona ekle** düğmesiyle uygulama simgesi oluşturabilirsiniz.
Simge ayrı uygulama penceresi açar ve son başarıyla bağlanılan bilgisayara otomatik bağlanır.
Bilgisayar veya internet geçici olarak erişilemezse açık telefon sayfası aralıklı olarak yeniden dener; bağlantı gelince QR ya da düğme gerektirmeden devam eder.
Telefonda **Bitir / Bağlantı isteğini iptal et** otomatik denemeyi durdurur. Sayfayı yeniden açmak otomatik bağlantıyı tekrar etkinleştirir.
Kalıcı kayıt aynı tarayıcı profiline aittir. Gizli sekme kullanmayın; site verileri silinirse yeniden eşleştirme gerekir.
Tarayıcı destekliyorsa kalıcı depolama talep edilir; işletim sistemi veya kullanıcı tarafından veri silinmesi engellenemez.
Çevrimdışıyken yalnızca arayüz açılır; uzaktan kontrol için internet gerekir. Ekran görüntüleri ve erişim anahtarları servis çalışanı önbelleğine alınmaz.

Uygulama bilgisayarda açık kalmalıdır. Uygulama kapanınca erişim durur; yeniden açılınca etkin eşleşmelerle bağlantı dinlemeye devam eder.
Windows başlangıcına otomatik eklenmez. Windows kilidi, oturum açma ve UAC güvenli masaüstü desteklenmez.
**Ayarlar** bölümünden kayıtlı telefonu kaldırabilir veya doğrudan erişimi kapatabilirsiniz.
Ana ekrandaki **Bağlantıyı kes** düğmesi etkin doğrudan erişimi durdurur; Ayarlar'dan yeniden açılabilir.

QR yerine telefonda **https://acikdestek-sunucu.tailcb8d95.ts.net/** adresini açıp bilgisayardaki bağlantı kodunu yapıştırabilirsiniz.
Varsayılan **Dokunmatik yüzey** modunda parmağınızı ekranın herhangi bir yerinde kaydırarak imleci bulunduğu yerden hareket ettirin.
Ekranın çevresindeki boş alanlar da dokunmatik yüzeydir. Parmağı kaldırıp farklı bir yere koymak imleci o noktaya atlatmaz.
Kısa dokunuş imlecin olduğu yerde tıklar; yarım saniye basılı tutup taşıma sürükler; iki parmakla hareket kaydırır.
Alttaki **İmleç** düğmesiyle **Doğrudan dokun** moduna geçebilirsiniz; tercih telefonda saklanır.
“Yazı yaz” ile telefon klavyesinden Türkçe metin gönderebilirsiniz. Sağ tık, Enter, Sil, Esc ve ok tuşları alttadır.
Daha büyük ekran için telefonu yatay çevirin. iPhone'da tarayıcı tam ekran desteği sınırlı olabilir.
Telefona EXE veya Tailscale kurulmaz. Kayıtlı telefon tekrar yerel onay gerektirmez.
Kodla bağlanan eşleşmemiş istemciler için yerel onay devam eder.
Tarayıcı kaydını silmek eşleşmeyi telefondan unutur; kalıcı iptal için bilgisayardaki Ayarlar'dan kaldırın.

Başka bir Windows bilgisayardan da aynı EXE'nin **Kodu yapıştır → Bağlan** bölümü kullanılabilir.

Yalnızca görüntüleme için “Fare ve klavye kontrolüne izin ver” seçimini kaldırın.
Uzak ekranın içine tıklayarak klavye kontrolünü etkinleştirin. F11 tam ekranı açar/kapatır.
Esc uzak bilgisayara da gönderilir; tutulan tuşları bırakır ve tam ekrandan çıkar.
Yerel fareyi ekranın köşesine taşımak PyAutoGUI güvenli durdurmasını tetikler.

## Mevcut sunucu

Hazır internet adresi: `wss://acikdestek-sunucu.tailcb8d95.ts.net`.
Uygulama bu adrese hazır gelir. Karşı tarafta Tailscale kurulumu gerekmez.
Windows uygulaması bu hazır sunucuya bağlanırken Tailscale üzerinden `ws://100.77.178.100:8765` özel yolunu önce dener; erişilemiyorsa genel WSS adresine döner.
Bu seçim kayıtlı telefonun genel HTTPS adresini, eşleşme anahtarını veya QR kodunu değiştirmez. Amaç PC trafiğinin HTTPS vekili üzerinden gereksiz yere geçirilmesini önlemektir.
Ubuntu: `192.168.1.69`, hizmet: `acikdestek.service`, yerel port: `8765`.
Yerel ağda Ayarlar'dan `ws://192.168.1.69:8765` seçilerek de kullanılabilir.

`100.95.233.35`, Windows bilgisayarının Tailscale adresidir; Ubuntu sunucusunun adresi değildir.
Ubuntu Tailscale ağına eklendi: `100.77.178.100`.
Tailscale Funnel yalnızca aktarım hizmetini HTTPS/WSS üzerinden internete açar.
Funnel beta durumundadır ve bant genişliği sınırlamalarına tabidir; yoğun kullanım için kendi alan adınız ve Caddy kurulumu tercih edilebilir.
Kaynak: https://tailscale.com/docs/features/tailscale-funnel
`sudo tailscale funnel status` durumunu gösterir; `sudo tailscale funnel --https=443 off` dış erişimi kapatır.

## İnternet sunucusu

Genel bir alan adı, sunucuya ulaşan 80/443 TCP portları ve Docker Compose varsa:

```sh
cp .env.example .env
# .env içindeki DOMAIN değerini kendi alan adınızla değiştirin.
docker compose up -d --build
```

Alan adının DNS kaydı sunucuya yönelmeli. Ev ağındaki sunucularda yönlendirici/CGNAT
durumu ayrıca değerlendirilmelidir. Caddy geçerli HTTPS/WSS sertifikasını yönetir.
İki bilgisayarda **Ayarlar → wss://destek.alanadiniz.com → Kaydet** kullanın.
Kısa bağlantı kodu sunucu adresini içermez; iki uygulamada aynı sunucu seçilmelidir.

## Gizlilik ve sınırlar

- Ekran ve kontrol mesajları uçtan uca AES-256-GCM ile şifrelenir. Bağlantı kodu 128 bit rastgele sır içerir; kodu yalnızca bağlanacak kişiyle paylaşın.
- Aktarım sunucusu bağlantı adreslerini, oda numarasını, paket boyutunu ve zamanlamasını görebilir; şifreleme anahtarı sunucuya gönderilmez.
- Eşleşmemiş istemciler ekran/kontrol için yerel onay alır. Eşleşmiş telefonlar değişen oturum sınaması ve HMAC-SHA256 doğrulamasıyla doğrudan bağlanır.
- İlk QR eşleştirme sırrı 10 dakika geçerlidir ve ilk kullanımda yeni bir telefon anahtarıyla değiştirilir. Eski QR kimlik bilgileri tekrar yetki vermez.
- Telefon anahtarları bilgisayarda Windows CurrentUser DPAPI ile şifreli tutulur; telefonda aynı tarayıcının yerel kaydında saklanır. Tarayıcı verilerinin silinmesi yeniden eşleştirme gerektirir.
- Eşleşmiş oturumlarda ekran ve kontrol için telefon anahtarı ile yeni sınamadan ayrı AES-GCM anahtarı türetilir. Önceki oturumdan kaydedilmiş kimlik doğrulama yanıtları kabul edilmez.
- Windows başlangıcında otomatik veya gizli başlama bulunmaz. Uygulama açıkken bağlantıyı dinler; kapatılması erişimi durdurur.
- Birincil monitör paylaşılır; bağlantı hızına göre yaklaşık 2–6 kare/sn, en fazla 1280×800 JPEG. Yavaş bağlantılarda 1024×640 ve daha düşük JPEG kalitesi seçilir.
- Güncel telefon istemcisi her görüntüyü gösterdikten sonra şifreli onay gönderir. Aynı anda yalnızca bir onaysız kare tutulur; eski telefon istemcileri daha düşük hızlı uyumlu aktarımı kullanır.
- Şifreli canlılık yanıtları görüntü aktarımından bağımsız olarak bağlantıyı kontrol eder. Telefonda 45 saniyelik yanıt toleransı, sunucuda 60 saniyelik ping toleransı ve 30 saniyelik aktarım zaman aşımı kullanılır.
- Bağlantı hatalarının türü, kapanış kodu ve oturum süresi bilgisayarda `%APPDATA%\AcikDestek\connection.log` dosyasına yazılır. Ekran, kontrol mesajı, bağlantı kodu ve erişim anahtarı kaydedilmez; günlük boyutu sınırlıdır.
- Ubuntu hizmeti rastgele izleme etiketi, kapanış kodu, süre ve toplam aktarılan bayt sayısını günlükte tutar; bağlantı kodu ve içerik kaydedilmez. `sudo journalctl -u acikdestek.service` ile okunur.
- Windows kilit ekranı, UAC güvenli masaüstü, Ctrl+Alt+Del, dosya aktarımı, ses ve pano eşitleme bu sürümde bulunmaz.
- Yönetici yetkili pencerelerin kontrolü Windows izinleriyle sınırlıdır.
- Kendi ağınızda `ws://` kullanılırken de içerik şifrelenir. Genel internet adreslerinde `wss://` zorunludur.
- Bu sürüm bağımsız güvenlik denetiminden geçmemiştir.
- Yazılım MIT lisansıyla ücretsizdir; sunucu, internet ve alan adı giderleri size aittir.

## Geliştirme

Windows ve Python 3.11+:

```powershell
python -m pip install -r requirements.txt
python app.py
python -m unittest discover -s tests -v
.\build.ps1
```

EXE: `dist/CepKontrol.exe`. Testlerde sentetik ekran kullanılır, klavye girdileri taklit edilir.
Mobil tarayıcı testi: `node tests/mobile_browser.cjs` (Playwright ve Edge gerekir).
Ana ekrana ekleme ve gerçek tarayıcı kapatma/açma testi: `node tests/pwa_browser.cjs`.
Tarayıcı testleri için `npm install --no-save playwright` kullanabilirsiniz. Edge yolu `BROWSER_PATH`, alternatif Playwright modülü `PLAYWRIGHT_MODULE` ile ayarlanabilir.
`MOBILE_SOAK_SECONDS=480` ve `MOBILE_NOISE=1` ile aynı test, yoğun sentetik görüntüyü sekiz dakika boyunca yeniden bağlantı olmadan gösterdiğini de doğrular.
Bu test şifreleme uyumunu, QR bağlantısını, dokunmayı, sürüklemeyi, iki parmak kaydırmayı ve Türkçe metni sentetik masaüstünde denetler.
Dokunmatik yüzey testi, parmağı başka yere koymayı, boş alandan kontrolü, uzun basarak sürüklemeyi ve iptal edilen dokunuşun tıklamamasını da doğrular.
PWA testi, tarayıcı yeniden açılışına ek olarak uzun bilgisayar kesintisinden ve internet geri gelişinden sonra kullanıcı müdahalesi olmadan yeniden bağlanmayı denetler.
`MOBILE_TRUSTED=1` ile aynı test, QR eşleştirmesini, yerel onay olmadan girişini, Windows uygulaması yeniden açıldıktan sonra yeniden bağlanmayı ve iptal edilen telefonun erişememesini de denetler.
15 Ekim 2026 doğrulaması: protokol/onay testleri yerel sunucuda, Ubuntu LAN adresinde,
WSS adresinde ve genel Funnel IP'sine zorlanan bağlantıda geçti. Son kontrolde TLS
sertifika doğrulaması açık tutuldu. Tk arayüzünden gerçek ekran yakalama, JPEG gösterimi,
onay penceresi, tam ekran ve bağlantı kesme de denetlendi. Gerçek fare/klavye enjeksiyonu
iki ayrı fiziksel bilgisayarda uçtan uca test edilmedi; otomatik testte girdiler taklit edildi.
Gerçek Ubuntu aktarım hizmetini test etmek için:

```powershell
$env:RELAY_TEST_URL = 'ws://192.168.1.69:8765'
python -m unittest discover -s tests -v
```

Sunucu durumunu Ubuntu'da `systemctl status acikdestek` ile görebilirsiniz.
Yardımcı `remote_admin.py` SSH parolasını etkileşimli ister; dosyaya yazmaz.
`ACIKDESTEK_SSH_HOST=100.77.178.100` ile sunucuya özel ağdan bağlanabilir; önceden doğrulanmış sunucu anahtarı denetlenir. `relay-logs` yalnızca aktarım hizmetinin son günlüklerini okur.
Sunucu kaynağını güncelledikten sonra hizmeti yeniden başlatın.

CepKontrol, önceki AçıkDestek sürümlerinin eşleşme kaydını ve şifreleme protokolünü korur. Bu nedenle `%APPDATA%\AcikDestek` dizini, tarayıcı kayıt anahtarları ve kurulu `acikdestek.service` hizmet adı uyumluluk için değişmez.

17 Ekim 2026 bağlantı doğrulaması: genel Funnel IP'sinden açılan telefon tarayıcısı ve PC'nin doğrudan özel aktarım yolu ile yoğun sentetik görüntü testi sekiz dakika sürdü; 270 kare gösterildi, yeniden bağlantı olmadı. Aynı test önceki HTTPS PC yolu ile yaklaşık bir dakikada kopmayı tekrarlamıştı. Bu ölçüm belirli test ağına aittir; farklı ağların davranışını garanti etmez.
