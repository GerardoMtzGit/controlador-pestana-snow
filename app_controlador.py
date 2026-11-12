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
import streamlit as st
from tab_engine import CDPBrowserController, TabInfo
from agent_bridge import HuggingFaceTabAgent


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
                controller.locate_and_open_ticket(search_num.strip())
                st.session_state.last_action_msg = f"Abriendo ticket {search_num}..."

                # Espera de 10 segundos con progreso visual para dar tiempo a ServiceNow
                progress_bar = st.progress(0)
                status_text = st.empty()
                for i in range(10):
                    time_left = 10 - i
                    status_text.info(f"⏳ ServiceNow cargando ticket {search_num}... ({time_left}s restantes)")
                    progress_bar.progress((i + 1) * 10)
                    time.sleep(1.0)

                status_text.success(f"¡Ticket {search_num} cargado!")
                st.session_state.last_frame = controller.take_screenshot()
                st.session_state.last_action_msg = f"Ticket {search_num} cargado y vista espejo actualizada"
                time.sleep(0.3)
                st.rerun()

    # LISTA DE TICKETS DETECTADOS AUTOMÁTICAMENTE
    if st.session_state.detected_tickets:
        st.markdown(f"**Tickets disponibles en la tabla (`{len(st.session_state.detected_tickets)}`):**")
        for idx, t in enumerate(st.session_state.detected_tickets):
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
                    st.session_state.last_action_msg = f"Ticket {t_num} cargado y vista espejo actualizada"
                    time.sleep(0.3)
                    st.rerun()
    else:
        st.info("💡 Enlaza tu pestaña de ServiceNow en el panel izquierdo; el escaneo se realiza automáticamente.")

    st.divider()

    # ================= CONTROLES GENERALES DE MOVIMIENTO =================
    st.subheader("🎮 Controles para Mover la Pestaña")

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("⬆️ Subir", use_container_width=True):
            controller.scroll("up", 400)
            st.session_state.last_frame = controller.take_screenshot()
            st.session_state.last_action_msg = "Scroll hacia arriba (-400px)"
            st.rerun()
    with b2:
        if st.button("⬇️ Bajar", use_container_width=True):
            controller.scroll("down", 400)
            st.session_state.last_frame = controller.take_screenshot()
            st.session_state.last_action_msg = "Scroll hacia abajo (+400px)"
            st.rerun()
    with b3:
        if st.button("🔄 Recargar", use_container_width=True):
            controller.reload()
            st.session_state.last_frame = controller.take_screenshot()
            st.session_state.last_action_msg = "Pestaña recargada"
            st.rerun()
    with b4:
        if st.button("👁️ Enfocar", use_container_width=True):
            if st.session_state.selected_tab_id:
                controller.select_tab_by_id(st.session_state.selected_tab_id)
                st.session_state.last_action_msg = "Pestaña enfocada al frente"

    st.divider()

    # Acciones Especiales de Formulario
    st.markdown("#### ⚡ Acciones en Formulario de ServiceNow")
    sn1, sn2 = st.columns(2)
    with sn1:
        if st.button("📝 Ir a Pestaña Notes", use_container_width=True):
            done = controller.click_element("[data-tab-name*='notes']") or \
                   controller.click_element("button:has-text('Notes')") or \
                   controller.click_element("Notes")
            st.session_state.last_frame = controller.take_screenshot()
            st.session_state.last_action_msg = "Clic en Notes" if done else "Selector de Notes no encontrado"
            st.rerun()
    with sn2:
        if st.button("💾 Guardar / Update", use_container_width=True):
            done = controller.click_element("button#sysverb_update") or \
                   controller.click_element("button:has-text('Update')") or \
                   controller.click_element("Update")
            st.session_state.last_frame = controller.take_screenshot()
            st.session_state.last_action_msg = "Clic en Guardar/Update" if done else "Botón Update no encontrado"
            st.rerun()

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
