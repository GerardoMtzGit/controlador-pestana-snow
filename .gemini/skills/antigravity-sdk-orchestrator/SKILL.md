---
name: antigravity-sdk-orchestrator
description: Orquestación local para el control de la pestaña activa en ServiceNow y navegadores web sin depender de la nube.
---

# Skill: Antigravity Local Orchestrator

Esta habilidad estandariza la orquestación 100% local del asistente:

## 1. Modos de Ejecución Local
- **Motor de Reglas Determinista (`local_rules`):** Procesa expresiones regulares y heurísticas de baja latencia (0 ms, 0 consumo de tokens de nube, 100% privado).
- **LLM Local (`local_llm`):** Compatible con Ollama y endpoints OpenAI-compatibles locales (`http://127.0.0.1:11434/v1`), usando modelos descargados localmente como `qwen2.5-coder:7b`.

## 2. Acciones Soportadas
- `scroll` (`down`/`up` con detección de píxeles).
- `click` (con soporte para selectores de ServiceNow: notas, update, assignment group).
- `type` (ingreso en inputs y textareas).
- `reload` (recargar pestaña).
