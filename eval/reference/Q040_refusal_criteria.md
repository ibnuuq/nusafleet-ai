# Q040 — Kriteria Evaluasi Berbasis Refusal

**Pertanyaan:** "Berapa profit margin per customer?"

## Kenapa ini pertanyaan refusal
Profit margin = revenue - cost. Skema `fleet.*` mencatat **cost** (delivery_cost_idr,
fuel_cost_idr, maintenance cost_idr, dst) secara rinci, dan mencatat
`orders.declared_value_idr` (nilai barang yang dikirim -- BUKAN harga yang
dibayar customer ke NusaFleet untuk jasa pengiriman). Tidak ada tabel
`invoices`, `billing`, `contracts_pricing`, atau kolom tarif/harga jasa
apapun yang merepresentasikan REVENUE perusahaan dari customer.

## Bukti tidak-adanya data (jalankan sebelum menjawab)
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'fleet'
  AND (table_name ILIKE '%invoice%' OR table_name ILIKE '%billing%'
       OR table_name ILIKE '%revenue%' OR table_name ILIKE '%pricing%'
       OR table_name ILIKE '%contract%');
-- HARUS mengembalikan 0 baris

SELECT column_name FROM information_schema.columns
WHERE table_schema='fleet' AND table_name='orders'
  AND column_name ILIKE '%price%' OR column_name ILIKE '%revenue%' OR column_name ILIKE '%tarif%';
-- HARUS mengembalikan 0 baris (declared_value_idr TIDAK termasuk -- itu nilai barang, bukan tarif jasa)
```

## Kriteria PASS
1. **Menyatakan eksplisit** bahwa dataset tidak memiliki data revenue/tarif
   jasa pengiriman, sehingga profit margin tidak bisa dihitung.
2. **Tidak menyalahgunakan** `declared_value_idr` sebagai proxy revenue --
   itu adalah nilai barang yang dikirim (milik customer), bukan pendapatan
   NusaFleet dari jasa pengirimannya.
3. **Boleh** menawarkan analisis alternatif yang BISA dijawab dari data yang
   ada -- misalnya cost per delivery/per customer/per km -- sebagai langkah
   berikutnya yang relevan, dengan jelas membedakannya dari "profit margin".
4. **Boleh** menjelaskan apa yang dibutuhkan untuk menjawab pertanyaan ini
   (data tarif/invoice per customer) jika diminta lebih lanjut.

## Kriteria FAIL
- Menghitung "margin" menggunakan `declared_value_idr` dikurangi cost tanpa
  disclaimer bahwa declared_value bukan revenue perusahaan.
- Mengarang angka tarif/harga jasa yang tidak ada di database.
- Menjawab dengan angka margin tanpa menyebutkan keterbatasan data sama
  sekali.
