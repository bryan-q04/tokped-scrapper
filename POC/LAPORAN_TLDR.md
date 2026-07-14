# TL;DR - Analisis Penjualan Produk IQOS di Tokopedia

Tanggal: 9 Juli 2026

## Tujuan
- Mengumpulkan (scrape) data produk IQOS di Tokopedia untuk membandingkan penjualan antara official store dan seller lain.
- Cakupan kata kunci: "iqos" dan "iluma". Cakupan kota: Jabodetabek, Bandung, Medan, Surabaya.

## Cara Kerja Singkat
- Data diambil langsung dari API pencarian Tokopedia, di-scrape sampai halaman terakhir (bukan dibatasi 2 halaman).
- Hasil disaring otomatis untuk memisahkan produk IQOS asli dari aksesoris dan produk tidak relevan.

## Temuan Utama
- Dari 533 baris data yang terkumpul, hanya sekitar 50 produk yang benar-benar produk IQOS asli; sisanya aksesoris (case, cleaner, cover) atau produk merek lain yang kebetulan memakai kata "iluma/terea".
- Pasar IQOS di Tokopedia kecil dan terpusat di Jabodetabek (49 dari 50 produk). Bandung dan Medan hampir tidak ada produk IQOS asli.
- Tidak ada Official Store resmi Tokopedia (badge Mall) di kategori ini. Semua penjual adalah seller biasa. Toko bernama "IQOS Partner Official Store" hanya menggunakan kata "Official Store" pada namanya, bukan badge resmi Tokopedia.
- Produk yang paling laku: IQOS ILUMA TEREA Golden - 1 Pack (100+ terjual, Rp30.500) oleh IQOS Partner Official Store.
- Perangkat (device) ILUMA terjual sedikit (kisaran 1-70 unit), sebagian besar barang impor/grey market.
- TEREA (batang tembakau) sangat langka karena pembatasan produk tembakau di Tokopedia.
- MIXOLOGIST PALAZZO memiliki listing terbanyak (22 produk) tetapi 0 terjual, indikasi importir grey market dengan harga tinggi.
- Produk dengan volume tertinggi justru bukan produk IQOS, melainkan cleaning kit pihak ketiga (FRIEQUOS).

## Keterbatasan Data
- Angka "terjual" dari Tokopedia bersifat dibulatkan (contoh: 100+, 1rb+), bukan angka pasti. Untuk angka pasti diperlukan pemantauan harian (belum dijalankan).
- Tokopedia tidak menyediakan skor keyakinan/relevansi per produk; urutan hasil hanya berdasarkan kecocokan kata kunci dan popularitas, sehingga aksesoris ikut muncul.

## Output yang Dihasilkan
- File CSV daftar produk (lengkap dengan penanda relevan/tidak relevan).
- File CSV daftar seller yang menjual produk IQOS asli (bukan aksesoris).
- Laporan HTML interaktif (ringkasan, tabel seller, tabel produk, data mentah).

## Catatan untuk Ditindaklanjuti
- Perlu penegasan definisi "official store" dari sisi klien, karena tidak ada badge Mall resmi di Tokopedia untuk produk ini.
- Opsi lanjutan: pemantauan harian untuk mengukur kecepatan penjualan (sales velocity) yang lebih akurat.
</content>
