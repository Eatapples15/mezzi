import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import io
from fpdf import FPDF
import os

# --- 1. CONFIGURAZIONE E PASSWORD ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("Accesso Riservato - Protezione Civile")
        st.text_input("Password di sistema:", type="password", on_change=password_entered, key="password")
        return False
    return st.session_state["password_correct"]

if check_password():
    # --- CONFIGURAZIONE ---
    WEBAPP_URL = st.secrets["url_foglio"]
    LOGO_PATH = "logo.png"
    st.set_page_config(page_title="Gestione Flotta PC", layout="wide")

    # --- FUNZIONI COMUNICAZIONE GOOGLE ---
    def gsheet_action(action, sheet_name, data=None):
        payload = {"action": action, "sheet": sheet_name, "data": data}
        try:
            # Seguiamo i redirect perché Google Apps Script reindirizza le POST
            response = requests.post(WEBAPP_URL, data=json.dumps(payload), timeout=10)
            if action == "read":
                raw_data = response.json()
                if len(raw_data) > 1:
                    return pd.DataFrame(raw_data[1:], columns=raw_data[0])
                return pd.DataFrame(columns=raw_data[0])
            return response.text
        except Exception as e:
            st.error(f"Errore di connessione al Cloud: {e}")
            return None

    # --- LOGICA APPLICATIVA ---
    df_mezzi = gsheet_action("read", "Mezzi")

    with st.sidebar:
        if os.path.exists(LOGO_PATH): st.image(LOGO_PATH, width=130)
        menu = st.radio("Menu:", ["Monitoraggio", "Inserimento/Verifica", "Storico"])
        if st.button("Disconnetti"):
            st.session_state["password_correct"] = False
            st.rerun()

    # --- 1. MONITORAGGIO ---
    if menu == "Monitoraggio":
        st.title("🚒 Dashboard Flotta Regionale")
        if df_mezzi is not None and not df_mezzi.empty:
            df_mezzi['scadenza_assicurazione'] = pd.to_datetime(df_mezzi['scadenza_assicurazione'])
            # Visualizzazione Alert...
            st.dataframe(df_mezzi, use_container_width=True)
        else:
            st.info("Nessun dato trovato nel foglio Google.")

    # --- 2. INSERIMENTO ---
    elif menu == "Inserimento/Verifica":
        st.title("📝 Registrazione Mezzo")
        with st.form("nuovo_mezzo"):
            c1, c2 = st.columns(2)
            targa = c1.text_input("Targa").upper()
            ass = c1.text_input("Associazione")
            scad_ass = c2.date_input("Scadenza Assicurazione")
            scad_rev = c2.date_input("Scadenza Revisione")
            conv = c2.selectbox("Convenzione", ["AIB", "Annuale"])
            
            if st.form_submit_button("Invia al Cloud"):
                dati_riga = [targa, "Mezzo", ass, str(scad_ass), str(scad_rev), conv]
                res = gsheet_action("upsert", "Mezzi", dati_riga)
                if res:
                    st.success("Dati salvati nel Foglio Google!")
