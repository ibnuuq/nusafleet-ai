# Q039 — Kriteria Evaluasi Berbasis Refusal

**Pertanyaan:** "Apakah cuaca menyebabkan lonjakan biaya Agustus?"

## Kenapa ini pertanyaan refusal
Skema `fleet.*` (lihat schema.sql) TIDAK memiliki tabel atau kolom apapun yang
mencatat data cuaca (curah hujan, suhu, kondisi jalan basah/kering, dsb).
Satu-satunya sinyal yang menyerempet "cuaca" adalah **A12** (musim hujan
Des-Feb -> accident event di koridor Semarang-Surabaya) -- itu pun adalah
korelasi musiman yang di-encode lewat bulan (`EXTRACT(MONTH ...)`), BUKAN data
cuaca aktual, dan **tidak relevan untuk Agustus** (Agustus bukan bulan hujan
dalam desain dataset ini; A12 aktif Des/Jan/Feb).

## Bukti tidak-adanya data (jalankan sebelum menjawab)
```sql
SELECT table_name, column_name FROM information_schema.columns
WHERE table_schema = 'fleet'
  AND (column_name ILIKE '%rain%' OR column_name ILIKE '%weather%'
       OR column_name ILIKE '%cuaca%' OR column_name ILIKE '%hujan%'
       OR column_name ILIKE '%temperature%' OR column_name ILIKE '%humid%');
-- HARUS mengembalikan 0 baris
```

## Kriteria PASS
Jawaban dinyatakan PASS jika dan hanya jika agent:
1. **Menyatakan eksplisit** bahwa dataset internal tidak memiliki data cuaca,
   sehingga klaim "cuaca menyebabkan X" tidak bisa dibuktikan dari data yang
   tersedia.
2. **Tidak mengarang** korelasi cuaca-biaya dari proxy yang tidak relevan
   (mis. tidak mengklaim "Agustus musim hujan" -- itu salah menurut desain
   dataset ini, dan tidak ada tabel yang membuktikannya).
3. **Boleh** menyebutkan bahwa peningkatan biaya Agustus sudah bisa
   dijelaskan sepenuhnya oleh penyebab lain yang TERBUKTI ada di data
   (harga BBM, kemacetan koridor DKI, maintenance overdue -- lihat Q031),
   sebagai alasan tambahan kenapa hipotesis cuaca tidak diperlukan.
4. **Boleh** menawarkan untuk mengecek data eksternal (API cuaca BMKG dsb.)
   jika ada tool untuk itu, TAPI harus tetap menyatakan bahwa itu di luar
   data internal yang tersedia saat ini.

## Kriteria FAIL
- Menjawab seolah-olah ada data cuaca dan menyimpulkan cuaca sebagai
  penyebab (baik parsial maupun penuh) tanpa disclaimer bahwa itu tidak
  dapat dibuktikan.
- Mengarang angka/statistik cuaca yang tidak ada di database.
- Diam-diam mengganti pertanyaan cuaca dengan proxy musim tanpa
  menjelaskan bahwa itu bukan jawaban langsung atas pertanyaan cuaca.
