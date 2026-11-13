# AI Airspace Conflict Advisor

## 1. Gambaran Umum Proyek

**AI Airspace Conflict Advisor** merupakan sistem pendukung keputusan (*Decision Support System*) berbasis Artificial Intelligence (AI) yang dirancang untuk membantu mengidentifikasi dan memprediksi potensi konflik antara Unmanned Aerial Vehicle (UAV/drone) dengan pesawat berawak di sekitar area penerbangan drone.

Sistem ini mengintegrasikan data lalu lintas udara dari OpenSky Network, algoritma prediksi konflik menggunakan metode Closest Point of Approach (CPA), serta AI Agent berbasis Hermes untuk memberikan rekomendasi mitigasi terhadap potensi konflik yang teridentifikasi.

Proyek dikembangkan dalam bentuk simulasi berbasis komputer dengan dashboard interaktif yang memungkinkan pengguna merencanakan misi drone, memantau lalu lintas pesawat, menganalisis potensi konflik, serta mengevaluasi alternatif mitigasi.

Sistem memiliki dua mode utama:

1. **Pre-Flight Analysis:** menganalisis potensi konflik sebelum misi penerbangan dimulai dan memberikan rekomendasi mitigasi.
2. **In-Flight Monitoring:** memantau pergerakan drone selama simulasi penerbangan dan mengidentifikasi potensi konflik yang muncul sepanjang misi.

AI Agent berperan dalam menganalisis situasi dan mengusulkan strategi mitigasi. Sementara itu, perhitungan matematis dan validasi usulan tetap dilakukan oleh modul Python untuk memastikan hasil rekomendasi dapat dievaluasi secara konsisten.

---

## 2. Latar Belakang

Peningkatan pemanfaatan Unmanned Aerial Vehicle (UAV) dalam berbagai sektor, seperti pemetaan, inspeksi infrastruktur, pertanian, logistik, dan pemantauan lingkungan, meningkatkan kebutuhan terhadap pengelolaan ruang udara yang aman.

Salah satu tantangan dalam operasional UAV adalah potensi interaksi dengan pesawat berawak yang beroperasi di ruang udara yang sama. Perbedaan karakteristik penerbangan, keterbatasan informasi lalu lintas udara, dan perubahan kondisi penerbangan dapat meningkatkan kompleksitas pengambilan keputusan operator drone.

Oleh karena itu, diperlukan suatu sistem yang mampu:

- Memperoleh informasi lalu lintas udara di sekitar area misi.
- Memprediksi potensi konflik berdasarkan posisi dan pergerakan pesawat.
- Menganalisis kemungkinan konflik sebelum dan selama simulasi penerbangan.
- Menghasilkan alternatif mitigasi berdasarkan hasil analisis.
- Menyajikan informasi dan rekomendasi melalui dashboard yang mudah dipahami.

AI Airspace Conflict Advisor dikembangkan sebagai prototipe untuk mengeksplorasi penggunaan algoritma prediksi konflik yang dikombinasikan dengan AI Agent dalam mendukung proses perencanaan dan pemantauan misi UAV.

---

## 3. Tujuan Proyek

Tujuan pengembangan proyek ini adalah:

1. Mengembangkan sistem simulasi untuk merepresentasikan pergerakan drone berdasarkan parameter misi yang ditentukan pengguna.
2. Mengintegrasikan data lalu lintas pesawat menggunakan OpenSky Network API.
3. Mengimplementasikan metode Closest Point of Approach (CPA) untuk memprediksi potensi konflik antara drone dan pesawat berawak.
4. Mengembangkan mekanisme pembentukan dan evaluasi alternatif rute penerbangan.
5. Mengintegrasikan AI Agent berbasis Hermes untuk menganalisis situasi konflik dan mengusulkan strategi mitigasi.
6. Mengembangkan dashboard interaktif untuk menampilkan posisi drone, pesawat, lintasan, hasil analisis, dan rekomendasi.
7. Mengevaluasi kinerja sistem melalui berbagai skenario simulasi.

---

## 4. Arsitektur Sistem 

Sistem dikembangkan menggunakan arsitektur Client-Server yang terdiri atas frontend, backend, modul pemrosesan data, conflict detection engine, route evaluation engine, AI Agent, dan simulation monitoring.

### 4.1 Komponen Arsitektur

Sistem AI Agent Drone terdiri dari beberapa komponen utama yang saling terintegrasi untuk mendukung proses perencanaan misi drone, pemantauan lalu lintas udara, pendeteksian potensi konflik, serta pemberian rekomendasi mitigasi berbasis AI.

