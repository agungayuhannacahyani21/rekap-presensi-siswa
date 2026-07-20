import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. KONFIGURASI KONEKSI GOOGLE SHEETS
# ==========================================
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Pastikan file credentials.json berada di folder proyek yang sama dengan file app.py ini
credentials_dict = dict(st.secrets["gcp_service_account"])
creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
client = gspread.authorize(creds)

# Buka spreadsheet berdasarkan nama yang telah dibuat di Tahap 1
sh = client.open(spreadsheet_name)

# ==========================================
# 2. FUNGSI MENARIK DATA MASTER SISWA
# ==========================================
@st.cache_data(ttl=600)  # Menyimpan data di memori selama 10 menit agar aplikasi terasa cepat
def muat_data_master():
    try:
        sheet_master = sh.worksheet("Master_Siswa")
        # Mengambil semua baris data dari tab Master_Siswa
        semua_data = sheet_master.get_all_records()
        
        # Proses pengelompokan nama siswa berdasarkan kelasnya
        pemetaan_kelas = {}
        for baris in semua_data:
            kelas = str(baris.get("Kelas")).strip()
            nama = str(baris.get("Nama Siswa")).strip()
            
            if kelas not in pemetaan_kelas:
                pemetaan_kelas[kelas] = []
            pemetaan_kelas[kelas].append(nama)
            
        return pemetaan_kelas
    except gspread.exceptions.WorksheetNotFound:
        st.error("❌ Tab 'Master_Siswa' tidak ditemukan! Pastikan nama tab di Google Sheets ditulis persis 'Master_Siswa'.")
        return {}
    except Exception as e:
        st.error(f"❌ Gagal memuat data master: {e}")
        return {}

# Panggil fungsi untuk mengambil daftar kelas dan siswa secara otomatis
data_kelas = muat_data_master()

# ==========================================
# 3. ANTARMUKA (UI) APLIKASI STREAMLIT
# ==========================================
st.set_page_config(page_title="Rekap Mingguan Presensi", layout="wide")
st.title("📊 Aplikasi Rekap Presensi Siswa (Mingguan)")
st.write("Aplikasi otomatis menarik data siswa dari Google Sheets dan mencatat akumulasi ketidakhadiran.")

# Cek apakah data master berhasil dimuat
if not data_kelas:
    st.warning("Aplikasi belum bisa berjalan. Silakan periksa kembali struktur tab 'Master_Siswa' di Google Sheets Anda.")
else:
    # Baris Input Informasi Minggu dan Pilihan Kelas
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        minggu_ke = st.text_input("Rekap untuk Minggu Ke- (Contoh: Minggu 1)", placeholder="Misal: Minggu 1")
    with col_info2:
        kelas_terpilih = st.selectbox("Pilih Kelas", list(data_kelas.keys()))

    st.divider()

    # Ambil daftar siswa berdasarkan kelas yang sedang dipilih guru
    daftar_siswa = data_kelas[kelas_terpilih]
    st.subheader(f"Input Rekap Kelas: {kelas_terpilih} ({len(daftar_siswa)} Siswa)")

    # Tempat menampung input angka jumlah kehadiran sementara di memori
    rekap_input = {}

    # Menggunakan st.form agar halaman tidak memuat ulang (reload) setiap kali angka diubah
    with st.form("form_rekap_mingguan"):
        
        # Membuat judul kolom agar tampilan form rapi berbentuk tabel/grid
        h_col1, h_col2, h_col3, h_col4 = st.columns([3, 1, 1, 1])
        h_col1.markdown("**Nama Siswa**")
        h_col2.markdown("**Sakit (Hari)**")
        h_col3.markdown("**Izin (Hari)**")
        h_col4.markdown("**Alpha (Hari)**")
        st.write("---")

        # Loop untuk memunculkan baris input bagi setiap siswa di kelas tersebut
        for siswa in daftar_siswa:
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            with c1:
                st.write(siswa)
            with c2:
                sakit = st.number_input(f"Sakit_{siswa}", min_value=0, max_value=7, step=1, label_visibility="collapsed")
            with c3:
                izin = st.number_input(f"Izin_{siswa}", min_value=0, max_value=7, step=1, label_visibility="collapsed")
            with c4:
                alpha = st.number_input(f"Alpha_{siswa}", min_value=0, max_value=7, step=1, label_visibility="collapsed")
            
            # Simpan nilai angka yang diinput ke dalam dictionary penampung
            rekap_input[siswa] = {"sakit": sakit, "izin": izin, "alpha": alpha}
        
        st.write("---")
        tombol_simpan = st.form_submit_button("Simpan Rekap Mingguan")

    # ==========================================
    # 4. PROSES VALIDASI & PENYIMPANAN DATA DATA
    # ==========================================
    if tombol_simpan:
        if not minggu_ke.strip():
            st.error("⚠️ Harap isi informasi 'Minggu Ke-' terlebih dahulu sebelum menekan tombol simpan!")
        else:
            try:
                # Menentukan nama tab tujuan rekap berdasarkan pilihan kelas (Contoh: 'Rekap_X-RPL')
                nama_tab_tujuan = f"Rekap_{kelas_terpilih}"
                worksheet_tujuan = sh.worksheet(nama_tab_tujuan)
                
                # --- VALIDASI PENCEGAHAN DATA GANDA ---
                # Membaca seluruh isi kolom A (kolom Minggu Ke) pada tab tujuan
                riwayat_minggu = worksheet_tujuan.col_values(1)
                
                # Standardisasi teks (hapus spasi berlebih dan jadikan huruf kecil) agar pengecekan akurat
                minggu_input_bersih = minggu_ke.strip().lower()
                daftar_minggu_terinput = [m.strip().lower() for m in riwayat_minggu]
                
                # Periksa apakah teks minggu tersebut sudah pernah ada di Google Sheets
                if minggu_input_bersih in daftar_minggu_terinput:
                    st.error(f"⚠️ Gagal Menyimpan! Rekap data untuk '**{minggu_ke}**' pada kelas **{kelas_terpilih}** sudah pernah dimasukkan sebelumnya.")
                else:
                    # --- PROSES SIMPAN MASSAL (BULK INSERT) ---
                    rows_to_insert = []
                    for siswa, data in rekap_input.items():
                        rows_to_insert.append([
                            minggu_ke.strip(), 
                            siswa, 
                            data["sakit"], 
                            data["izin"], 
                            data["alpha"]
                        ])
                    
                    # Kirim seluruh baris data siswa sekaligus ke baris terbawah Google Sheets
                    worksheet_tujuan.append_rows(rows_to_insert)
                    st.success(f"✅ Berhasil! Rekap mingguan kelas {kelas_terpilih} aman disimpan ke tab '{nama_tab_tujuan}'.")
                
            except gspread.exceptions.WorksheetNotFound:
                st.error(f"❌ Gagal Menyimpan! Tab dengan nama '{nama_tab_tujuan}' belum dibuat di Google Sheets Anda. Silakan buat tab baru dengan nama tersebut terlebih dahulu.")
            except Exception as e:
                st.error(f"❌ Terjadi gangguan sistem saat menyimpan data: {e}")
