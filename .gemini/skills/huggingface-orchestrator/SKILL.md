---
name: huggingface-orchestrator
description: Orquestación del Agente de Inteligencia Artificial mediante modelos de Hugging Face (InferenceClient / Qwen2.5 / Mistral) o motor local determinista.
---

# Skill: Hugging Face Orchestrator

Esta habilidad estandariza la orquestación del asistente sin librerías externas propietarias:

## 1. Modos de Ejecución
- **Motor Local Determinista (`local_rules`):** Procesa expresiones regulares y heurísticas de baja latencia (0 ms, 0 llamadas de red, 100% privado y corporativo).
- **Hugging Face (`huggingface`):** Conexión vía `huggingface_hub.InferenceClient` con modelos como `Qwen/Qwen2.5-Coder-7B-Instruct` o `mistralai/Mistral-7B-Instruct-v0.3`.

## 2. Acciones Soportadas
- `scroll` (`down`/`up` con detección de píxeles).
- `click` (con soporte para selectores de ServiceNow: notas, update, assignment group).
- `type` (ingreso en inputs y textareas).
- `reload` (recargar pestaña).