| Komponen | Deskripsi |
|---|---|
| **Frontend Dashboard** | Menyediakan antarmuka visual bagi pengguna untuk mengatur parameter misi drone, memantau lalu lintas pesawat di sekitar area penerbangan, melihat simulasi pergerakan drone, serta menampilkan hasil analisis dan rekomendasi AI. |
| **Backend System** | Menangani logika utama aplikasi, memproses permintaan dari pengguna, mengelola komunikasi antarkomponen, serta mengoordinasikan keseluruhan proses analisis. |
| **Pengambilan Data Lalu Lintas Udara** | Mengambil informasi lalu lintas pesawat dari sumber data eksternal, seperti OpenSky Network API, sebagai masukan untuk proses pemantauan dan analisis potensi konflik udara. |
| **Simulasi Penerbangan** | Menyimulasikan pergerakan drone berdasarkan rute dan parameter misi yang telah ditentukan, seperti posisi awal, tujuan, ketinggian, dan kecepatan. |
| **Deteksi dan Analisis Konflik** | Menganalisis kemungkinan terjadinya konflik antara lintasan drone dan lintasan pesawat di sekitarnya menggunakan metode *Closest Point of Approach* (CPA). |
| **Pembangkitan dan Evaluasi Rute** | Menghasilkan serta mengevaluasi alternatif rute penerbangan apabila terdeteksi potensi konflik, dengan mempertimbangkan tingkat risiko konflik dan kelayakan rute. |
| **AI Agent** | Membantu menginterpretasikan hasil analisis konflik, mempertimbangkan strategi mitigasi yang memungkinkan, serta memberikan rekomendasi untuk mendukung proses perencanaan misi dan pengambilan keputusan. |

Seluruh komponen saling terhubung melalui backend system sehingga informasi dapat diproses dan diteruskan antara dashboard, sumber data lalu lintas udara, sistem simulasi, modul analisis konflik, dan AI Agent.

### 4.2 Diagram Arsitektur Sistem

Secara umum, sistem AI Agent Drone bekerja melalui beberapa tahapan yang saling terintegrasi, dimulai dari konfigurasi misi oleh pengguna, pengambilan data lalu lintas udara, simulasi penerbangan, hingga analisis potensi konflik dan pemberian rekomendasi mitigasi.

Sistem memiliki dua mode operasi utama, yaitu **Pre-Flight Analysis** dan **In-Flight Monitoring**. Pre-Flight Analysis digunakan untuk mengevaluasi rencana penerbangan sebelum simulasi dimulai, sedangkan In-Flight Monitoring digunakan untuk memantau potensi konflik selama simulasi penerbangan berlangsung.

Diagram berikut menggambarkan alur kerja sistem secara keseluruhan.

    A([Mulai]) --> B[Pengguna Membuka Dashboard]
    B --> C[Memasukkan Parameter Misi Drone]
    C --> D[Backend Memproses Konfigurasi Misi]

    D --> E[Pengambilan Data Lalu Lintas Udara]
    E --> F[Validasi dan Pemrosesan Data Pesawat]
    F --> G[Simulasi dan Prediksi Lintasan Drone]
    
    G --> H[Analisis Potensi Konflik Menggunakan CPA]
    H --> I{Apakah Terdapat Potensi Konflik?}

    I -->|Tidak| J[Menampilkan Hasil Analisis dan Rute Misi]
    I -->|Ya| K[AI Agent Menganalisis Hasil Konflik]
    K --> L[Memberikan Rekomendasi Mitigasi]
    L --> M[Evaluasi dan Validasi Rekomendasi oleh Sistem]
    M --> N[Menampilkan Alternatif Rute atau Strategi Mitigasi]

    J --> O[Pengguna Meninjau dan Memilih Rencana Misi]
    N --> O

    O --> P{Apakah Misi Dilanjutkan?}
    P -->|Tidak| C
    P -->|Ya| Q[Memulai Simulasi Penerbangan]

    Q --> R[In-Flight Monitoring]
    R --> S[Memperbarui Posisi Drone dan Data Pesawat]
    S --> T[Analisis Ulang Potensi Konflik]
    T --> U{Apakah Terdapat Potensi Konflik Baru?}

    U -->|Tidak| V[Memperbarui Informasi pada Dashboard]
    U -->|Ya| W[AI Agent Memberikan Analisis dan Rekomendasi]
    W --> X[Menampilkan Peringatan dan Rekomendasi kepada Pengguna]
    
    V --> Y{Apakah Simulasi Selesai?}
    X --> Y
    Y -->|Tidak| R
    Y -->|Ya| Z[Menampilkan Hasil Akhir Simulasi]
    Z --> AA([Selesai])

