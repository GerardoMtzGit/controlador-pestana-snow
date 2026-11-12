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
from classifier_engine import TicketClassifierEngine, USER_ROUTING_MARKDOWN


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

if "routing_markdown" not in st.session_state:
    st.session_state.routing_markdown = USER_ROUTING_MARKDOWN

if "classifier_engine" not in st.session_state:
    st.session_state.classifier_engine = TicketClassifierEngine(st.session_state.routing_markdown)

if "routing_decisions" not in st.session_state:
    st.session_state.routing_decisions = []

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

                # PASO 3: Extracción automática inmediata de los 16 campos
                extracted = controller.extract_ticket_form_data()
                if extracted:
                    if not extracted.get("Number"):
                        extracted["Number"] = clean_target
                    st.session_state.extracted_ticket_data = extracted
                    existing_idx = next((i for i, r in enumerate(st.session_state.saved_tickets_list) if r.get("Number") == extracted.get("Number")), None)
                    if existing_idx is not None:
                        st.session_state.saved_tickets_list[existing_idx] = extracted
                    else:
                        st.session_state.saved_tickets_list.append(extracted)

                st.session_state.last_action_msg = f"Ticket {clean_target} cargado y campos guardados en tabla"
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

                    # PASO 3: Extracción automática inmediata de los 16 campos
                    extracted = controller.extract_ticket_form_data()
                    if extracted:
                        if not extracted.get("Number"):
                            extracted["Number"] = t_num
                        st.session_state.extracted_ticket_data = extracted
                        existing_idx = next((i for i, r in enumerate(st.session_state.saved_tickets_list) if r.get("Number") == extracted.get("Number")), None)
                        if existing_idx is not None:
                            st.session_state.saved_tickets_list[existing_idx] = extracted
                        else:
                            st.session_state.saved_tickets_list.append(extracted)

                    st.session_state.last_action_msg = f"Ticket {t_num} cargado y campos guardados en tabla"
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
                    existing_entry = next((r for r in st.session_state.saved_tickets_list if r.get("Number") == t_num), {})
                    merged = {**existing_entry, **data}
                    st.session_state.extracted_ticket_data = merged

                    if t_num:
                        idx_found = next((i for i, r in enumerate(st.session_state.saved_tickets_list) if r.get("Number") == t_num), None)
                        if idx_found is not None:
                            st.session_state.saved_tickets_list[idx_found] = merged
                        else:
                            st.session_state.saved_tickets_list.append(merged)
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
                    curr_ticket = st.session_state.saved_tickets_list[-1].get("Number", "")

                # Mezclar datos en la sesión y en la tabla guardada
                st.session_state.extracted_ticket_data.update(user_fields)
                if curr_ticket:
                    idx_found = next((i for i, r in enumerate(st.session_state.saved_tickets_list) if r.get("Number") == curr_ticket), None)
                    if idx_found is not None:
                        st.session_state.saved_tickets_list[idx_found].update(user_fields)
                    else:
                        entry = {"Number": curr_ticket, **user_fields}
                        st.session_state.saved_tickets_list.append(entry)

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
        st.dataframe(df_saved, use_container_width=True)

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
        st.dataframe(df_summary, use_container_width=True)

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

    # ================= FEATURE: PASO 4 - CLASIFICACIÓN Y ENRUTAMIENTO INTELIGENTE =================
    st.markdown("### 🧠 Paso 4: Clasificación y Enrutamiento de Cola (Queue)")
    st.caption("Compara la descripción del ticket contra las directrices en Markdown para sugerir la Cola (Queue) de destino y una Posible Solución.")

    # Visualizador y Editor de Markdown
    with st.expander("📄 Ver / Modificar Guía de Reglas en Markdown", expanded=False):
        st.info("Puedes pegar aquí tus directrices en formato Markdown o modificarlas libremente. El motor reevaluará las colas y soluciones automáticamente.")
        new_md = st.text_area(
            "Directrices y Reglas Markdown:",
            value=st.session_state.routing_markdown,
            height=260,
            help="Pega aquí el contenido Markdown con los Queues, palabras clave y posibles soluciones."
        )
        if new_md != st.session_state.routing_markdown:
            st.session_state.routing_markdown = new_md
            st.session_state.classifier_engine.update_rules_from_markdown(new_md)
            st.success("¡Reglas Markdown actualizadas!")

    col_run_p4, col_clear_p4 = st.columns([2, 1])
    with col_run_p4:
        if st.button("🚀 Evaluar y Enrutar Tickets (Paso 4)", type="primary", use_container_width=True):
            # Priorizar tickets completos extraídos en Paso 3, o los detectados en la tabla de Paso 2
            tickets_to_eval = st.session_state.saved_tickets_list or st.session_state.detected_tickets
            if tickets_to_eval:
                with st.spinner("Comparando descripciones contra las directrices Markdown..."):
                    decisions = st.session_state.classifier_engine.classify_all_tickets(tickets_to_eval)
                    st.session_state.routing_decisions = decisions
                    st.session_state.last_action_msg = f"{len(decisions)} ticket(s) enrutados en Paso 4"
                    st.rerun()
            else:
                st.warning("No hay tickets disponibles para clasificar. Abre un ticket o enlaza la pestaña en el panel izquierdo.")

    with col_clear_p4:
        if st.button("🗑️ Limpiar Decisiones", use_container_width=True):
            st.session_state.routing_decisions = []
            st.session_state.last_action_msg = "Decisiones de Paso 4 limpiadas"
            st.rerun()

    # TABLA DE DECISIONES DE ENRUTAMIENTO (PASO 4)
    if st.session_state.routing_decisions:
        df_routing = pd.DataFrame(st.session_state.routing_decisions)
        routing_cols = ["Número de Ticket", "Descripción", "Equipo Destino", "Posible Queue", "Justificación", "Paso Evaluado"]
        present_r_cols = [c for c in routing_cols if c in df_routing.columns]
        df_routing = df_routing[present_r_cols]

        st.markdown(f"**Tabla de Enrutamiento y Posibles Soluciones (`{len(df_routing)}`):**")
        st.dataframe(df_routing, use_container_width=True)

        csv_routing_bytes = df_routing.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Descargar Tabla de Enrutamiento en CSV",
            data=csv_routing_bytes,
            file_name="enrutamiento_tickets_servicenow.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("💡 Haz clic en **'🚀 Evaluar y Enrutar Tickets (Paso 4)'** para analizar los tickets y generar la tabla con el Número de Ticket, Descripción, Posible Queue y Posible Solución.")

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
