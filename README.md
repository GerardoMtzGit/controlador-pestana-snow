# Controlador de Pestañas Web (ServiceNow / Chrome) con Google Antigravity SDK

Subproyecto independiente y modular dentro de `asignador de SNOW/controlador_pestana` diseñado con una metodología de ingeniería estructurada (Spec-Driven + Modular Architecture).

Repositorio oficial en GitHub: **[https://github.com/GerardoMtzGit/controlador-pestana-snow](https://github.com/GerardoMtzGit/controlador-pestana-snow)**

---

## ⚡ Inicio con Auto-Verificación y Descarga de Dependencias

El proyecto cuenta con un sistema de arranque inteligente que:
1. **Comprueba librerías faltantes** (`streamlit`, `playwright`, `google-antigravity`, `requests`, `pillow`, `nest-asyncio`). Si falta alguna, **la descarga e instala automáticamente** vía pip antes de iniciar.
2. **Valida componentes de Playwright** (navegadores y conectores CDP).
3. **Revisa la integridad de las Skills** en `.gemini/skills/` y las restaura automáticamente si alguna falta.
4. **Lanza la aplicación web** directamente en tu navegador.

### Para iniciar:
- **Doble clic en:** [`iniciar_proyecto.bat`](iniciar_proyecto.bat) (o ejecuta `python bootstrap.py` en la terminal).

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
├── bootstrap.py                 # Auto-verificador y descargador de dependencias/skills
├── iniciar_proyecto.bat         # LANZADOR PRINCIPAL 1-CLIC (con auto-instalación)
├── requirements.txt             # Lista de requerimientos y versiones mínimas
├── tab_engine.py                # Motor central CDP y Playwright (scroll, clicks, capturas)
├── agent_bridge.py              # Puente del agente IA con Google Antigravity SDK
├── app_controlador.py           # Interfaz gráfica moderna y limpia en Streamlit
├── iniciar_navegador_debug.bat  # Inicia Chrome/Edge en puerto 9222
├── METHODOLOGY.md               # Metodología de construcción y diseño
└── README.md                    # Documentación del proyecto
```

---

## 🛠️ Guía Rápida de Uso

1. **Abrir Chrome con Depuración:**
   - Ejecuta [`iniciar_navegador_debug.bat`](iniciar_navegador_debug.bat) y abre tu sesión de **ServiceNow**.
2. **Iniciar el Proyecto:**
   - Ejecuta [`iniciar_proyecto.bat`](iniciar_proyecto.bat). El programa verificará e instalará cualquier librería o skill faltante e iniciará la interfaz.
3. **Operar la Pestaña:**
   - En el panel lateral, selecciona la pestaña de ServiceNow y haz clic en **"⚡ Activar y Enlazar Pestaña"**.
   - Usa los botones directos (**Subir, Bajar, Recargar, Enfocar, Ir a Notes, Guardar**) o escribe comandos en lenguaje natural con el Agente IA de Google Antigravity.