![System Workflow](docs/Worklow_General.png)

**Penjelasan alur kerja:**

1. **Konfigurasi Misi:** Pengguna memasukkan parameter penerbangan drone melalui dashboard, seperti posisi awal, tujuan, ketinggian, dan kecepatan.
2. **Pengambilan Data:** Sistem mengambil data lalu lintas pesawat dari sumber eksternal, kemudian melakukan validasi dan pemrosesan data.
3. **Simulasi dan Analisis:** Sistem menyimulasikan lintasan drone dan menganalisis potensi konflik dengan lintasan pesawat di sekitarnya menggunakan metode CPA.
4. **Analisis dan Mitigasi:** Jika ditemukan potensi konflik, AI Agent membantu menganalisis kondisi dan memberikan rekomendasi mitigasi. Rekomendasi tersebut kemudian dievaluasi dan divalidasi oleh sistem.
5. **Pemilihan Rencana Misi:** Pengguna meninjau hasil analisis dan menentukan apakah simulasi penerbangan akan dilanjutkan.
6. **Pemantauan Selama Penerbangan:** Selama simulasi berlangsung, sistem memperbarui posisi drone dan informasi lalu lintas pesawat, kemudian melakukan analisis konflik secara berkala.
7. **Peringatan dan Rekomendasi:** Apabila ditemukan potensi konflik baru, sistem menampilkan peringatan serta rekomendasi dari AI Agent kepada pengguna.
8. **Hasil Akhir:** Setelah simulasi selesai, sistem menampilkan hasil akhir pemantauan dan analisis penerbangan.


### 4.3 Fungsi Komponen

**Frontend Dashboard**

Berfungsi sebagai antarmuka pengguna untuk:

- Mengatur parameter misi drone.
- Menentukan titik awal dan tujuan penerbangan.
- Menampilkan peta dan posisi pesawat.
- Menampilkan lintasan drone.
- Menampilkan hasil Pre-Flight Analysis.
- Menampilkan kondisi In-Flight Monitoring.
- Menampilkan rekomendasi dari AI Agent.

**Backend API**

Berfungsi sebagai penghubung antara frontend dan seluruh modul pemrosesan Python.

Backend menerima permintaan dari dashboard, menjalankan proses analisis, dan mengirimkan hasil dalam format data yang dapat ditampilkan frontend.

**Aircraft Data Acquisition**

Mengambil informasi lalu lintas udara melalui OpenSky Network API atau menggunakan data sintetis untuk pengujian dan demonstrasi.

**Conflict Detection Engine**

Menghitung prediksi posisi relatif antara drone dan pesawat, menentukan titik pendekatan terdekat, serta mengidentifikasi kondisi yang memenuhi kriteria potensi konflik.

**Route Evaluation & Mitigation**

Membentuk kandidat rute alternatif, menjalankan evaluasi CPA, dan memeriksa apakah kandidat memenuhi batasan simulasi.

**AI Agent**

Menggunakan Hermes untuk menganalisis informasi konflik, mengusulkan strategi mitigasi, dan menjelaskan hasil evaluasi.

**Simulation & Monitoring**

Mensimulasikan pergerakan drone berdasarkan flight plan yang aktif serta melakukan pemantauan dan analisis konflik selama simulasi berlangsung.

---

## 5. Teknologi yang Digunakan

Teknologi utama yang digunakan dalam proyek ini adalah:

- Programming Language : Python 
- Backend Framework : FastAPI 
- Frontend Framework : React.js 
- Map Visualization : MapLibre 
- Aircraft Traffic Data : OpenSky Network API 
- AI Agent : Hermes 
- LLM Provider : OpenRouter 
- Conflict Detection : Closest Point of Approach (CPA) 

---

## 6. Alur Kerja Sistem

Sistem memiliki dua alur kerja utama, yaitu Pre-Flight Analysis dan In-Flight Monitoring.

### 6.1 Analisis Sebelum Penerbangan (Pre-Flight Analysis)

Pre-Flight Analysis merupakan proses analisis sebelum drone memulai misi penerbangan.

Proses ini bertujuan untuk mengidentifikasi potensi konflik pada rencana penerbangan dan menentukan kemungkinan mitigasi sebelum simulasi dijalankan.

