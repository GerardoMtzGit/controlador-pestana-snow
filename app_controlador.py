"""
app_controlador.py
Interfaz interactiva y clara para seleccionar y controlar pestañas de ServiceNow.
Incluye:
- Retraso inteligente de 10 segundos con barra de progreso visual al abrir ticket para permitir carga completa de ServiceNow.
- Apertura garantizada en un solo disparo.
- Botón destacado '🔙 Regresar a la Lista de Tickets'.
- Actualización sincronizada de la vista espejo.
"""

import os
import time
import subprocess
from io import BytesIO
from PIL import Image
import pandas as pd
import streamlit as st
from tab_engine import CDPBrowserController, TabInfo
from agent_bridge import HuggingFaceTabAgent
from similarity_engine import HistoricalCSVAnalyzer, LocalGemmaClient


st.set_page_config(
    page_title="Controlador de Pestañas ServiceNow",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar sesión persistente
if "controller" not in st.session_state:
    st.session_state.controller = CDPBrowserController()

if "agent" not in st.session_state:
    st.session_state.agent = HuggingFaceTabAgent(mode="local_rules")

if "selected_tab_id" not in st.session_state:
    st.session_state.selected_tab_id = None

if "selected_tab_title" not in st.session_state:
    st.session_state.selected_tab_title = ""

if "last_action_msg" not in st.session_state:
    st.session_state.last_action_msg = "Listo para operar"

if "last_frame" not in st.session_state:
    st.session_state.last_frame = None

if "detected_tickets" not in st.session_state:
    st.session_state.detected_tickets = []

if "queue_summary_text" not in st.session_state:
    st.session_state.queue_summary_text = ""

if "last_scan_logs" not in st.session_state:
    st.session_state.last_scan_logs = []

if "show_more_tickets" not in st.session_state:
    st.session_state.show_more_tickets = False

if "extracted_ticket_data" not in st.session_state:
    st.session_state.extracted_ticket_data = {}

if "saved_tickets_list" not in st.session_state:
    st.session_state.saved_tickets_list = []

if "similarity_analyzer" not in st.session_state:
    st.session_state.similarity_analyzer = HistoricalCSVAnalyzer()

if "similarity_results" not in st.session_state:
    st.session_state.similarity_results = None

if "csv_status_msg" not in st.session_state:
    st.session_state.csv_status_msg = ""

controller: CDPBrowserController = st.session_state.controller
agent: HuggingFaceTabAgent = st.session_state.agent

# Estilos CSS
st.markdown("""
<style>
    .se-banner {
        background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
        padding: 16px 22px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
        border-left: 5px solid #009530;
    }
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-ok { background: #dcfce7; color: #166534; }
    .badge-warn { background: #fef3c7; color: #92400e; }
    .snow-tab-card {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .ticket-box {
        background: #ffffff;
        border: 1.5px solid #cbd5e1;
        border-left: 4px solid #009530;
        padding: 12px 14px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .queue-counter-banner {
        background: #0f172a;
        color: #38bdf8;
        padding: 10px 14px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 0.95rem;
        border: 1px solid #1e293b;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# Banner Principal
st.markdown("""
<div class="se-banner">
    <h2 style="margin:0; font-size:1.4rem; font-weight:700;">⚡ Controlador Directo de Pestaña ServiceNow</h2>
    <p style="margin:4px 0 0 0; font-size:0.88rem; color:#cbd5e1;">
        Paso 2: Apertura en 1 solo disparo, tiempo de espera calibrado (10s) para carga completa de ServiceNow y retorno a lista.
    </p>
</div>
""", unsafe_allow_html=True)


# ================= SIDEBAR: LISTA Y SELECCIÓN DE PESTAÑAS =================
with st.sidebar:
    st.header("📑 Selección de Pestaña")

    is_connected = controller.is_cdp_available()
    active_port = controller.active_port or 9222

    if is_connected:
        st.markdown(f'<span class="badge badge-ok">● Navegador Conectado (Puerto {active_port})</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge badge-warn">▲ Navegador no detectado</span>', unsafe_allow_html=True)
        st.warning(
            "Chrome no se inició con el puerto de depuración abierto. "
            "Haz clic en el botón de abajo para abrir una ventana lista para conectar:"
        )
        if st.button("🚀 Iniciar Navegador con Depuración", type="primary", use_container_width=True):
            try:
                subprocess.Popen(["cmd.exe", "/c", "iniciar_navegador_debug.bat"], shell=True)
                time.sleep(2.5)
                st.rerun()
            except Exception as e:
                st.error(f"Error al abrir: {e}")

    st.divider()

    tabs = controller.list_tabs() if is_connected else []

    if tabs:
        snow_tabs = [t for t in tabs if t.is_servicenow]

        # 1. BOTÓN DIRECTO SI HAY SERVICENOW DETECTADO
        if snow_tabs:
            st.markdown("##### 🟢 Pestaña de ServiceNow Detectada:")
            target_snow = snow_tabs[0]
            st.markdown(f"""
            <div class="snow-tab-card">
                <strong>🎫 {target_snow.title[:40]}</strong><br>
                <small style="color:#64748b;">{target_snow.url[:45]}...</small>
            </div>
            """, unsafe_allow_html=True)

            if st.button("👉 Conectar a esta pestaña de ServiceNow", type="primary", use_container_width=True):
                controller.select_tab_by_id(target_snow.tab_id)
                st.session_state.selected_tab_id = target_snow.tab_id
                st.session_state.selected_tab_title = target_snow.title
                st.session_state.last_action_msg = f"Enlazado a ServiceNow: {target_snow.title[:30]}"
                diag = controller.scan_tickets_with_diagnostics()
                st.session_state.detected_tickets = diag.get("tickets", [])
                st.session_state.queue_summary_text = diag.get("totalQueueText", "")
                st.session_state.last_scan_logs = diag.get("logs", [])
                st.session_state.last_frame = controller.take_screenshot()
                st.success("¡Pestaña de ServiceNow vinculada!")
                time.sleep(0.3)
                st.rerun()

            st.caption("O elige otra pestaña de la lista abajo:")

        # 2. SELECTOR GENERAL DE PESTAÑAS
        tab_display_names = {}
        for t in tabs:
            prefix = "🟢 [ServiceNow]" if t.is_servicenow else "🌐 [Web]"
            label = f"{prefix} {t.title[:35]} ({t.url[:25]}...)"
            tab_display_names[label] = (t.tab_id, t.title)

        selected_label = st.selectbox(
            "Selecciona cualquier pestaña:",
            options=list(tab_display_names.keys()),
            index=0
        )
        selected_id, selected_title = tab_display_names[selected_label]

        col_act1, col_act2 = st.columns([1, 1])
        with col_act1:
            if st.button("⚡ Enlazar", use_container_width=True):
                controller.select_tab_by_id(selected_id)
                st.session_state.selected_tab_id = selected_id
                st.session_state.selected_tab_title = selected_title
                st.session_state.last_action_msg = f"Enlazado a: {selected_title[:30]}"
                diag = controller.scan_tickets_with_diagnostics()
                st.session_state.detected_tickets = diag.get("tickets", [])
                st.session_state.queue_summary_text = diag.get("totalQueueText", "")
                st.session_state.last_scan_logs = diag.get("logs", [])
                st.session_state.last_frame = controller.take_screenshot()
                st.success("¡Pestaña enlazada!")
                time.sleep(0.3)
                st.rerun()
        with col_act2:
            if st.button("🔄 Refrescar", use_container_width=True):
                if st.session_state.selected_tab_id:
                    diag = controller.scan_tickets_with_diagnostics()
                    st.session_state.detected_tickets = diag.get("tickets", [])
                    st.session_state.queue_summary_text = diag.get("totalQueueText", "")
                    st.session_state.last_scan_logs = diag.get("logs", [])
                    st.session_state.last_frame = controller.take_screenshot()
                st.rerun()

    else:
        if is_connected:
            st.info("No hay pestañas tipo página abiertas. Abre tu pestaña de ServiceNow y pulsa 'Refrescar'.")
            if st.button("🔄 Refrescar Lista", use_container_width=True):
                st.rerun()
        else:
            st.caption("Abre el navegador con el botón superior para mostrar las pestañas.")


# ================= PANEL PRINCIPAL: CONTROLES =================
col_ctrl, col_view = st.columns([1, 1], gap="medium")

with col_ctrl:
    # ================= FEATURE: PASO 2 - ESCANEAR Y ABRIR EL TICKET =================
    st.markdown("### 🎯 Paso 2: Escanear y Abrir el Ticket")

    # Botón Destacado: Regresar a la Lista Anterior
    col_nav1, col_nav2 = st.columns([1, 1])
    with col_nav1:
        if st.button("🔙 Regresar a la Lista de Tickets", use_container_width=True):
            controller.go_back_to_list()
            st.session_state.last_action_msg = "Regresando a la vista de lista..."

            # Espera de 5 segundos con progreso visual para permitir carga completa de la lista en ServiceNow
            progress_bar = st.progress(0)
            status_text = st.empty()
            for i in range(5):
                time_left = 5 - i
                status_text.info(f"⏳ ServiceNow cargando lista de tickets... ({time_left}s restantes)")
                progress_bar.progress((i + 1) * 20)
                time.sleep(1.0)

            status_text.success("¡Lista de tickets cargada!")
            st.session_state.last_frame = controller.take_screenshot()
            diag = controller.scan_tickets_with_diagnostics()
            st.session_state.detected_tickets = diag.get("tickets", [])
            st.session_state.queue_summary_text = diag.get("totalQueueText", "")
            st.session_state.last_action_msg = "Lista de tickets cargada y vista espejo actualizada"
            time.sleep(0.3)
            st.rerun()

    with col_nav2:
        if st.button("🔄 Refrescar Tickets", use_container_width=True):
            diag = controller.scan_tickets_with_diagnostics()
            st.session_state.detected_tickets = diag.get("tickets", [])
            st.session_state.queue_summary_text = diag.get("totalQueueText", "")
            st.session_state.last_frame = controller.take_screenshot()
            st.rerun()

    # Si hay una pestaña enlazada pero aún no se escanearon tickets, escanear automáticamente
    if st.session_state.selected_tab_id and not st.session_state.detected_tickets:
        diag = controller.scan_tickets_with_diagnostics()
        st.session_state.detected_tickets = diag.get("tickets", [])
        st.session_state.queue_summary_text = diag.get("totalQueueText", "")
        st.session_state.last_scan_logs = diag.get("logs", [])
        st.session_state.last_frame = controller.take_screenshot()

    # Banner con información del Queue
    if st.session_state.queue_summary_text:
        st.markdown(f"""
        <div class="queue-counter-banner">
            📊 Total en Cola (Queue): {st.session_state.queue_summary_text} | Detectados en vista: {len(st.session_state.detected_tickets)}
        </div>
        """, unsafe_allow_html=True)

    # FUNCIÓN DE BÚSQUEDA Y APERTURA DIRECTA (1 SOLO DISPARO CON ESPERA DE 10s)
    st.markdown("#### 🔎 Búsqueda de Ticket")
    col_search_inp, col_search_btn = st.columns([2, 1])

    suggested_val = st.session_state.detected_tickets[0]["number"] if st.session_state.detected_tickets else ""

    with col_search_inp:
        search_num = st.text_input(
            "Ingresa el número de ticket:",
            value=suggested_val,
            placeholder="Ej: SCTASK5214212 o INC3446174",
            label_visibility="collapsed"
        )

    with col_search_btn:
        if st.button("⚡ Abrir Ticket", type="primary", use_container_width=True):
            if search_num.strip():
                clean_target = search_num.strip().upper()
                controller.locate_and_open_ticket(clean_target)
                st.session_state.last_action_msg = f"Abriendo ticket {clean_target}..."

                # Espera de 10 segundos con progreso visual para dar tiempo a ServiceNow
                progress_bar = st.progress(0)
                status_text = st.empty()
                for i in range(10):
                    time_left = 10 - i
                    status_text.info(f"⏳ ServiceNow cargando ticket {clean_target}... ({time_left}s restantes)")
                    progress_bar.progress((i + 1) * 10)
                    time.sleep(1.0)

                status_text.success(f"¡Ticket {clean_target} cargado!")
                st.session_state.last_frame = controller.take_screenshot()

                # Limpiar datos previos de Paso 3 y Paso 4 para mostrar exclusivamente el ticket buscado
                st.session_state.saved_tickets_list = []
                st.session_state.extracted_ticket_data = {}
                st.session_state.similarity_results = None

                # PASO 3: Extracción automática del ticket actual
                extracted = controller.extract_ticket_form_data()
                if extracted:
                    if not extracted.get("Number"):
                        extracted["Number"] = clean_target
                    st.session_state.extracted_ticket_data = extracted
                    st.session_state.saved_tickets_list = [extracted]

                st.session_state.last_action_msg = f"Ticket {clean_target} cargado (datos previos limpiados)"
                time.sleep(0.3)
                st.rerun()

    # LISTA DE TICKETS DETECTADOS AUTOMÁTICAMENTE
    if st.session_state.detected_tickets:
        total_found = len(st.session_state.detected_tickets)
        st.markdown(f"**Tickets disponibles en la tabla (`{total_found}`):**")

        # Si son más de 3 tickets, mostrar solo el primero y botón para ver el resto
        tickets_to_render = st.session_state.detected_tickets
        is_collapsed = False

        if total_found > 3 and not st.session_state.show_more_tickets:
            tickets_to_render = [st.session_state.detected_tickets[0]]
            is_collapsed = True

        for idx, t in enumerate(tickets_to_render):
            t_num = t["number"]
            t_desc = t.get("description", "Sin descripción")
            is_first = (idx == 0)

            with st.container():
                st.markdown(f"""
                <div class="ticket-box" style="{'border-left: 5px solid #009530; background:#f0fdf4;' if is_first else ''}">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:#0f172a; font-size:1.05rem;">
                            {'🥇 [Primero en Queue] ' if is_first else ''}🎯 {t_num}
                        </span>
                        <span style="font-size:0.75rem; background:#dcfce7; color:#166534; padding:2px 8px; border-radius:4px; font-weight:700;">Columna Number</span>
                    </div>
                    <p style="margin:4px 0 6px 0; font-size:0.8rem; color:#475569; line-height:1.3;">
                        {t_desc[:120]}{'...' if len(t_desc) > 120 else ''}
                    </p>
                </div>
                """, unsafe_allow_html=True)

                if st.button(f"👉 Abrir {t_num}", key=f"btn_open_pos_{t_num}_{idx}", use_container_width=True):
                    controller.locate_and_open_ticket(t_num)
                    st.session_state.last_action_msg = f"Abriendo ticket {t_num}..."

                    # Espera de 10 segundos con progreso visual para dar tiempo a ServiceNow
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    for i in range(10):
                        time_left = 10 - i
                        status_text.info(f"⏳ ServiceNow cargando {t_num}... ({time_left}s restantes)")
                        progress_bar.progress((i + 1) * 10)
                        time.sleep(1.0)

                    status_text.success(f"¡Ticket {t_num} cargado!")
                    st.session_state.last_frame = controller.take_screenshot()

                    # Limpiar datos previos de Paso 3 y Paso 4 para mostrar exclusivamente el ticket buscado
                    st.session_state.saved_tickets_list = []
                    st.session_state.extracted_ticket_data = {}
                    st.session_state.similarity_results = None

                    # PASO 3: Extracción automática del ticket actual
                    extracted = controller.extract_ticket_form_data()
                    if extracted:
                        if not extracted.get("Number"):
                            extracted["Number"] = t_num
                        st.session_state.extracted_ticket_data = extracted
                        st.session_state.saved_tickets_list = [extracted]

                    st.session_state.last_action_msg = f"Ticket {t_num} cargado (datos previos limpiados)"
                    time.sleep(0.3)
                    st.rerun()

        # Botón para expandir o contraer cuando hay más de 3 tickets
        if total_found > 3:
            if is_collapsed:
                if st.button(f"➕ Ver más tickets ({total_found - 1} restantes)", use_container_width=True):
                    st.session_state.show_more_tickets = True
                    st.rerun()
            else:
                if st.button("➖ Ver menos tickets", use_container_width=True):
                    st.session_state.show_more_tickets = False
                    st.rerun()
    else:
        st.info("💡 Enlaza tu pestaña de ServiceNow en el panel izquierdo; el escaneo se realiza automáticamente.")

    st.divider()

    # ================= FEATURE: PASO 3 - GUARDAR CAMPOS DEL TICKET EN TABLA =================
    st.markdown("### 📋 Paso 3: Guardar Campos del Ticket en Tabla")
    st.caption("Extracción y registro de los campos del formulario principal y de la pestaña **User Submitted Fields**.")

    col_p3_1, col_p3_2, col_p3_3 = st.columns([1, 1.4, 0.8])
    with col_p3_1:
        if st.button("📥 Extraer Campos Generales", type="secondary", use_container_width=True):
            with st.spinner("Extrayendo campos del formulario de ServiceNow..."):
                data = controller.extract_ticket_form_data()
                if data:
                    t_num = data.get("Number", "").strip()
                    existing_entry = st.session_state.saved_tickets_list[0] if st.session_state.saved_tickets_list else {}
                    merged = {**existing_entry, **data}
                    st.session_state.extracted_ticket_data = merged
                    st.session_state.saved_tickets_list = [merged]
                    st.session_state.last_action_msg = f"Campos generales extraídos para {t_num or 'ticket actual'}"
                    st.session_state.last_frame = controller.take_screenshot()
                    st.rerun()

    with col_p3_2:
        if st.button("📂 Abrir Tab 'User Submitted Fields' y Extraer", type="primary", use_container_width=True):
            with st.spinner("Cambiando a pestaña 'User Submitted Fields' en ServiceNow..."):
                user_fields = controller.open_and_extract_user_submitted_fields()

                # Obtener ticket activo
                curr_ticket = st.session_state.extracted_ticket_data.get("Number", "")
                if not curr_ticket and st.session_state.saved_tickets_list:
                    curr_ticket = st.session_state.saved_tickets_list[0].get("Number", "")

                # Mezclar datos exclusivamente sobre el ticket actual
                st.session_state.extracted_ticket_data.update(user_fields)
                if st.session_state.saved_tickets_list:
                    st.session_state.saved_tickets_list[0].update(user_fields)
                else:
                    entry = {"Number": curr_ticket, **user_fields}
                    st.session_state.saved_tickets_list = [entry]

                st.session_state.last_action_msg = "Pestaña 'User Submitted Fields' abierta y campos extraídos"
                st.session_state.last_frame = controller.take_screenshot()
                st.success("¡Pestaña 'User Submitted Fields' abierta y campos extraídos con éxito!")
                time.sleep(0.3)
                st.rerun()

    with col_p3_3:
        if st.button("🗑️ Limpiar Tabla", use_container_width=True):
            st.session_state.saved_tickets_list = []
            st.session_state.extracted_ticket_data = {}
            st.session_state.last_action_msg = "Tabla de tickets limpiada"
            st.rerun()

    # Visualización de la Tabla Guardada con todas las columnas requeridas
    field_columns = [
        "Number", "State", "Affected user", "User email used to login", "Channel", "Reported by",
        "Impact", "Category", "Urgency", "Subcategory", "Priority",
        "Service", "Assignment group", "Configuration Item", "Assigned to",
        "Short description", "Description", "More Information (Issue Description)"
    ]

    if st.session_state.saved_tickets_list:
        df_saved = pd.DataFrame(st.session_state.saved_tickets_list)
        for c in field_columns:
            if c not in df_saved.columns:
                df_saved[c] = ""
        df_saved = df_saved[field_columns]

        st.markdown(f"**📑 Tabla Completa de Formulario (18 Campos Extraídos) (`{len(df_saved)}`):**")
        st.dataframe(df_saved, use_container_width=True, height=380)

        # TABLA EXTRA SOLICITADA: Únicamente Número de Ticket y Descripción (estrictamente Description)
        st.markdown(f"**📋 Resumen Directo: Número de Ticket y Descripción (`{len(df_saved)}`):**")
        summary_rows = []
        for item in st.session_state.saved_tickets_list:
            t_num = item.get("Number", "").strip()
            # Usar estrictamente el campo Description del formulario
            desc_val = (item.get("Description") or item.get("description", "")).strip()
            if not desc_val:
                desc_val = item.get("More Information (Issue Description)", "").strip()
            if not desc_val:
                desc_val = "Sin contenido en Description (Short description: " + item.get("Short description", "").strip() + ")"
            summary_rows.append({
                "Número de Ticket": t_num,
                "Descripción": desc_val
            })
        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(
            df_summary,
            use_container_width=True,
            height=320,
            column_config={
                "Número de Ticket": st.column_config.TextColumn("Número de Ticket", width="small"),
                "Descripción": st.column_config.TextColumn("Descripción", width="large")
            }
        )

        csv_bytes = df_saved.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Descargar Tabla en CSV",
            data=csv_bytes,
            file_name="tickets_servicenow_extraidos.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("💡 Abre un ticket en el Paso 2 o presiona **'📥 Extraer Campos Generales'** y **'📂 Abrir Tab User Submitted Fields'** para registrar todos los campos en la tabla.")

    st.divider()

    # ================= FEATURE: PASO 4 - ANÁLISIS HISTÓRICO CSV Y LLM GEMMA =================
    st.markdown("### 🧠 Paso 4: Arrastra tu CSV para Análisis con LLM Local")
    st.caption("Arrastra tu archivo CSV con tickets históricos para comparar su campo **Description** contra el ticket del Paso 3 y obtener la sugerencia de Queue con LLM local.")

    # Cuadro directo y destacado para arrastrar el archivo CSV
    uploaded_csv = st.file_uploader(
        "📂 Arrastra aquí tu archivo CSV histórico de ServiceNow:",
        type=["csv"],
        key="uploader_csv_tickets_main",
        help="Soporta exportaciones estándar de ServiceNow con columnas Number, Description, Assignment group, State."
    )

    if uploaded_csv is not None:
        ok, msg = st.session_state.similarity_analyzer.load_csv(uploaded_csv)
        st.session_state.csv_status_msg = msg
        if ok:
            st.success(f"✅ {msg}")
        else:
            st.error(f"❌ {msg}")
    elif st.session_state.csv_status_msg:
        st.info(f"ℹ️ {st.session_state.csv_status_msg}")

    # Indicador de estado del LLM Local (Gemma)
    is_gemma_live = LocalGemmaClient.is_available()
    if is_gemma_live:
        models = LocalGemmaClient.get_available_models()
        model_display = next((m for m in models if "gemma" in m.lower()), "gemma:2b")
        st.success(f"🤖 **LLM Gemma Local Conectado:** Modelo `{model_display}` listo para generar explicaciones del enrutamiento.")
    else:
        st.info("⚙️ **Motor NLP Local Activo:** Procesará la similitud semántica con TF-IDF + Coseno. *(Opcional: ejecuta `ollama run gemma:2b` en tu terminal para activar explicaciones con Gemma)*.")

    # Botones de ejecución y limpieza
    col_sim_btn, col_sim_clear = st.columns([2, 1])
    with col_sim_btn:
        if st.button("🔍 Analizar Similitud con Tickets Históricos (CSV)", type="primary", use_container_width=True):
            # Obtener descripción del ticket de Paso 3
            target_desc = ""
            target_ticket_num = ""

            if st.session_state.saved_tickets_list:
                last_t = st.session_state.saved_tickets_list[-1]
                target_ticket_num = last_t.get("Number", "TICKET").strip()
                target_desc = (last_t.get("Description") or last_t.get("description") or last_t.get("More Information (Issue Description)")).strip()
            elif st.session_state.detected_tickets:
                last_t = st.session_state.detected_tickets[0]
                target_ticket_num = last_t.get("number", "TICKET").strip()
                target_desc = last_t.get("description", "").strip()

            if not target_desc:
                st.warning("⚠️ No se encontró la descripción del ticket en el Paso 3. Abre un ticket o extrae sus campos primero.")
            elif st.session_state.similarity_analyzer.df_historical is None:
                st.warning("⚠️ Por favor arrastra un archivo CSV arriba antes de presionar analizar.")
            else:
                with st.spinner(f"Analizando similitud de '{target_ticket_num}' contra tickets del CSV..."):
                    res = st.session_state.similarity_analyzer.analyze_similarity(target_desc, top_k=15)
                    res["ticket_number"] = target_ticket_num
                    res["ticket_desc"] = target_desc
                    st.session_state.similarity_results = res
                    st.session_state.last_action_msg = f"Análisis completado: {res.get('matches_count', 0)} tickets similares encontrados"
                    st.rerun()

    with col_sim_clear:
        if st.button("🗑️ Limpiar Análisis", use_container_width=True):
            st.session_state.similarity_results = None
            st.session_state.last_action_msg = "Resultados de análisis limpiados"
            st.rerun()

    # RESULTADOS DEL ANÁLISIS HISTÓRICO
    if st.session_state.similarity_results:
        res = st.session_state.similarity_results
        m_count = res.get("matches_count", 0)
        breakdown = res.get("queue_breakdown", {})
        top_q = res.get("top_queue", "")
        target_tnum = res.get("ticket_number", "TICKET")
        target_tdesc = res.get("ticket_desc", "Sin descripción registrada")

        # Resumen principal requerido con la descripción textual del ticket del Paso 3
        st.markdown(f"""
        <div style="background:#eff6ff; border:2px solid #3b82f6; border-radius:10px; padding:18px 22px; margin:16px 0;">
            <h4 style="margin:0; color:#1e40af; font-size:1.22rem;">🎯 Conclusión del Análisis Histórico</h4>

            <div style="background:#ffffff; border:1px solid #bfdbfe; border-radius:8px; padding:12px 16px; margin:12px 0;">
                <span style="font-weight:700; color:#1e3a8a; font-size:0.95rem;">📝 Descripción Textual del Ticket Evaluado ({target_tnum}):</span>
                <p style="margin:6px 0 0 0; color:#0f172a; font-size:0.92rem; white-space:pre-wrap; line-height:1.45;">{target_tdesc}</p>
            </div>

            <p style="margin:8px 0 10px 0; font-size:1.05rem; color:#1e293b; font-weight:700;">
                Se encontraron <span style="color:#2563eb; font-size:1.3rem;">{m_count}</span> tickets extremadamente parecidos a tu descripción y se cerraron en estos Queues:
            </p>
            <ul style="margin:0; padding-left:22px; color:#334155; font-size:0.98rem; line-height:1.5;">
                {''.join(f'<li><b>{q}:</b> {cnt} ticket(s) ({round(cnt/m_count*100, 1) if m_count else 0}%)</li>' for q, cnt in breakdown.items())}
            </ul>
            <div style="margin-top:14px; padding:10px 14px; background:#dbeafe; border-radius:6px; color:#1e40af; font-weight:700; font-size:1.05rem;">
                👉 Queue Recomendado por Cierre Histórico: <span style="font-size:1.15rem; color:#1d4ed8;">{top_q}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Síntesis de Gemma si está presente
        if res.get("gemma_synthesis"):
            st.markdown(f"""
            <div style="background:#f0fdf4; border-left:4px solid #16a34a; padding:12px 16px; border-radius:6px; margin:12px 0;">
                <span style="font-weight:700; color:#15803d;">🤖 Análisis Explicativo de Gemma Local:</span>
                <p style="margin:4px 0 0 0; color:#166534; font-size:0.92rem; white-space:pre-wrap;">
                    {res.get("gemma_synthesis")}
                </p>
            </div>
            """, unsafe_allow_html=True)

        # Tabla detallada ampliada con altura generosa y columnas completas
        matches_list = res.get("detailed_matches", [])
        if matches_list:
            st.markdown(f"**Detalle de Tickets Históricos Más Parecidos (`{len(matches_list)}`):**")
            df_matches = pd.DataFrame(matches_list)
            cols_to_show = ["Ticket Histórico", "Descripción Histórica", "Queue de Cierre", "Similitud (%)", "Estado / Cierre"]
            valid_cols = [c for c in cols_to_show if c in df_matches.columns]
            df_matches_view = df_matches[valid_cols]

            # Tabla más grande con altura de 560px para evitar scroll excesivo
            st.dataframe(
                df_matches_view,
                use_container_width=True,
                height=560,
                column_config={
                    "Ticket Histórico": st.column_config.TextColumn("Ticket Histórico", width="small"),
                    "Descripción Histórica": st.column_config.TextColumn("Descripción Histórica", width="large"),
                    "Queue de Cierre": st.column_config.TextColumn("Queue de Cierre", width="medium"),
                    "Similitud (%)": st.column_config.NumberColumn("Similitud (%)", format="%.1f%%"),
                    "Estado / Cierre": st.column_config.TextColumn("Estado / Cierre", width="small")
                }
            )

            csv_matches = df_matches_view.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Descargar Comparativa Histórica en CSV",
                data=csv_matches,
                file_name="comparativa_tickets_historicos.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.info("💡 Arrastra tu archivo CSV de tickets cerrados arriba y presiona **'🔍 Analizar Similitud con Tickets Históricos'** para comparar la descripción de Paso 3.")

    st.caption(f"Última acción: **{st.session_state.last_action_msg}**")


with col_view:
    st.subheader("📺 Vista Previa de la Pestaña")

    if st.session_state.selected_tab_id and controller.current_tab_id != st.session_state.selected_tab_id:
        controller.current_tab_id = st.session_state.selected_tab_id

    # Actualizar frame si no hay en memoria
    if not st.session_state.last_frame:
        st.session_state.last_frame = controller.take_screenshot()

    frame_to_show = st.session_state.last_frame

    if frame_to_show:
        image = Image.open(BytesIO(frame_to_show))
        st.image(image, caption=f"Pestaña enlazada: {st.session_state.selected_tab_title or 'En vivo'}", use_container_width=True)
        if st.button("📸 Actualizar Vista Espejo", use_container_width=True):
            st.session_state.last_frame = controller.take_screenshot()
            st.rerun()
    else:
        st.info("Elige tu pestaña en el panel izquierdo y haz clic en **'⚡ Enlazar'** para ver su vista en vivo aquí.")
