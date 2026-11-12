"""
app_controlador.py
Interfaz interactiva y clara para seleccionar y controlar pestañas de ServiceNow.
Incluye:
- Conexión CDP nativa ultra estable (sin caídas de Playwright).
- Botones compatibles con nuevas versiones de Streamlit (width='stretch').
- Detección visual y botón directo '⚡ Conectar a esta pestaña de ServiceNow'.
- Scroll fluido y vista previa en tiempo real.
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
</style>
""", unsafe_allow_html=True)

# Banner Principal
st.markdown("""
<div class="se-banner">
    <h2 style="margin:0; font-size:1.4rem; font-weight:700;">⚡ Controlador Directo de Pestaña ServiceNow</h2>
    <p style="margin:4px 0 0 0; font-size:0.88rem; color:#cbd5e1;">
        Selecciona tu pestaña de ServiceNow en el panel izquierdo y muévela, haz scroll o interactúa con ella desde aquí.
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
                st.success("¡Pestaña de ServiceNow vinculada permanentemente!")
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
                st.success("¡Pestaña enlazada!")
                time.sleep(0.3)
                st.rerun()
        with col_act2:
            if st.button("🔄 Refrescar", use_container_width=True):
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
    st.subheader("🎮 Controles para Mover la Pestaña")

    if st.session_state.selected_tab_id:
        st.markdown(f"**Pestaña Activa:** `{st.session_state.selected_tab_title or st.session_state.selected_tab_id}`")
    else:
        st.info("💡 Enlaza una pestaña desde el menú lateral para activarla.")

    # Botones de Scroll y Vista
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("⬆️ Subir", use_container_width=True):
            controller.scroll("up", 400)
            st.session_state.last_action_msg = "Scroll hacia arriba (-400px)"
            st.rerun()
    with b2:
        if st.button("⬇️ Bajar", use_container_width=True):
            controller.scroll("down", 400)
            st.session_state.last_action_msg = "Scroll hacia abajo (+400px)"
            st.rerun()
    with b3:
        if st.button("🔄 Recargar", use_container_width=True):
            controller.reload()
            st.session_state.last_action_msg = "Pestaña recargada"
            st.rerun()
    with b4:
        if st.button("👁️ Enfocar", use_container_width=True):
            if st.session_state.selected_tab_id:
                controller.select_tab_by_id(st.session_state.selected_tab_id)
                st.session_state.last_action_msg = "Pestaña enfocada al frente"

    st.divider()

    # Acciones Especiales de ServiceNow
    st.markdown("#### ⚡ Acciones en Tickets de ServiceNow")
    sn1, sn2 = st.columns(2)
    with sn1:
        if st.button("📝 Ir a Pestaña Notes", use_container_width=True):
            done = controller.click_element("[data-tab-name*='notes']") or \
                   controller.click_element("button:has-text('Notes')") or \
                   controller.click_element("Notes")
            st.session_state.last_action_msg = "Clic en Notes" if done else "Selector de Notes no encontrado"
            st.rerun()
    with sn2:
        if st.button("💾 Guardar / Update", use_container_width=True):
            done = controller.click_element("button#sysverb_update") or \
                   controller.click_element("button:has-text('Update')") or \
                   controller.click_element("Update")
            st.session_state.last_action_msg = "Clic en Guardar/Update" if done else "Botón Update no encontrado"
            st.rerun()

    st.divider()

    # Comandos en lenguaje natural
    st.markdown("#### 💬 Comandos por Texto")
    prompt = st.text_input(
        "Escribe qué quieres que haga la pestaña:",
        placeholder="Ej: 'baja 500px', 'sube', 'haz clic en Notes', 'guardar'..."
    )

    if st.button("✨ Enviar Comando", use_container_width=True):
        if prompt:
            action_data = agent.run_sync(prompt)
            act = action_data.get("action", "")
            
            if act == "scroll":
                direction = action_data.get("direction", "down")
                amt = action_data.get("amount", 400)
                controller.scroll(direction, amt)
                st.session_state.last_action_msg = f"Scroll {direction} ({amt}px)"
            elif act == "click":
                sel = action_data.get("selector", "")
                done = controller.click_element(sel)
                st.session_state.last_action_msg = f"Clic en {sel} ({'Éxito' if done else 'No hallado'})"
            elif act == "reload":
                controller.reload()
                st.session_state.last_action_msg = "Recarga completada"
            elif act == "answer":
                st.info(action_data.get("message", ""))

            st.rerun()

    st.caption(f"Última acción: **{st.session_state.last_action_msg}**")


with col_view:
    st.subheader("📺 Vista Previa de la Pestaña")

    if st.session_state.selected_tab_id and controller.current_tab_id != st.session_state.selected_tab_id:
        controller.current_tab_id = st.session_state.selected_tab_id

    screenshot_bytes = controller.take_screenshot()
    if screenshot_bytes:
        st.session_state.last_frame = screenshot_bytes

    frame_to_show = screenshot_bytes or st.session_state.last_frame

    if frame_to_show:
        image = Image.open(BytesIO(frame_to_show))
        st.image(image, caption=f"Pestaña enlazada: {st.session_state.selected_tab_title or 'En vivo'}", use_container_width=True)
        if st.button("📸 Actualizar Vista Espejo", use_container_width=True):
            st.rerun()
    else:
        st.info("Elige tu pestaña en el panel izquierdo y haz clic en **'⚡ Enlazar'** para ver su vista en vivo aquí.")