#### Workflow Diagram

    A([Start]) --> B["User Mengatur Parameter Misi"]
    B --> C["Menentukan Start Point dan Destination"]
    C --> D["Mengatur Altitude, Speed, dan Parameter Simulasi"]

    D --> E["Mengambil Data Pesawat"]
    E --> F{"Data Tersedia?"}

    F -- Tidak --> G["Menggunakan Demo Data / Menampilkan Status Data"]
    F -- Ya --> H["Memproses Data Pesawat"]
    G --> I["Membentuk Flight Plan"]
    H --> I

    I --> J["CPA Conflict Detection"]
    J --> K{"Potensi Konflik?"}

    K -- Tidak --> L["Menyimpan Flight Plan Awal"]
    K -- Ya --> M["Membentuk Kandidat Mitigasi"]

    M --> N["Python Route Generator dan Route Evaluator"]
    N --> O["Hermes Mengusulkan Strategi Mitigasi"]
    O --> P["Python Memvalidasi Usulan dengan CPA"]

    P --> Q{"Usulan Memenuhi Kriteria?"}
    Q -- Tidak --> R["Mengirim Hasil Evaluasi sebagai Feedback"]
    R --> O
    Q -- Ya --> S["Menampilkan Kandidat Mitigasi"]

    S --> T["User Memilih Mitigasi"]
    T --> U["Membentuk Active Simulation Plan"]
    L --> U

    U --> V([Pre-Flight Selesai])

![Pre-Flight Workflow](docs/Workflow_Pre_Flight.png)

#### Proses Pre-Flight 

1. Pengguna memasukkan koordinat awal dan tujuan drone.
2. Pengguna mengatur parameter penerbangan seperti altitude dan speed.
3. Sistem mengambil data pesawat dari OpenSky Network atau menggunakan data Demo.
4. Backend membentuk flight plan drone.
5. CPA Engine melakukan analisis potensi konflik antara lintasan drone dan pesawat.
6. Jika ditemukan potensi konflik, sistem menjalankan mekanisme mitigasi.
7. Python menghasilkan kandidat rute dan mengevaluasi kandidat berdasarkan CPA.
8. Hermes dapat mengusulkan strategi mitigasi seperti perubahan rute, altitude, atau departure delay.
9. Usulan Hermes diperiksa kembali menggunakan perhitungan Python.
10. Dashboard menampilkan hasil analisis dan alternatif mitigasi.
11. Pengguna memilih rencana mitigasi yang akan digunakan dalam simulasi.

### Pemantauan Selama Penerbangan (In-Flight Monitoring)

In-Flight Monitoring merupakan proses pemantauan selama simulasi penerbangan berlangsung.

Sistem memperbarui posisi drone berdasarkan waktu simulasi dan mengevaluasi potensi konflik sepanjang penerbangan.

#### Workflow Diagram

    A([Start In-Flight]) --> B["Memuat Active Flight Plan"]
    B --> C["Menjalankan Drone Simulator"]
    C --> D["Memperbarui Posisi Drone"]
    D --> E["Mengambil / Memperbarui Data Pesawat"]
    E --> F["Melakukan CPA Analysis"]
    F --> G{"Potensi Konflik?"}

    G -- Tidak --> H["Memperbarui Dashboard"]
    H --> I{"Misi Selesai?"}
    I -- Tidak --> D
    I -- Ya --> J([Simulation Completed])

    G -- Ya --> K["Menampilkan Conflict Warning"]
    K --> L["Mengirim Informasi Konflik ke Hermes"]
    L --> M["Hermes Menganalisis Situasi"]
    M --> N["Menampilkan Penjelasan dan Rekomendasi"]
    N --> O["Operator Mengevaluasi Rekomendasi"]
    O --> H

![Pre-Flight Workflow](docs/Workflow_In_Flight.png)

#### Proses In-Flight

1. Sistem memuat active flight plan yang telah dipilih pengguna.
2. Drone simulator menjalankan pergerakan drone.
3. Posisi drone diperbarui berdasarkan waktu simulasi.
4. Sistem melakukan analisis CPA terhadap pesawat di sekitar lintasan drone.
5. Jika ditemukan potensi konflik, dashboard menampilkan peringatan.
6. Informasi konflik dapat dikirimkan kepada Hermes untuk memperoleh analisis dan penjelasan.
7. Rekomendasi ditampilkan kepada pengguna.
8. Pemantauan berlanjut hingga simulasi selesai.

---

## 7. Fitur Utama Sistem 

### 7.1 Perencanaan Misi Drone (Mission Planner)

Mission Planner memungkinkan pengguna menentukan parameter misi penerbangan drone.

