import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import io
from fpdf import FPDF
import os

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Portale Flotta PC Basilicata", layout="wide", page_icon="🚒")
WEBAPP_URL = st.secrets["url_foglio"]
LOGO_PATH = "logo.png"

# --- LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("Protezione Civile Basilicata - Accesso")
        if os.path.exists(LOGO_PATH): st.image(LOGO_PATH, width=150)
        pwd = st.text_input("Inserisci la password di accesso:", type="password")
        if st.button("Accedi"):
            if pwd == st.secrets["password"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Password errata")
        return False
    return True

if check_password():
    # --- FUNZIONI DI COMUNICAZIONE ---
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
            st.error(f"Errore di sincronizzazione: {e}")
            return None

    # --- CARICAMENTO DATI ---
    df_mezzi = gsheet_action("read", "Mezzi")
    
    # Pulizia date se il dataframe non è vuoto
    if df_mezzi is not None and not df_mezzi.empty:
        df_mezzi['scadenza_assicurazione'] = pd.to_datetime(df_mezzi['scadenza_assicurazione'], errors='coerce')
        df_mezzi['scadenza_revisione'] = pd.to_datetime(df_mezzi['scadenza_revisione'], errors='coerce')

    # --- SIDEBAR ---
    with st.sidebar:
        if os.path.exists(LOGO_PATH): st.image(LOGO_PATH, width=130)
        st.title("Menu Gestione")
        menu = st.radio("Vai a:", ["Dashboard Alert", "Caricamento (Singolo/Massivo)", "Verifica Portali", "Storico"])
        st.divider()
        if st.button("Disconnetti"):
            del st.session_state["password_correct"]
            st.rerun()

    # --- 1. DASHBOARD ALERT ---
    if menu == "Dashboard Alert":
        st.header("🚒 Stato Flotta e Alert Scadenze")
        
        if df_mezzi is None or df_mezzi.empty:
            st.info("Nessun mezzo registrato nel database cloud.")
        else:
            oggi = pd.to_datetime(datetime.now().date())
            soglia = oggi + timedelta(days=30)
            
            # Filtri Alert
            alert_ass = df_mezzi[df_mezzi['scadenza_assicurazione'] <= soglia]
            alert_rev = df_mezzi[df_mezzi['scadenza_revisione'] <= soglia]
            
            # Metriche
            m1, m2, m3 = st.columns(3)
            m1.metric("Mezzi Totali", len(df_mezzi))
            m2.metric("Scadenze Assicurazione", len(alert_ass), delta_color="inverse")
            m3.metric("Scadenze Revisione", len(alert_rev), delta_color="inverse")
            
            # Tabella Alert
            if not alert_ass.empty or not alert_rev.empty:
                st.subheader("⚠️ Mezzi in scadenza (prossimi 30 giorni)")
                tab_ass, tab_rev = st.tabs(["Assicurazioni", "Revisioni"])
                with tab_ass:
                    st.dataframe(alert_ass, use_container_width=True)
                with tab_rev:
                    st.dataframe(alert_rev, use_container_width=True)
            else:
                st.success("Tutti i mezzi sono in regola.")
            
            st.divider()
            st.subheader("Elenco Completo Mezzi")
            st.dataframe(df_mezzi, use_container_width=True)

    # --- 2. CARICAMENTO (SINGOLO E MASSIVO) ---
    elif menu == "Caricamento (Singolo/Massivo)":
        st.header("📥 Inserimento Dati")
        
        tab_s, tab_m = st.tabs(["Inserimento Singolo", "Caricamento da Excel"])
        
        with tab_s:
            with st.form("form_singolo"):
                c1, c2 = st.columns(2)
                targa = c1.text_input("Targa").upper().strip()
                ass = c1.text_input("Associazione")
                tipo = c1.selectbox("Tipo", ["Pick-up AIB", "Autovettura", "Autobotte", "Altro"])
                s_ass = c2.date_input("Scadenza Assicurazione")
                s_rev = c2.date_input("Scadenza Revisione")
                conv = c2.selectbox("Convenzione Pagamento", ["AIB", "Annuale"])
                
                if st.form_submit_button("Salva nel Cloud"):
                    riga = [targa, tipo, ass, str(s_ass), str(s_rev), conv]
                    gsheet_action("upsert", "Mezzi", riga)
                    st.success(f"Mezzo {targa} salvato correttamente!")
                    st.rerun()

        with tab_m:
            st.write("Carica un file Excel con le colonne: `targa`, `tipo`, `associazione`, `scadenza_assicurazione`, `scadenza_revisione`, `convenzione_pagamento_ass`")
            file_ex = st.file_uploader("Scegli file Excel", type="xlsx")
            if file_ex:
                df_import = pd.read_excel(file_ex)
                st.dataframe(df_import.head())
                if st.button("Conferma Importazione Massiva"):
                    progress = st.progress(0)
                    for i, row in df_import.iterrows():
                        riga = [str(row['targa']).upper(), row['tipo'], row['associazione'], 
                                str(row['scadenza_assicurazione']), str(row['scadenza_revisione']), row['convenzione_pagamento_ass']]
                        gsheet_action("upsert", "Mezzi", riga)
                        progress.progress((i + 1) / len(df_import))
                    st.success("Tutti i dati sono stati sincronizzati sul Cloud!")
                    st.rerun()

    # --- 3. VERIFICA PORTALI ---
    elif menu == "Verifica Portali":
        st.header("🔍 Verifica Esterna")
        targa_v = st.text_input("Inserisci Targa").upper()
        if targa_v:
            col1, col2 = st.columns(2)
            col1.link_button("Verifica Revisione (Ministero)", "https://www.ilportaledellautomobilista.it/web/portale-automobilista/verifica-ultima-revisione")
            col2.link_button("Verifica RCA (Consap)", f"https://www.consap.it/servizi-assicurativi/fondo-di-garanzia-per-le-vittime-della-strada/controlla-il-veicolo-estero/?targa={targa_v}")

    # --- 4. STORICO ---
    elif menu == "Storico":
        st.header("📜 Cronologia")
        df_storico = gsheet_action("read", "Storico")
        if df_storico is not None and not df_storico.empty:
            st.dataframe(df_storico, use_container_width=True)
        else:
            st.info("Nessun dato storico presente.")
