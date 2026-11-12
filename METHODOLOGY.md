# Metodología de Construcción: Controlador de Pestaña ServiceNow con Antigravity SDK

Este documento define la metodología de desarrollo estructurada en 5 fases (Spec-Driven Development + Modular Architecture).

```
[Fase 1: Especificación y Contratos]
                │
                ▼
[Fase 2: Motor de Conectividad CDP & Playwright]
                │
                ▼
[Fase 3: Integración con Google Antigravity SDK]
                │
                ▼
[Fase 4: Interfaz de Usuario Limpia y Minimalista]
                │
                ▼
[Fase 5: Pruebas de Integración y Lanzador 1-Click]
```

---

## Fase 1: Arquitectura y Módulos
1. **`tab_engine.py`**:
   - Descubre todas las pestañas abiertas en Chrome/Edge (puerto 9222).
   - Permite listar pestañas con `title`, `url`, `id`.
   - Permite activar/enfocar una pestaña.
   - Permite scroll (arriba, abajo, cantidad personalizada).
   - Permite hacer clic, escribir texto y navegar a una URL.
   - Captura fotogramas/capturas de pantalla en tiempo real de la pestaña seleccionada.

2. **`agent_bridge.py`**:
   - Integra `google.antigravity.Agent` con `LocalAgentConfig`.
   - Permite recibir instrucciones en lenguaje natural ("ve a la pestaña de ServiceNow", "haz scroll abajo", "escribe esto en notas") y ejecutarlas a través de `tab_engine`.

3. **`ui.py`**:
   - Interfaz gráfica limpia (CustomTkinter / Streamlit) enfocada en:
     - Selector desplegable de pestañas activas (con botón "Refrescar pestañas").
     - Vista en vivo (preview) de la pestaña seleccionada.
     - Botones de acción directa: Arriba / Abajo / Click / Recargar / Enfocar.
     - Barra de comando asistido con IA (Google Antigravity SDK).

4. **`launch_browser_debug.bat`**:
   - Script para iniciar Chrome/Edge con depuración remota activada sin alterar el perfil principal ni requerir extensiones complejas.

