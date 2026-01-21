import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io
from fpdf import FPDF
import os

# --- 1. PROTEZIONE CON PASSWORD ---
def check_password():
    """Restituisce True se l'utente ha inserito la password corretta."""

    def password_entered():
        """Controlla se la password inserita corrisponde a quella nei Secrets."""
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Rimuove la password dallo stato per sicurezza
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # Visualizzazione form di login
        st.title("Accesso Riservato")
        st.image("logo.png", width=150) if os.path.exists("logo.png") else None
        st.text_input("Inserisci la password per accedere al database flotta:", 
                      type="password", on_change=password_entered, key="password")
        if "password_correct" in st.session_state:
            st.error("😕 Password errata")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password errata")
        return False
    else:
        return True

# --- ESECUZIONE LOGIN ---
if check_password():
    # Se la password è corretta, il resto del codice viene eseguito

    # Configurazione Pagina (Va spostata qui se non presente prima)
    st.set_page_config(page_title="PC Basilicata - Gestione Flotta", layout="wide", page_icon="🚒")

    # --- COSTANTI E LOGO ---
    LOGO_PATH = "logo.png"

    # --- DATABASE SETUP ---
    def init_db():
        conn = sqlite3.connect('flotta_pc_basilicata.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS mezzi (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        targa TEXT UNIQUE, tipo TEXT, tipologia TEXT, associazione TEXT,
                        sede TEXT, convenzione_attivabile TEXT, scadenza_assicurazione DATE,
                        scadenza_revisione DATE, convenzione_pagamento_ass TEXT
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS storico (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, targa TEXT, evento TEXT,
                        data_evento DATE, dettagli TEXT, convenzione_rif TEXT
                    )''')
        conn.commit()
        conn.close()

    def log_storico(targa, evento, dettagli, conv):
        conn = sqlite3.connect('flotta_pc_basilicata.db')
        c = conn.cursor()
        c.execute("INSERT INTO storico (targa, evento, data_evento, dettagli, convenzione_rif) VALUES (?,?,?,?,?)",
                  (targa.upper(), evento, datetime.now().date(), dettagli, conv))
        conn.commit()
        conn.close()

    def save_to_db(df):
        conn = sqlite3.connect('flotta_pc_basilicata.db')
        for _, row in df.iterrows():
            c = conn.cursor()
            c.execute('''INSERT INTO mezzi (targa, tipo, tipologia, associazione, sede, 
                         convenzione_attivabile, scadenza_assicurazione, scadenza_revisione, convenzione_pagamento_ass)
                         VALUES (?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(targa) DO UPDATE SET
                         scadenza_assicurazione=excluded.scadenza_assicurazione,
                         scadenza_revisione=excluded.scadenza_revisione,
                         convenzione_pagamento_ass=excluded.convenzione_pagamento_ass''', 
                      (str(row['targa']).upper(), row['tipo'], row['tipologia'], row['associazione'], row['sede'], 
                       row['convenzione_attivabile'], row['scadenza_assicurazione'], row['scadenza_revisione'], row['convenzione_pagamento_ass']))
            log_storico(row['targa'], "Aggiornamento/Import", "Dati salvati nel database", row['convenzione_pagamento_ass'])
        conn.commit()
        conn.close()

    def load_data(table="mezzi"):
        conn = sqlite3.connect('flotta_pc_basilicata.db')
        df = pd.read_sql(f'SELECT * FROM {table}', conn)
        conn.close()
        if not df.empty and 'scadenza_assicurazione' in df.columns:
            df['scadenza_assicurazione'] = pd.to_datetime(df['scadenza_assicurazione'], errors='coerce')
            df['scadenza_revisione'] = pd.to_datetime(df['scadenza_revisione'], errors='coerce')
        return df

    # --- FUNZIONI PDF ---
    class PC_Report(FPDF):
        def header(self):
            if os.path.exists(LOGO_PATH): self.image(LOGO_PATH, 10, 8, 25)
            self.set_font('Arial', 'B', 12)
            self.set_y(12)
            self.cell(0, 10, 'Regione Basilicata - Protezione Civile', 0, 1, 'C')
            self.ln(10)

    def export_pdf(df, titolo):
        pdf = PC_Report()
        pdf.add_page()
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 10, titolo, 0, 1, 'L', fill=True)
        pdf.ln(5)
        pdf.set_font("Arial", "B", 8)
        for col in ["Targa", "Associazione", "Scadenza", "Convenzione"]:
            pdf.cell(45, 8, col, 1, 0, 'C')
        pdf.ln()
        pdf.set_font("Arial", "", 8)
        for _, row in df.iterrows():
            pdf.cell(45, 8, str(row['targa']), 1)
            pdf.cell(45, 8, str(row['associazione'])[:25], 1)
            pdf.cell(45, 8, row['scadenza_assicurazione'].strftime('%d/%m/%Y'), 1)
            pdf.cell(45, 8, str(row['convenzione_attivabile']), 1)
            pdf.ln()
        return pdf.output()

    # --- INTERFACCIA ---
    init_db()
    df_mezzi = load_data("mezzi")

    with st.sidebar:
        if os.path.exists(LOGO_PATH): st.image(LOGO_PATH, width=130)
        st.title("P.C. Basilicata")
        menu = st.radio("Menu principale:", ["Dashboard Alert", "Gestione & Verifica", "Storico & Excel"])
        if st.button("Esci / Log out"):
            st.session_state["password_correct"] = False
            st.rerun()

    # --- 1. DASHBOARD ---
    if menu == "Dashboard Alert":
        st.title("🚒 Monitoraggio Scadenze Flotta")
        if df_mezzi.empty:
            st.info("Nessun mezzo in archivio.")
        else:
            oggi = pd.to_datetime(datetime.now().date())
            soglia = oggi + timedelta(days=30)
            
            scad_ass = df_mezzi[df_mezzi['scadenza_assicurazione'] <= soglia]
            scad_rev = df_mezzi[df_mezzi['scadenza_revisione'] <= soglia]
            duplicati = df_mezzi[df_mezzi.duplicated('targa', keep=False)]

            c1, c2, c3 = st.columns(3)
            c1.metric("Totale Mezzi", len(df_mezzi))
            c2.metric("Assicurazioni Alert", len(scad_ass), delta_color="inverse")
            c3.metric("Conflitti Targa", len(duplicati['targa'].unique()), delta_color="inverse")

            if not scad_ass.empty:
                st.warning("⚠️ Assicurazioni in scadenza")
                st.dataframe(scad_ass[['targa', 'associazione', 'scadenza_assicurazione']], use_container_width=True)
                pdf_ass = export_pdf(scad_ass, "REPORT SCADENZE ASSICURATIVE")
                st.download_button("🖨️ Esporta PDF Assicurazioni", pdf_ass, "alert_assicurazioni.pdf")

            if not scad_rev.empty:
                st.error("🛠️ Revisioni in scadenza")
                st.dataframe(scad_rev[['targa', 'associazione', 'scadenza_revisione']], use_container_width=True)

    # --- 2. GESTIONE & VERIFICA ---
    elif menu == "Gestione & Verifica":
        st.title("📝 Verifica e Aggiornamento Mezzi")
        tab1, tab2 = st.tabs(["Inserimento/Aggiornamento", "Verifica Rapida Portali"])
        
        with tab1:
            with st.form("form_mezzo", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    targa = st.text_input("Targa *").upper().strip()
                    ass = st.text_input("Associazione *")
                    tipo = st.selectbox("Tipo", ["Pick-up AIB", "Autovettura", "Autobotte", "Modulo Rimorchio"])
                with col2:
                    s_ass = st.date_input("Nuova Scadenza Assicurazione")
                    s_rev = st.date_input("Nuova Scadenza Revisione")
                    conv = st.selectbox("Pagata con Convenzione:", ["AIB", "Annuale", "Extra"])
                if st.form_submit_button("💾 Salva e Storicizza"):
                    if targa and ass:
                        nuovo = pd.DataFrame([{
                            'targa': targa, 'tipo': tipo, 'tipologia': '', 'associazione': ass, 'sede': '',
                            'convenzione_attivabile': conv, 'scadenza_assicurazione': s_ass,
                            'scadenza_revisione': s_rev, 'convenzione_pagamento_ass': conv
                        }])
                        save_to_db(nuovo)
                        st.success(f"Dati per {targa} salvati!")
                        st.rerun()

        with tab2:
            st.subheader("🔍 Strumenti di verifica esterna gratuita")
            targa_v = st.text_input("Inserisci targa da controllare:").upper().strip()
            if targa_v:
                v1, v2 = st.columns(2)
                url_rev = "https://www.ilportaledellautomobilista.it/web/portale-automobilista/verifica-ultima-revisione"
                v1.link_button("🛠️ Verifica Ultima Revisione", url_rev)
                url_ass = "https://www.ilportaledellautomobilista.it/web/portale-automobilista/verifica-copertura-rc"
                v2.link_button("🛡️ Verifica Copertura RCA", url_ass)

    # --- 3. STORICO & EXCEL ---
    elif menu == "Storico & Excel":
        st.title("📊 Dati Massivi e Cronologia")
        up_col, down_col = st.columns(2)
        with up_col:
            uploaded = st.file_uploader("Carica Excel Flotta", type="xlsx")
            if uploaded:
                if st.button("Importa tutto"):
                    df_ex = pd.read_excel(uploaded)
                    save_to_db(df_ex)
                    st.success("Importazione completata!")
        with down_col:
            if st.button("Genera Excel Completo"):
                df_full = load_data("mezzi")
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_full.to_excel(writer, index=False)
                st.download_button("📥 Scarica Database Excel", output.getvalue(), "db_flotta_pc.xlsx")
        st.divider()
        targa_h = st.text_input("Targa da ricercare:").upper()
        if targa_h:
            hist = load_data("storico")
            res = hist[hist['targa'] == targa_h].sort_values('data_evento', ascending=False)
            st.table(res[['data_evento', 'evento', 'dettagli', 'convenzione_rif']])