Parameter yang digunakan meliputi:

| Parameter | Deskripsi | Satuan |
|---|---|---|
| Start Latitude | Koordinat lintang titik awal | Degree |
| Start Longitude | Koordinat bujur titik awal | Degree |
| Destination Latitude | Koordinat lintang tujuan | Degree |
| Destination Longitude | Koordinat bujur tujuan | Degree |
| Altitude | Ketinggian simulasi drone | Meter |
| Speed | Kecepatan drone | m/s |
| Time Step | Interval perhitungan simulasi | Detik |
| Monitoring Radius | Cakupan pemantauan pesawat | km |

Pengguna dapat menentukan lokasi melalui koordinat maupun interaksi dengan peta, sesuai fitur yang tersedia pada dashboard.

### 7.2 Pemantauan Lalu Lintas Pesawat (Aircraft Monitoring)

Sistem mengambil data lalu lintas udara menggunakan OpenSky Network API.

Informasi pesawat yang dapat digunakan dalam analisis meliputi:

- ICAO24 address.
- Callsign.
- Latitude.
- Longitude.
- Barometric altitude.
- Velocity.
- True track / heading.
- Vertical rate.
- Timestamp dan status data lainnya jika tersedia.

Data digunakan untuk merepresentasikan posisi dan pergerakan pesawat dalam proses analisis CPA.

Sistem juga mendukung penggunaan data sintetis untuk skenario demonstrasi dan pengujian.

### 7.3 Deteksi Konflik Udara (Conflict Detection)

Conflict Detection menggunakan metode Closest Point of Approach (CPA) untuk memperkirakan jarak terdekat antara drone dan pesawat berdasarkan model pergerakan yang digunakan.

Hasil analisis digunakan untuk mengidentifikasi potensi konflik berdasarkan threshold horizontal dan vertikal.

### 7.4 Mitigasi dan Evaluasi Rute (Route Mitigation)

Sistem dapat membentuk beberapa kandidat rute alternatif melalui perubahan geometris terhadap lintasan awal.

Metode yang digunakan meliputi:

- Pergeseran titik belok ke kiri.
- Pergeseran titik belok ke kanan.
- Variasi jarak offset.
- Variasi posisi titik belok sepanjang rute.

Pada konfigurasi adaptive route generation yang telah diuji, sistem dapat membentuk 30 kandidat dari kombinasi arah, offset, dan posisi titik belok.

Jumlah dan parameter kandidat mengikuti konfigurasi implementasi.

### 7.5 Route Evaluation

Setiap kandidat rute dievaluasi menggunakan perhitungan CPA.

Evaluasi dilakukan untuk mengetahui:

- Jumlah potensi konflik.
- Horizontal CPA.
- Vertical separation.
- Estimasi durasi penerbangan.
- Jarak lintasan.
- Kelayakan kandidat berdasarkan parameter simulasi.

Kandidat yang tidak memenuhi kriteria tidak boleh dianggap sebagai rute bebas konflik.

### 7.6 Rekomendasi Berbasis AI (AI Advisory)

AI Agent berbasis Hermes digunakan untuk:

- Menganalisis informasi konflik.
- Memahami hasil evaluasi CPA.
- Mengusulkan perubahan rute.
- Mengusulkan perubahan altitude.
- Mengusulkan departure delay.
- Memberikan penjelasan terhadap hasil analisis.
- Memanfaatkan feedback hasil evaluasi Python dalam proses mitigasi.

AI Agent tidak menggantikan perhitungan CPA maupun proses validasi matematis.

---

## 8. Metode Deteksi Konflik

### 8.1 Closest Point of Approach (CPA)

Closest Point of Approach merupakan metode untuk memperkirakan jarak terdekat antara dua objek yang bergerak berdasarkan posisi dan kecepatan relatifnya.

Dalam proyek ini, CPA digunakan untuk memperkirakan potensi pendekatan antara drone dan pesawat berawak.

Implementasi juga harus memperhatikan pembatasan horizon prediksi, satuan, transformasi koordinat, dan penanganan kondisi khusus.

### 8.2 Vertical Separation

Separasi vertikal dihitung berdasarkan perbedaan ketinggian drone dan pesawat:

[
\Delta h =
|h_{aircraft}-h_{drone}|
]

Nilai ini digunakan bersama HCPA untuk menentukan apakah kondisi memenuhi kriteria potensi konflik.

### 8.3 Conflict Threshold

Parameter yang digunakan pada konfigurasi eksperimen saat ini:

