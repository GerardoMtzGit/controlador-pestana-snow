"""
agent_bridge.py
Puente de orquestación local para el control de la pestaña de navegador.
Soporta dos modalidades 100% locales:
1. Antigravity Local Engine (Motor determinista/reglas contextualizado de baja latencia, 0 dependencias de nube).
2. Local LLM / Ollama (compatible con LocalOpenAIAgentConfig / endpoints locales tipo http://127.0.0.1:11434/v1).
"""

import re
import json
import asyncio
import requests
from typing import Dict, Any, Optional

try:
    from google.antigravity import Agent, LocalOpenAIAgentConfig, CapabilitiesConfig
    ANTIGRAVITY_AVAILABLE = True
except Exception:
    ANTIGRAVITY_AVAILABLE = False


SYSTEM_PROMPT = """
Eres un asistente de automatización y control de navegador web (especializado en ServiceNow y portales corporativos).
Tu objetivo es interpretar lo que pide el usuario y retornar ÚNICAMENTE un objeto JSON válido con la acción que se debe ejecutar en la pestaña activa.

Las acciones disponibles son:
1. SCROLL: {"action": "scroll", "direction": "down" | "up", "amount": 400}
2. CLICK: {"action": "click", "selector": "texto o selector CSS"}
3. TYPE: {"action": "type", "selector": "selector CSS", "text": "texto a escribir"}
4. RELOAD: {"action": "reload"}
5. NAVIGATE: {"action": "navigate", "url": "https://..."}
6. ANSWER: {"action": "answer", "message": "Respuesta informativa directa al usuario"}
"""


class LocalOrchestrator:
    """Motor de orquestación local determinista de alta velocidad y cero latencia."""

    @staticmethod
    def parse_command(user_prompt: str) -> Dict[str, Any]:
        text = user_prompt.strip().lower()

        # 1. Extracción de distancias de scroll (ej: "baja 500px", "sube 200")
        amount_match = re.search(r"\b(\d{2,4})\s*(px|pixeles|píxeles)?\b", text)
        scroll_amount = int(amount_match.group(1)) if amount_match else 400

        # Scroll hacia abajo
        if any(w in text for w in ["abajo", "baja", "down", "desciende", "bajar", "scroll down"]):
            return {"action": "scroll", "direction": "down", "amount": scroll_amount, "engine": "local_rules"}

        # Scroll hacia arriba
        if any(w in text for w in ["arriba", "sube", "up", "ascender", "subir", "scroll up"]):
            return {"action": "scroll", "direction": "up", "amount": scroll_amount, "engine": "local_rules"}

        # Recargar página
        if any(w in text for w in ["recarga", "refresca", "reload", "actualiza la página", "f5"]):
            return {"action": "reload", "engine": "local_rules"}

        # Clics específicos de ServiceNow: Notas
        if any(w in text for w in ["nota", "notas", "notes", "work notes", "pestaña notas"]):
            return {
                "action": "click",
                "selector": "[data-tab-name*='notes'], button:has-text('Notes'), span.tab_caption_text:has-text('Notes')",
                "engine": "local_rules",
                "label": "Ir a pestaña Notes"
            }

        # Clics específicos de ServiceNow: Guardar / Update
        if any(w in text for w in ["guardar", "save", "update", "actualizar", "guardar cambios"]):
            return {
                "action": "click",
                "selector": "button#sysverb_update, button:has-text('Update'), button:has-text('Save')",
                "engine": "local_rules",
                "label": "Guardar / Update"
            }

        # Clics específicos de ServiceNow: Asignación o Grupo
        if any(w in text for w in ["assignment group", "grupo de asignación", "grupo"]):
            return {
                "action": "click",
                "selector": "input[id*='assignment_group'], input[name*='assignment_group']",
                "engine": "local_rules",
                "label": "Campo Assignment Group"
            }

        # Escribir texto
        type_match = re.search(r"(?:escribe|escribir|pon|type)\s+['\"]?(.+?)['\"]?\s+(?:en|sobre)\s+(.+)", text)
        if type_match:
            txt_to_type = type_match.group(1).strip()
            target_field = type_match.group(2).strip()
            selector = f"input[placeholder*='{target_field}'], textarea[name*='{target_field}']"
            return {"action": "type", "selector": selector, "text": txt_to_type, "engine": "local_rules"}

        # Clic genérico por nombre de botón
        click_match = re.search(r"(?:haz\s+)?(?:clic|click|presiona|toca)\s+(?:en\s+|sobre\s+)?['\"]?(.+?)['\"]?$", text)
        if click_match:
            target_btn = click_match.group(1).strip()
            return {"action": "click", "selector": f"button:has-text('{target_btn}'), a:has-text('{target_btn}')", "engine": "local_rules"}

        # Navegación a URL
        url_match = re.search(r"(?:navega|ve a|ir a|abre)\s+(https?://[^\s]+)", text)
        if url_match:
            return {"action": "navigate", "url": url_match.group(1), "engine": "local_rules"}

        return {
            "action": "answer",
            "message": f"Comando '{user_prompt}' interpretado localmente. Puedes probar: 'baja 500px', 'sube', 'haz clic en Notes', 'guardar' o 'recarga'.",
            "engine": "local_rules"
        }


class AntigravityTabAgent:
    """Orquestador híbrido con preferencia local estricta."""

    def __init__(self, mode: str = "local_rules", ollama_base_url: str = "http://127.0.0.1:11434/v1", model_name: str = "qwen2.5-coder:7b"):
        self.mode = mode
        self.ollama_base_url = ollama_base_url
        self.model_name = model_name

    def is_ollama_online(self) -> bool:
        """Verifica si el servidor Ollama local está activo."""
        try:
            r = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.0)
            return r.status_code == 200
        except Exception:
            return False

    async def _interpret_with_local_llm(self, prompt: str) -> Dict[str, Any]:
        """Utiliza el conector LocalOpenAIAgentConfig del SDK o llamada local directa a Ollama."""
        # 1. Intentar vía endpoint local de Ollama (OpenAI-compatible)
        try:
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "format": "json"
            }
            r = requests.post(f"{self.ollama_base_url}/chat/completions", json=payload, timeout=8.0)
            if r.status_code == 200:
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                parsed["engine"] = f"ollama_{self.model_name}"
                return parsed
        except Exception:
            pass

        # Fallback inmediato al motor de reglas local
        return LocalOrchestrator.parse_command(prompt)

    def run_sync(self, user_prompt: str) -> Dict[str, Any]:
        """Ejecuta la orquestación en modo estrictamente local sin llamadas a servidores externos."""
        if self.mode == "local_llm" and self.is_ollama_online():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
                    return loop.run_until_complete(self._interpret_with_local_llm(user_prompt))
                else:
                    return asyncio.run(self._interpret_with_local_llm(user_prompt))
            except Exception:
                return LocalOrchestrator.parse_command(user_prompt)

        # Modo por defecto: motor local instantáneo (0 llamadas de red)
        return LocalOrchestrator.parse_command(user_prompt)
