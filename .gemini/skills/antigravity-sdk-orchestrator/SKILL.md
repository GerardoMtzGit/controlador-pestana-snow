---
name: antigravity-sdk-orchestrator
description: Orquestación del Agente de Inteligencia Artificial mediante google-antigravity SDK para interpretar comandos del usuario y ejecutar acciones asistidas sobre la pestaña activa.
---

# Skill: Antigravity SDK Orchestrator

Esta habilidad estandariza el uso del paquete oficial `google-antigravity` en Python.

## 1. Configuración del Agente
- Uso de `LocalAgentConfig` y `CapabilitiesConfig` para habilitar herramientas seguras de lectura y ejecución.
- Inyección de instrucciones de sistema (`system_instructions`) contextualizadas al control de ServiceNow y navegación web.

## 2. Ciclo de Ejecución
- Context manager asíncrono:
  ```python
  async with Agent(config) as agent:
      response = await agent.chat(prompt)
  ```
- Streaming de respuesta, pensamientos (`response.thoughts`) y llamadas a herramientas (`response.tool_calls`).

## 3. Disparo de Acciones
- Traducción de intenciones en lenguaje natural ("busca el ticket INC123", "baja a las notas", "actualiza el grupo") en invocaciones CDP precisas.

