"""
agent_bridge.py
Puente de orquestación para el control de la pestaña de navegador.
Diseñado para entornos corporativos:
- 0 dependencias exóticas (no requiere nest-asyncio ni bucles async conflictivos).
- Funciones 100% sincrónicas nativas para máxima compatibilidad con Streamlit.
- Motor Local Determinista (0 ms latencia, 0 red, corporativo).
- Soporte opcional para Hugging Face (InferenceClient / HTTP directo).
"""

import os
import re
import json
import requests
from typing import Dict, Any, Optional

try:
    from huggingface_hub import InferenceClient
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False


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

Para ServiceNow:
- Si el usuario dice "ve a las notas", usa selector: "[data-tab-name*='notes'], button:has-text('Notes')"
- Si el usuario dice "baja", usa action: "scroll", direction: "down"
- Si el usuario dice "sube", usa action: "scroll", direction: "up"
- Si el usuario dice "guardar", usa action: "click", selector: "button#sysverb_update, button:has-text('Update')"

Responde siempre con el JSON puro.
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


class HuggingFaceTabAgent:
    """Orquestador con soporte para modelos de Hugging Face y fallback a motor local sincrónico."""

    def __init__(
        self,
        mode: str = "local_rules",
        hf_token: Optional[str] = None,
        model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    ):
        self.mode = mode
        self.hf_token = hf_token or os.getenv("HF_TOKEN", "")
        self.model_name = model_name
        self.client: Optional[Any] = None

        if HF_AVAILABLE and self.hf_token:
            try:
                self.client = InferenceClient(model=self.model_name, token=self.hf_token)
            except Exception:
                self.client = None

    def interpret_with_hf(self, prompt: str) -> Dict[str, Any]:
        """Consulta el modelo de Hugging Face mediante InferenceClient o REST de forma sincrónica."""
        if not self.client:
            return LocalOrchestrator.parse_command(prompt)

        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            response = self.client.chat_completion(
                messages=messages,
                max_tokens=256,
                temperature=0.1
            )
            content = response.choices[0].message.content.strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            parsed = json.loads(content)
            parsed["engine"] = f"hf_{self.model_name.split('/')[-1]}"
            return parsed
        except Exception:
            return LocalOrchestrator.parse_command(prompt)

    def run_sync(self, user_prompt: str) -> Dict[str, Any]:
        """Ejecución 100% sincrónica directa (no requiere nest-asyncio)."""
        if self.mode == "huggingface" and self.client:
            return self.interpret_with_hf(user_prompt)
        return LocalOrchestrator.parse_command(user_prompt)