| Parameter | Nilai |
|---|---:|
| Horizontal CPA Threshold | 10.000 meter |
| Vertical Separation Threshold | 300 meter |
| Monitoring Radius | 70 km pada konfigurasi simulasi yang digunakan |

Kriteria potensi konflik:

\[
HCPA \leq 10.000\text{ m}
\]

DAN

\[
\Delta h \leq 300\text{ m}
\]

Kedua kondisi harus terpenuhi untuk dikategorikan sebagai potensi konflik berdasarkan aturan eksperimen saat ini.

Threshold tersebut merupakan parameter penelitian dan simulasi, bukan standar separasi universal atau batas keselamatan operasional UAV.

---

## 9. AI Agent dan Strategi Mitigasi

### 9.1 Aristektur AI Agent

Sistem mengintegrasikan Hermes sebagai AI Agent melalui koneksi yang dikonfigurasi menggunakan OpenRouter dan/atau gateway Hermes sesuai environment yang digunakan.

AI Agent menerima informasi situasi konflik dan menghasilkan usulan mitigasi yang kemudian diproses serta dievaluasi oleh backend Python.

### 9.2 Pembagian Tanggung Jawab

| Komponen | Tanggung Jawab |
|---|---|
| Python Route Generator | Membentuk kandidat rute geometris |
| Python CPA Engine | Menghitung prediksi pendekatan terdekat |
| Route Evaluator | Mengevaluasi kandidat berdasarkan CPA |
| Hermes AI Agent | Menganalisis konflik dan mengusulkan strategi |
| Python Validation | Memvalidasi usulan mitigasi |
| Dashboard | Menampilkan hasil dan memberikan kontrol kepada pengguna |

### 9.3 Strategi Mitigasi

Sistem mempertimbangkan tiga strategi utama:

**1. Route Modification**

Mengubah lintasan horizontal drone dengan menambahkan atau menggeser titik belok.

**2. Altitude Adjustment**

Mengubah ketinggian penerbangan drone untuk memperoleh separasi vertikal yang berbeda.

**3. Departure Delay**

Mengubah waktu keberangkatan untuk mengurangi kemungkinan pertemuan drone dan pesawat pada waktu yang sama.

### 9.4 Agent Feedback Loop

Proses mitigasi dapat dilakukan secara iteratif:

1. CPA mengidentifikasi konflik.
2. Informasi konflik dikirimkan kepada Hermes.
3. Hermes mengusulkan strategi mitigasi.
4. Python membentuk atau memproses usulan.
5. CPA mengevaluasi hasil mitigasi.
6. Hasil evaluasi dikirimkan kembali sebagai feedback.
7. Hermes dapat mengusulkan tindakan berikutnya sesuai batas iterasi.
8. Kandidat yang memenuhi kriteria ditampilkan kepada pengguna.

Dengan pendekatan ini, Hermes berperan sebagai komponen pengambilan keputusan, sedangkan Python bertanggung jawab atas perhitungan dan validasi.

---

## 10. Batasan dan Kendala Rekayasa (Engineering Constraints)

Engineering Constraints merupakan batasan teknis dan operasional yang digunakan untuk memastikan sistem dikembangkan dan dievaluasi dalam ruang lingkup yang jelas.

### 10.1 Functional Constraints

1. Sistem dikembangkan sebagai software-based simulation.
2. Pengguna dapat menentukan parameter misi drone melalui dashboard.
3. Sistem harus mampu membentuk representasi lintasan drone.
4. Sistem menggunakan data pesawat dari OpenSky Network atau data sintetis untuk demonstrasi.
5. Sistem harus dapat melakukan analisis CPA terhadap lintasan drone dan pesawat.
6. Sistem dapat membentuk dan mengevaluasi alternatif mitigasi.
7. Rekomendasi Hermes harus melalui validasi Python sebelum dikategorikan memenuhi kriteria simulasi.
8. Sistem menyediakan mode Pre-Flight Analysis dan In-Flight Monitoring.
9. Pengguna tetap memiliki kendali dalam memilih rencana mitigasi yang akan digunakan pada simulasi.

### 10.2 Technical Constraints

1. Backend dikembangkan menggunakan Python dan FastAPI.
2. Frontend dikembangkan menggunakan React.
3. Visualisasi peta menggunakan MapLibre.
4. Data antarbagian sistem dipertukarkan melalui API dan format JSON.
5. Perhitungan CPA dilakukan menggunakan modul Python, bukan diserahkan sepenuhnya kepada LLM.
6. AI Agent menggunakan Hermes dengan penyedia atau gateway model yang dikonfigurasi.
7. Ketersediaan layanan eksternal seperti OpenSky Network dan LLM provider bergantung pada koneksi internet, autentikasi, dan batas penggunaan layanan.
8. Proses simulasi menggunakan asumsi gerak dan parameter yang ditentukan dalam konfigurasi sistem.

