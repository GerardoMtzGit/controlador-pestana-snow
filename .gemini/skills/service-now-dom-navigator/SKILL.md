---
name: service-now-dom-navigator
description: Mapeo y navegación de la interfaz de ServiceNow (Next Experience / UI16 / Service Portal), incluyendo iFrames, formularios de Incidentes y tablas de tareas.
---

# Skill: ServiceNow DOM Navigator

Esta habilidad documenta las peculiaridades del DOM en ServiceNow para evitar fallos por elementos anidados o tiempos de carga dinámicos.

## 1. Detección de iFrames
- ServiceNow tradicionalmente carga las vistas y formularios dentro de `iframe#gsft_main` o dentro de componentes Web/Shadow DOM.
- Siempre verificar si el elemento objetivo está en el documento raíz o dentro de un `frame_locator("iframe#gsft_main")`.

## 2. Selectores Comunes
- **Campo de Búsqueda:** `input[placeholder*='Search']`, `input#sysparm_search`
- **Pestaña de Notas:** `[data-tab-name*='notes']`, `button:has-text('Notes')`, `span.tab_caption_text:has-text('Notes')`
- **Work Notes:** `textarea[id*='work_notes']`, `textarea[name*='work_notes']`
- **Assignment Group:** `input[name*='assignment_group']`, `input[id*='sys_display.incident.assignment_group']`
- **Botón Guardar/Update:** `button#sysverb_update`, `button:has-text('Update')`, `button:has-text('Save')`

## 3. Manejo de Esperas
- Usar `wait_for_selector(..., state="visible", timeout=5000)` antes de interactuar.
- Realizar scroll antes de hacer click para asegurar que el elemento esté en el viewport.

