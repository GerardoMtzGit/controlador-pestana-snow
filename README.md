# Controlador de Pestañas Web (ServiceNow / Chrome) con Google Antigravity SDK

Subproyecto independiente y modular dentro de `asignador de SNOW/controlador_pestana` diseñado con una metodología de ingeniería estructurada (Spec-Driven + Modular Architecture).

---

## 🚀 Metodología y Habilidades (Skills) Integradas

Este proyecto cuenta con tres habilidades especializadas documentadas en `.gemini/skills/`:
1. **`cdp-tab-automation`**: Conexión a Chrome/Edge en ejecución (vía puerto de depuración 9222), descubrimiento y activación de pestañas mediante CDP y Playwright sin perder sesiones activas ni SSO corporativo.
2. **`antigravity-sdk-orchestrator`**: Integración con el paquete oficial `google-antigravity` para interpretar instrucciones en lenguaje natural ("baja a las notas", "sube 300px", "actualiza el ticket").
3. **`service-now-dom-navigator`**: Mapeo y navegación de formularios, iFrames (`gsft_main`), selectores de notas y botones de guardado específicos de ServiceNow.

---

## 📂 Estructura de Archivos

```text
controlador_pestana/
├── .gemini/skills/              # Skills metodológicas del proyecto
│   ├── cdp-tab-automation/      # Habilidad de control de pestañas y CDP
│   ├── antigravity-sdk-orchestrator/ # Habilidad de uso del SDK oficial
│   └── service-now-dom-navigator/   # Habilidad de navegación de ServiceNow
├── tab_engine.py                # Motor central CDP y Playwright (scroll, clicks, capturas)
├── agent_bridge.py              # Puente del agente IA con Google Antigravity SDK
├── app_controlador.py           # Interfaz gráfica moderna y limpia en Streamlit
├── iniciar_navegador_debug.bat  # Inicia Chrome/Edge en puerto 9222
├── ejecutar_controlador.bat     # Lanza la aplicación interactiva con 1 clic
├── METHODOLOGY.md               # Metodología de construcción y diseño
└── README.md                    # Documentación del proyecto
```

---

## 🛠️ Cómo Utilizar

1. **Abrir Chrome con Depuración:**
   - Ejecuta [`iniciar_navegador_debug.bat`](iniciar_navegador_debug.bat) o inicia Chrome con `--remote-debugging-port=9222`.
   - Abre tu sesión de **ServiceNow** o cualquier otra página.

2. **Lanzar la Interfaz:**
   - Ejecuta [`ejecutar_controlador.bat`](ejecutar_controlador.bat).
   - Se abrirá en tu navegador: `http://localhost:8501`.

3. **Operar la Pestaña:**
   - En el panel lateral, verás la lista automática de pestañas abiertas.
   - Selecciona la pestaña de **ServiceNow** y haz clic en **"⚡ Activar y Enlazar Pestaña"**.
   - Usa los botones directos (**Subir, Bajar, Recargar, Enfocar, Ir a Notes, Guardar**) o escribe comandos en lenguaje natural con el Agente IA de Google Antigravity.