### 10.3 Data Constraints

1. OpenSky Network digunakan sebagai sumber data lalu lintas udara, bukan sebagai sumber yang menjamin seluruh pesawat di suatu wilayah terpantau.
2. Ketersediaan data bergantung pada cakupan sensor, kualitas penerimaan, dan pembaruan data.
3. Data pesawat dapat mengalami keterlambatan, ketidaklengkapan, atau ketidakakuratan.
4. Data sintetis dapat digunakan untuk menguji skenario tertentu, tetapi tidak merepresentasikan seluruh kondisi penerbangan nyata.
5. Timestamp dan referensi ketinggian harus diperhatikan ketika membandingkan data drone dan pesawat.
6. Hasil prediksi tidak boleh dianggap lebih akurat daripada kualitas data masukan yang digunakan.

### 10.4 Simulation Constraints

1. Drone merupakan objek simulasi dan tidak terhubung dengan perangkat UAV fisik.
2. Pergerakan drone ditentukan oleh flight plan dan parameter simulasi.
3. Posisi drone pada dashboard merupakan posisi hasil perhitungan simulasi.
4. Prediksi pergerakan pesawat bergantung pada informasi yang tersedia dan model prediksi yang digunakan.
5. Model pergerakan dapat menggunakan asumsi kecepatan, heading, dan altitude konstan dalam horizon analisis tertentu.
6. Kondisi dunia nyata seperti cuaca, turbulensi, manuver mendadak, dan perubahan instruksi ATC belum sepenuhnya direpresentasikan.

### 10.5 AI Agent Constraints

1. Hermes digunakan untuk analisis dan rekomendasi, bukan sebagai satu-satunya penentu keselamatan penerbangan.
2. Output LLM dapat mengandung kesalahan atau usulan yang tidak sesuai kondisi.
3. Setiap usulan mitigasi harus diperiksa kembali oleh mekanisme validasi Python.
4. Rekomendasi dibatasi oleh parameter, tool, dan jumlah iterasi yang dikonfigurasi.
5. Sistem tidak boleh menganggap seluruh rekomendasi AI pasti valid hanya karena dihasilkan oleh model.
6. Ketersediaan dan kualitas rekomendasi bergantung pada koneksi dan respons layanan LLM.

### 10.6 Safety and Operational Constraints

1. Sistem merupakan prototipe penelitian dan bukan sistem keselamatan penerbangan yang tersertifikasi.
2. Threshold CPA yang digunakan merupakan parameter eksperimen, bukan standar universal.
3. Hasil tanpa konflik hanya menunjukkan bahwa konflik tidak ditemukan berdasarkan model, data, dan parameter yang digunakan.
4. Hasil simulasi tidak dapat dianggap sebagai izin terbang, jaminan bebas konflik, atau persetujuan dari otoritas penerbangan.
5. Sistem tidak memberikan kendali langsung kepada drone fisik.
6. Pengambilan keputusan operasional tetap memerlukan prosedur dan otoritas yang berlaku.

---

## 11. Konfigurasi Sistem

Parameter sistem dikelola melalui konfigurasi backend, termasuk `config.py` untuk parameter analisis yang digunakan oleh modul terkait.

Contoh parameter konfigurasi yang perlu diperhatikan:

| Parameter | Deskripsi | Contoh Nilai |
|---|---|---:|
| Horizontal CPA Threshold | Batas jarak horizontal potensi konflik | 10.000 m |
| Vertical Separation Threshold | Batas separasi vertikal | 300 m |
| Monitoring Radius | Cakupan pemantauan pesawat | 70 km |
| Drone Altitude | Ketinggian simulasi drone | 150 m |
| Drone Speed | Kecepatan simulasi drone | 10 m/s |
| Time Step | Interval simulasi | 30 s |

Nilai di atas merupakan contoh konfigurasi pengujian dan dapat berubah sesuai skenario penelitian.

Pengaturan aktual mengikuti parameter yang tersedia pada `config.py`, `simulator.py`, dan modul terkait.

---

## 12. Testing and Evaluation

Pengujian dilakukan untuk memeriksa fungsi masing-masing modul serta kemampuan sistem dalam menangani berbagai skenario simulasi.

### 12.1 Unit Testing

