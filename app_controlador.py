"""
app_controlador.py
Interfaz limpia y minimalista en Streamlit para seleccionar y controlar pestañas de navegador.
Permite:
- Ver todas las pestañas abiertas en tiempo real (con título y URL).
- Seleccionar una pestaña (ej. ServiceNow).
- Mover la pestaña (Scroll Arriba / Abajo, Click en botones, Recargar).
- Vista previa en vivo con captura de pantalla.
- Comando inteligente vía Orquestador Local (motor de reglas instantáneo o LLM local).
"""

import time
import subprocess
from io import BytesIO
from PIL import Image
import streamlit as st
from tab_engine import CDPBrowserController
from agent_bridge import AntigravityTabAgent


st.set_page_config(
    page_title="Controlador de Pestañas | ServiceNow",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar estado de sesión
if "controller" not in st.session_state:
    st.session_state.controller = CDPBrowserController(port=9222)

if "agent" not in st.session_state:
    st.session_state.agent = AntigravityTabAgent(mode="local_rules")

if "selected_tab_id" not in st.session_state:
    st.session_state.selected_tab_id = None

if "last_action_msg" not in st.session_state:
    st.session_state.last_action_msg = "Listo para conectar"

controller: CDPBrowserController = st.session_state.controller
agent: AntigravityTabAgent = st.session_state.agent

# Estilos CSS limpios
st.markdown("""
<style>
    .header-box {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        padding: 16px 20px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
        border-left: 5px solid #2563eb;
    }
    .status-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.82rem;
        font-weight: 600;
    }
    .status-ok { background: #dcfce7; color: #15803d; }
    .status-warn { background: #fef3c7; color: #b45309; }
    .status-info { background: #e0f2fe; color: #0369a1; }
</style>
""", unsafe_allow_html=True)

# Encabezado
st.markdown("""
<div class="header-box">
    <h2 style="margin:0; font-size:1.5rem; font-weight:700;">🎯 Controlador de Pestañas Web (ServiceNow / Chrome)</h2>
    <p style="margin:4px 0 0 0; font-size:0.9rem; color:#94a3b8;">
        Controla y mueve la pestaña seleccionada directamente desde esta interfaz con <strong>orquestación 100% local</strong>.
    </p>
</div>
""", unsafe_allow_html=True)

# SIDEBAR: Conexión, Configuración Local y Selección de Pestañas
with st.sidebar:
    st.header("🔌 Conexión de Navegador")
    is_connected = controller.is_cdp_available()

    if is_connected:
        st.markdown('<span class="status-badge status-ok">● Navegador Detectado (Puerto 9222)</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-badge status-warn">▲ Navegador Desconectado</span>', unsafe_allow_html=True)
        st.info("Para conectar tu navegador sin cerrar sesión, inicia Chrome con depuración:")
        if st.button("🚀 Iniciar Navegador con Depuración", use_container_width=True):
            try:
                subprocess.Popen(["cmd.exe", "/c", "iniciar_navegador_debug.bat"], shell=True)
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"Error al abrir: {e}")

    st.divider()

    # Selector de Motor de Orquestación Local
    st.subheader("⚙️ Motor de Orquestación")
    engine_choice = st.selectbox(
        "Modo de orquestación:",
        options=["Motor Local Determinista (Ultra rápido, 0 red)", "LLM Local (Ollama / LocalOpenAI)"],
        index=0
    )

    if "LLM Local" in engine_choice:
        agent.mode = "local_llm"
        ollama_ok = agent.is_ollama_online()
        if ollama_ok:
            st.markdown('<span class="status-badge status-ok">● Ollama Local Activo</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-warn">▲ Ollama no detectado en :11434</span>', unsafe_allow_html=True)
            st.caption("Usa 'ollama serve' para iniciar tu modelo local, o mantén el Motor Local.")
    else:
        agent.mode = "local_rules"
        st.markdown('<span class="status-badge status-info">● Motor de Reglas Local Activo</span>', unsafe_allow_html=True)

    st.divider()
    st.subheader("📑 Seleccionar Pestaña")

    tabs = controller.list_tabs() if is_connected else []

    if tabs:
        tab_options = {f"{t.title[:45]} ({t.url[:35]}...)": t.tab_id for t in tabs}
        
        default_index = 0
        for i, t in enumerate(tabs):
            if any(k in t.url.lower() or k in t.title.lower() for k in ["service-now", "servicenow", "incident", "task"]):
                default_index = i
                break

        selected_label = st.selectbox(
            "Pestañas abiertas:",
            options=list(tab_options.keys()),
            index=default_index
        )
        selected_id = tab_options[selected_label]

        if st.button("⚡ Activar y Enlazar Pestaña", type="primary", use_container_width=True):
            success = controller.select_tab_by_id(selected_id)
            if success:
                st.session_state.selected_tab_id = selected_id
                st.session_state.last_action_msg = f"Enlazado a: {selected_label}"
                st.success("¡Pestaña enlazada correctamente!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("No se pudo conectar a la pestaña.")
    else:
        if is_connected:
            st.warning("No se encontraron pestañas tipo página abiertas.")
        else:
            st.caption("Abre Chrome con depuración para listar tus pestañas.")

    if st.button("🔄 Refrescar Lista de Pestañas", use_container_width=True):
        st.rerun()


# PANEL PRINCIPAL
col_left, col_right = st.columns([1, 1], gap="medium")

with col_left:
    st.subheader("🎮 Controles de la Pestaña")

    # Botones directos de movimiento
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("⬆️ Subir", use_container_width=True):
            controller.scroll("up", 400)
            st.session_state.last_action_msg = "Scroll hacia arriba (400px)"
            st.rerun()
    with c2:
        if st.button("⬇️ Bajar", use_container_width=True):
            controller.scroll("down", 400)
            st.session_state.last_action_msg = "Scroll hacia abajo (400px)"
            st.rerun()
    with c3:
        if st.button("🔄 Recargar", use_container_width=True):
            controller.reload()
            st.session_state.last_action_msg = "Página recargada"
            st.rerun()
    with c4:
        if st.button("👁️ Enfocar", use_container_width=True):
            if st.session_state.selected_tab_id:
                controller.select_tab_by_id(st.session_state.selected_tab_id)
                st.session_state.last_action_msg = "Pestaña enfocada al frente"

    st.divider()

    # Controles específicos de ServiceNow
    st.markdown("#### ⚡ Acciones Rápidas para ServiceNow")
    sn1, sn2 = st.columns(2)
    with sn1:
        if st.button("📝 Ir a Pestaña Notes", use_container_width=True):
            done = controller.click_element("[data-tab-name*='notes']") or \
                   controller.click_element("button:has-text('Notes')") or \
                   controller.click_element("span.tab_caption_text:has-text('Notes')")
            st.session_state.last_action_msg = "Clic en Notes" if done else "Selector de Notes no encontrado"
            st.rerun()
    with sn2:
        if st.button("💾 Guardar / Update", use_container_width=True):
            done = controller.click_element("button#sysverb_update") or \
                   controller.click_element("button:has-text('Update')") or \
                   controller.click_element("button:has-text('Save')")
            st.session_state.last_action_msg = "Clic en Guardar/Update" if done else "Botón Update no encontrado"
            st.rerun()

    st.divider()

    # Control por Lenguaje Natural con Orquestador Local
    st.markdown("#### 🤖 Orquestador Asistido Local (0 llamadas a la nube)")
    prompt = st.text_input(
        "Indica una acción en lenguaje natural:",
        placeholder="Ej: 'baja 500px', 'sube', 'haz clic en Notes', 'guardar'..."
    )

    if st.button("✨ Ejecutar Acción Local", use_container_width=True):
        if prompt:
            action_data = agent.run_sync(prompt)
            act = action_data.get("action", "")
            engine_used = action_data.get("engine", "local")
            
            if act == "scroll":
                direction = action_data.get("direction", "down")
                amt = action_data.get("amount", 400)
                controller.scroll(direction, amt)
                st.session_state.last_action_msg = f"[{engine_used}] Scroll {direction} ({amt}px)"
            elif act == "click":
                sel = action_data.get("selector", "")
                done = controller.click_element(sel)
                st.session_state.last_action_msg = f"[{engine_used}] Clic en: {sel} ({'Éxito' if done else 'No hallado'})"
            elif act == "reload":
                controller.reload()
                st.session_state.last_action_msg = f"[{engine_used}] Recarga completada"
            elif act == "answer":
                st.info(action_data.get("message", ""))
            
            st.rerun()

    st.caption(f"Última acción: **{st.session_state.last_action_msg}**")


with col_right:
    st.subheader("📺 Vista Previa en Vivo de la Pestaña")
    
    screenshot_bytes = controller.take_screenshot()
    if screenshot_bytes:
        image = Image.open(BytesIO(screenshot_bytes))
        st.image(image, caption="Pestaña activa en tiempo real", use_container_width=True)
    else:
        st.warning("Selecciona y activa una pestaña desde el panel lateral izquierdo para ver su contenido en vivo aquí.")
