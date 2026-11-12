---
name: cdp-tab-automation
description: Conexión, descubrimiento, selección e inspección en vivo de pestañas de navegador (Chrome/Edge) mediante Chrome DevTools Protocol (CDP) y Playwright.
---

# Skill: CDP Tab Automation & Mirroring

Esta habilidad proporciona el estándar de ingeniería para conectarse a un navegador en ejecución sin forzar el cierre de sesión ni perder el SSO corporativo.

## 1. Conexión no invasiva
- Detectar puerto de depuración (default: `9222` o configurable).
- Descubrir pestañas abiertas vía `http://localhost:9222/json/list`.
- Filtrar pestañas válidas (`type == "page"`), extrayendo `id`, `title`, `url` y `webSocketDebuggerUrl`.

## 2. Operaciones sobre la pestaña seleccionada
- **Navegación:** `bring_to_front()` / `activate()`.
- **Captura:** `screenshot()` con buffer de imagen para transmisión a UI en baja latencia.
- **Scroll interactivo:** `mouse.wheel(delta_x, delta_y)` o `evaluate("window.scrollBy(...)")`.
- **Clicks y Typing:** Enviar eventos exactos de mouse y teclado a selectores o coordenadas relativas.
- **Evaluación remota:** Inyección de scripts JavaScript para extraer el DOM visible sin recargar la página.