Modul yang dapat diuji meliputi:

- Conflict Detection.
- CPA Analyzer.
- Route Generator.
- Route Evaluator.
- Agent Flight Planner.
- Simulation Plan.
- In-Flight Monitoring.
- Hermes Advisor.

Hasil pengujian harus diperbarui sesuai kondisi kode terbaru.

### 12.2 Simulation Testing

Pengujian dapat dilakukan menggunakan:

1. Skenario tanpa potensi konflik.
2. Skenario dengan potensi konflik horizontal.
3. Skenario dengan potensi konflik vertikal.
4. Skenario perlintasan lintasan drone dan pesawat.
5. Skenario perubahan altitude.
6. Skenario perubahan rute.
7. Skenario departure delay.
8. Skenario dengan variasi jumlah pesawat.
9. Skenario dengan keterlambatan atau ketidaklengkapan data.

### 12.3 Performance Evaluation

Beberapa metrik yang dapat digunakan dalam penelitian:

- Conflict Detection Result : Mengukur hasil deteksi konflik 
- Horizontal CPA : Mengukur jarak pendekatan horizontal 
- Vertical Separation : Mengukur separasi vertikal 
- Mitigation Success Rate : Mengukur keberhasilan mitigasi 
- Conflict Reduction Rate : Mengukur pengurangan konflik 
- Route Distance Increase : Mengukur tambahan jarak rute 
- Response Time : Mengukur waktu respons sistem 
- Computational Time : Mengukur waktu pemrosesan 
- AI Iteration Count : Mengukur jumlah percobaan mitigasi AI 

---

## 15. Keterbatasan Sistem

Beberapa keterbatasan sistem saat ini meliputi:

1. Sistem masih berupa simulasi komputer dan belum terintegrasi dengan drone fisik.
2. Data OpenSky Network memiliki keterbatasan cakupan dan kelengkapan informasi.
3. Akurasi prediksi bergantung pada kualitas data masukan dan asumsi model pergerakan.
4. Model prediksi belum sepenuhnya merepresentasikan seluruh dinamika penerbangan nyata.
5. Alternatif rute yang dihasilkan masih dibatasi oleh metode dan parameter pencarian yang digunakan.
6. AI Agent bergantung pada layanan model bahasa dan tidak menjamin seluruh usulan benar.
7. Sistem belum menggantikan prosedur operasional, pengawasan ATC, maupun persyaratan regulasi penerbangan.

---

## 16. Rencana Pengembangan Selanjutnya

Pengembangan berikutnya dapat diarahkan pada:

- Peningkatan metode prediksi trajectory pesawat.
- Pengembangan algoritma pencarian rute yang lebih adaptif.
- Evaluasi performa Hermes dibandingkan metode baseline.
- Integrasi data lalu lintas udara dengan cakupan lebih baik.
- Pengembangan uncertainty-aware conflict prediction.
- Evaluasi pengaruh data latency terhadap hasil CPA.
- Pengembangan automatic replanning dalam lingkungan simulasi.
- Integrasi telemetry UAV untuk pengembangan lebih lanjut.
- Pengujian dengan skenario dan data yang lebih representatif terhadap kondisi operasional.
- Dashboard diubah ke dalam bentuk vercel.app sehingga dapat diakses oleh seluruh orang 

---

## 17. Referensi 

Dokumentasi dan sumber teknologi yang digunakan:

1. **OpenSky Network:** https://opensky-network.org/
2. **OpenSky Network API Documentation:** https://openskynetwork.github.io/opensky-api/
3. **FastAPI Documentation:** https://fastapi.tiangolo.com/
4. **React Documentation:** https://react.dev/
5. **MapLibre Documentation:** https://maplibre.org/
6. **OpenRouter Documentation:** https://openrouter.ai/docs
7. **Mermaid Documentation:** https://mermaid.js.org/

---

## 18. Disclaimer

AI Airspace Conflict Advisor merupakan prototipe penelitian untuk mempelajari penerapan AI Agent dan metode prediksi CPA dalam mendukung analisis potensi konflik penerbangan UAV.

Sistem hanya digunakan dalam lingkungan simulasi dan tidak dimaksudkan untuk menggantikan sistem manajemen lalu lintas udara, prosedur ATC, sistem deteksi konflik tersertifikasi, maupun keputusan operator yang berwenang.

Seluruh hasil prediksi dan rekomendasi harus dipahami berdasarkan batasan data, asumsi model, dan parameter eksperimen yang digunakan.

**Project Status:** Research Prototype / Software-Based Simulation
