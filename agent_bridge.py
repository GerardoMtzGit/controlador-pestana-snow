"""
agent_bridge.py
Puente de Inteligencia Artificial que utiliza google-antigravity SDK
para interpretar intenciones del usuario en lenguaje natural y traducirlas
en acciones sobre la pestaña del navegador (ServiceNow o cualquier otra).
"""

import asyncio
import json
from typing import Dict, Any, Optional
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig


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
- Si el usuario dice "ve a las notas" o "abre notas", usa selector: "button:has-text('Notes'), [data-tab-name*='notes']"
- Si el usuario dice "baja" o "scroll abajo", usa action: "scroll", direction: "down"
- Si el usuario dice "sube" o "scroll arriba", usa action: "scroll", direction: "up"
- Si el usuario dice "actualizar" o "guardar", usa action: "click", selector: "button:has-text('Update'), button:has-text('Save')"

IMPORTANTE: Responde SIEMPRE con el bloque JSON sin texto introductorio.
"""


class AntigravityTabAgent:
    def __init__(self):
        self.config = LocalAgentConfig(
            system_instructions=SYSTEM_PROMPT,
            capabilities=CapabilitiesConfig()
        )

    async def interpret_command(self, user_prompt: str) -> Dict[str, Any]:
        """Envía el comando del usuario al agente Antigravity y devuelve la acción parseada."""
        try:
            async with Agent(self.config) as agent:
                response = await agent.chat(user_prompt)
                full_reply = ""
                async for token in response:
                    full_reply += token

                # Extraer JSON de la respuesta
                clean_reply = full_reply.strip()
                if "```json" in clean_reply:
                    clean_reply = clean_reply.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_reply:
                    clean_reply = clean_reply.split("```")[1].split("```")[0].strip()

                return json.loads(clean_reply)
        except Exception as e:
            # Fallback heurístico en caso de fallo de red/IA
            low = user_prompt.lower()
            if any(w in low for w in ["abajo", "baja", "down", "desciende"]):
                return {"action": "scroll", "direction": "down", "amount": 450}
            elif any(w in low for w in ["arriba", "sube", "up"]):
                return {"action": "scroll", "direction": "up", "amount": 450}
            elif any(w in low for w in ["recarga", "refresca", "reload"]):
                return {"action": "reload"}
            elif any(w in low for w in ["nota", "notas", "notes"]):
                return {"action": "click", "selector": "button:has-text('Notes'), [data-tab-name*='notes']"}
            elif any(w in low for w in ["guardar", "save", "update", "actualizar"]):
                return {"action": "click", "selector": "button:has-text('Update'), button:has-text('Save')"}
            return {"action": "answer", "message": f"Interpretado localmente (SDK fallback: {e})"}

    def run_sync(self, user_prompt: str) -> Dict[str, Any]:
        """Versión sincrónica para ejecutar directamente desde interfaces Streamlit/Tkinter."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.interpret_command(user_prompt))
            else:
                return asyncio.run(self.interpret_command(user_prompt))
        except Exception:
            return asyncio.run(self.interpret_command(user_prompt))

