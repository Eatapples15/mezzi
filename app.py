import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import io
from fpdf import FPDF
import os

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Portale Flotta PC Basilicata", layout="wide", page_icon="🚒")

# --- RECUPERO SEGRETI ---
# Assicurati che questi siano impostati correttamente nei Secrets di Streamlit Cloud
WEBAPP_URL = st.secrets["url_foglio"]
PASSWORD_SISTEMA = st.secrets["password"]
LOGO_PATH = "logo.png"

# --- FUNZIONE DI AUTENTICAZIONE ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("Protezione Civile Basilicata - Accesso Riservato")
        if os.path.exists(LOGO_PATH): 
            st.image(LOGO_PATH, width=150)
        
        pwd = st.text_input("Inserisci la password di sistema:", type="password")
        if st.button("Accedi"):
            if pwd == PASSWORD_SISTEMA:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("🚫 Password errata. Riprova.")
        return False
    return True

# Se l'utente è autenticato, esegui l'app
if check_password():

    # --- FUNZIONI DI COMUNICAZIONE CLOUD (Google Apps Script) ---
    def gsheet_action(action, sheet_name, data=None):
        payload = {"action": action, "sheet": sheet_name, "data": data}
        try:
            response = requests.post(WEBAPP_URL, data=json.dumps(payload), timeout=15)
            if action == "read":
                raw_data = response.json()
                if len(raw_data) > 1:
                    return pd.DataFrame(raw_data[1:], columns=raw_data[0])
                return pd.DataFrame(columns=raw_data[0] if raw_data else [])
            return response.text
        except Exception as e:
            st.error(f"⚠️ Errore di sincronizzazione Cloud: {e}")
            return None

    # --- CARICAMENTO E PULIZIA DATI ---
    @st.cache_data(ttl=60)
    def get_fleet_data():
        df = gsheet_action("read", "Mezzi")
        if df is not None and not df.empty:
            # NORMALIZZAZIONE DATE: Forziamo il formato datetime64[ns] di Pandas
            df['scadenza_assicurazione'] = pd.to_datetime(df['scadenza_assicurazione'], errors='coerce')
            df['scadenza_revisione'] = pd.to_datetime(df['scadenza_revisione'], errors='coerce')
            
            # Pulizia stringhe
            df['targa'] = df['targa'].astype(str).str.upper().str.strip()
            df['associazione'] = df['associazione'].astype(str).str.strip()
            df['sede'] = df['sede'].astype(str).str.strip()
            
            # Rimuoviamo eventuali righe completamente vuote
            df = df.dropna(subset=['targa'])
        return df

    df_mezzi = get_fleet_data()

    # --- SIDEBAR ---
    with st.sidebar:
        if os.path.exists(LOGO_PATH): 
            st.image(LOGO_PATH, width=130)
        st.title("Gestione Flotta")
        menu = st.radio("Seleziona Modulo:", 
                        ["Dashboard & Ricerca", "Caricamento Mezzi", "Verifica Portali Esterni", "Storico"])
        st.divider()
        if st.button("Esci dal Sistema"):
            del st.session_state["password_correct"]
            st.rerun()

    # --- 1. DASHBOARD & RICERCA AVANZATA ---
    if menu == "Dashboard & Ricerca":
        st.header("🚒 Dashboard Monitoraggio Flotta")
        
        if df_mezzi is None or df_mezzi.empty:
            st.info("Il database è vuoto. Carica dei dati per iniziare.")
        else:
            # FILTRI DI RICERCA
            with st.expander("🔍 Filtri di Ricerca Avanzata", expanded=True):
                c_search1, c_search2, c_search3 = st.columns(3)
                search_targa = c_search1.text_input("Cerca per Targa").upper()
                search_ass = c_search2.text_input("Cerca per Associazione")
                search_sede = c_search3.text_input("Cerca per Sede (Comune)")

            # Applicazione Filtri
            df_filtrato = df_mezzi.copy()
            if search_targa:
                df_filtrato = df_filtrato[df_filtrato['targa'].str.contains(search_targa, na=False)]
            if search_ass:
                df_filtrato = df_filtrato[df_filtrato['associazione'].str.contains(search_ass, case=False, na=False)]
            if search_sede:
                df_filtrato = df_filtrato[df_filtrato['sede'].str.contains(search_sede, case=False, na=False)]

            # --- LOGICA ALERT (FIX TYPE ERROR) ---
            # Usiamo pd.Timestamp per garantire la compatibilità con il dtype della colonna
            oggi = pd.Timestamp(datetime.now().date())
            soglia = oggi + pd.Timedelta(days=30)
            
            # Filtriamo assicurazioni e revisioni (escludendo i valori non validi NaT)
            mask_ass = df_filtrato['scadenza_assicurazione'].notna()
            alert_ass = df_filtrato[mask_ass & (df_filtrato['scadenza_assicurazione'] <= soglia)]
            
            mask_rev = df_filtrato['scadenza_revisione'].notna()
            alert_rev = df_filtrato[mask_rev & (df_filtrato['scadenza_revisione'] <= soglia)]
            
            # METRICHE
            m1, m2, m3 = st.columns(3)
            m1.metric("Mezzi Totali", len(df_filtrato))
            m2.metric("Alert Assicurazione", len(alert_ass), delta_color="inverse")
            m3.metric("Alert Revisione", len(alert_rev), delta_color="inverse")

            # TABELLE ALERT
            if not alert_ass.empty or not alert_rev.empty:
                st.subheader("⚠️ Scadenze Imminenti (30 giorni)")
                col_a, col_b = st.columns(2)
                with col_a:
                    if not alert_ass.empty:
                        st.error("Assicurazioni in scadenza:")
                        st.dataframe(alert_ass[['targa', 'associazione', 'scadenza_assicurazione', 'sede']].sort_values('scadenza_assicurazione'), use_container_width=True)
                with col_b:
                    if not alert_rev.empty:
                        st.warning("Revisioni in scadenza:")
                        st.dataframe(alert_rev[['targa', 'associazione', 'scadenza_revisione', 'sede']].sort_values('scadenza_revisione'), use_container_width=True)
            
            st.divider()
            st.subheader("Elenco Completo")
            # Mostriamo le date in formato leggibile italiano
            df_display = df_filtrato.copy()
            df_display['scadenza_assicurazione'] = df_display['scadenza_assicurazione'].dt.strftime('%d/%m/%Y')
            df_display['scadenza_revisione'] = df_display['scadenza_revisione'].dt.strftime('%d/%m/%Y')
            st.dataframe(df_display, use_container_width=True, hide_index=True)

    # --- 2. CARICAMENTO MEZZI ---
    elif menu == "Caricamento Mezzi":
        st.header("📥 Inserimento Dati Cloud")
        
        t1, t2 = st.tabs(["Inserimento Singolo", "Caricamento Massivo (Excel)"])
        
        with t1:
            with st.form("nuovo_mezzo", clear_on_submit=True):
                c1, c2 = st.columns(2)
                targa_in = c1.text_input("Targa *").upper().strip()
                tipo_in = c1.selectbox("Tipo Mezzo", ["Autocarro", "Pick-up", "Autovettura", "Modulo AIB", "Altro"])
                tipol_in = c1.text_input("Tipologia/Allestimento")
                ass_in = c1.text_input("Associazione Proprietaria *")
                sede_in = c2.text_input("Sede Operativa (Comune) *")
                scad_ass_in = c2.date_input("Scadenza Assicurazione")
                scad_rev_in = c2.date_input("Scadenza Revisione")
                conv_in = c2.selectbox("Convenzione Pagamento", ["AIB", "Annuale", "Extra"])
                
                if st.form_submit_button("Salva nel Foglio Google"):
                    if targa_in and ass_in and sede_in:
                        riga = [targa_in, tipo_in, tipol_in, ass_in, sede_in, str(scad_ass_in), str(scad_rev_in), conv_in]
                        gsheet_action("upsert", "Mezzi", riga)
                        st.success(f"✅ Mezzo {targa_in} sincronizzato!")
                        st.cache_data.clear()
                    else:
                        st.error("I campi con * sono obbligatori.")

        with t2:
            st.write("Scarica il template o carica il tuo file Excel.")
            file_ex = st.file_uploader("Scegli file Excel", type="xlsx")
            if file_ex:
                df_ex = pd.read_excel(file_ex)
                if st.button("Esegui Caricamento Massivo"):
                    bar = st.progress(0)
                    for i, row in df_ex.iterrows():
                        riga = [
                            str(row['targa']).upper().strip(), str(row['tipo']), str(row['tipologia']),
                            str(row['associazione']), str(row['sede']),
                            str(pd.to_datetime(row['scadenza_assicurazione']).date()),
                            str(pd.to_datetime(row['scadenza_revisione']).date()),
                            str(row['convenzione_pagamento_ass'])
                        ]
                        gsheet_action("upsert", "Mezzi", riga)
                        bar.progress((i + 1) / len(df_ex))
                    st.success("Sincronizzazione completata!")
                    st.cache_data.clear()

    # --- 3. VERIFICA PORTALI ESTERNI ---
    elif menu == "Verifica Portali Esterni":
        st.header("🔍 Verifica Documentale")
        t_check = st.text_input("Targa da controllare:").upper()
        if t_check:
            c1, c2 = st.columns(2)
            c1.link_button("🛠️ Verifica Revisione (Portale Automobilista)", 
                           "https://www.ilportaledellautomobilista.it/web/portale-automobilista/verifica-ultima-revisione")
            c2.link_button("🛡️ Verifica Assicurazione (Consap)", 
                           f"https://www.consap.it/servizi-assicurativi/fondo-di-garanzia-per-le-vittime-della-strada/controlla-il-veicolo-estero/?targa={t_check}")

    # --- 4. STORICO ---
    elif menu == "Storico":
        st.header("📜 Log Operazioni")
        df_hist = gsheet_action("read", "Storico")
        if df_hist is not None and not df_hist.empty:
            st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("Storico non disponibile.")
