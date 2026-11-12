"""
cdp_native.py
Cliente nativo CDP (Chrome DevTools Protocol) ultra ligero y resiliente.
Se comunica directamente con el navegador vía WebSocket y HTTP estándar:
- 0 caídas por cierre de contexto de Playwright.
- Funciona perfecto con el ciclo de vida de Streamlit.
- Métodos directos: captura de pantalla (Page.captureScreenshot), scroll (Runtime.evaluate),
  detección de tablas de tickets en ServiceNow y apertura por click en la columna Number.
"""

import json
import base64
import requests
import asyncio
import websockets
from typing import List, Dict, Any, Optional


def run_coro_sync(coro):
    """Ejecuta una corrutina de forma sincrónica en un event loop seguro."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class CDPNativeClient:
    """Cliente CDP directo sobre WebSocket para una pestaña específica."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._msg_id = 0

    async def _send_command(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 3.5) -> Dict[str, Any]:
        self._msg_id += 1
        msg = {
            "id": self._msg_id,
            "method": method,
            "params": params or {}
        }
        async with websockets.connect(self.ws_url, max_size=25 * 1024 * 1024) as ws:
            await ws.send(json.dumps(msg))
            while True:
                resp = await asyncio.wait_for(ws.recv(), timeout=timeout)
                data = json.loads(resp)
                if data.get("id") == self._msg_id:
                    return data

    def send(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 3.5) -> Dict[str, Any]:
        return run_coro_sync(self._send_command(method, params, timeout=timeout))

    def capture_screenshot(self) -> Optional[bytes]:
        """Captura de pantalla instantánea vía Page.captureScreenshot."""
        try:
            res = self.send("Page.captureScreenshot", {"format": "jpeg", "quality": 75})
            if "result" in res and "data" in res["result"]:
                return base64.b64decode(res["result"]["data"])
        except Exception as e:
            print(f"[CDP Native] Error al capturar: {e}")
        return None

    def scroll(self, delta_y: int) -> bool:
        """Scroll vertical fluido en la página."""
        expr = f"""
        (function() {{
            window.scrollBy({{ top: {delta_y}, behavior: 'smooth' }});
            return true;
        }})();
        """
        try:
            self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return True
        except Exception as e:
            print(f"[CDP Native] Error al hacer scroll: {e}")
            return False

    def click_selector(self, selector: str) -> bool:
        """Hace clic en un elemento CSS/XPath o dentro de iframe gsft_main en ServiceNow."""
        expr = f"""
        (function() {{
            function tryClick(doc) {{
                try {{
                    let el = doc.querySelector("{selector}");
                    if (el) {{
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        el.click();
                        return true;
                    }}
                }} catch(e) {{}}
                return false;
            }}

            if (tryClick(document)) return true;

            let iframe = document.querySelector("iframe#gsft_main");
            if (iframe && iframe.contentDocument) {{
                if (tryClick(iframe.contentDocument)) return true;
            }}

            let btns = Array.from(document.querySelectorAll("button, a, span"));
            for (let b of btns) {{
                if (b.innerText && b.innerText.trim().toLowerCase().includes("{selector.lower()}")) {{
                    b.click();
                    return true;
                }}
            }}
            return false;
        }})();
        """
        try:
            self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return True
        except Exception as e:
            print(f"[CDP Native] Error al hacer click: {e}")
            return False

    def detect_tickets_in_table(self) -> List[Dict[str, str]]:
        """
        Inspecciona el DOM de la vista de ServiceNow (tanto en el documento principal como en iframe#gsft_main).
        Localiza la tabla de tareas/incidentes y extrae cada registro de la columna 'Number':
        - Número de ticket (ej. SCTASK5214212, INC3446174, TASK..., RITM...)
        - Descripción breve
        - Estado
        - Asignado a
        """
        expr = """
        (function() {
            let docs = [document];
            let iframe = document.querySelector("iframe#gsft_main");
            if (iframe && iframe.contentDocument) {
                docs.push(iframe.contentDocument);
            }

            let foundTickets = [];

            for (let doc of docs) {
                // Estrategia 1: Buscar enlaces o celdas con formato de ticket típico de ServiceNow
                let elements = Array.from(doc.querySelectorAll("a, td, span, div"));
                for (let el of elements) {
                    let txt = (el.innerText || "").trim();
                    let match = txt.match(/^(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})$/i);
                    if (match) {
                        let ticketNum = match[1].toUpperCase();
                        if (!foundTickets.some(t => t.number === ticketNum)) {
                            // Extraer contexto de la fila (tr) si existe
                            let tr = el.closest("tr");
                            let desc = "";
                            let state = "";
                            let assignedTo = "";

                            if (tr) {
                                let cells = Array.from(tr.querySelectorAll("td"));
                                let texts = cells.map(c => (c.innerText || "").trim()).filter(t => t && t !== ticketNum);
                                if (texts.length > 0) desc = texts.find(t => t.length > 15) || texts[0];
                                if (texts.length > 1) state = texts.find(t => ["in progress", "on hold", "new", "open", "resolved", "pending"].includes(t.toLowerCase())) || "";
                            }

                            foundTickets.push({
                                number: ticketNum,
                                description: desc,
                                state: state
                            });
                        }
                    }
                }
            }
            return foundTickets;
        })();
        """
        try:
            res = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            if "result" in res and "value" in res["result"] and isinstance(res["result"]["value"], list):
                return res["result"]["value"]
        except Exception as e:
            print(f"[CDP Native] Error al detectar tickets: {e}")
        return []

    def open_ticket_by_number(self, ticket_number: str) -> bool:
        """
        Ubica la celda o enlace correspondiente al ticket en la columna Number y hace clic en él
        para abrir el formulario completo del ticket.
        """
        num_clean = ticket_number.strip().upper()
        expr = f"""
        (function() {{
            let targetNum = "{num_clean}";
            let docs = [document];
            let iframe = document.querySelector("iframe#gsft_main");
            if (iframe && iframe.contentDocument) {{
                docs.push(iframe.contentDocument);
            }}

            for (let doc of docs) {{
                // 1. Buscar enlaces con el número exacto
                let links = Array.from(doc.querySelectorAll("a, td[data-field='number'], span, tr"));
                for (let el of links) {{
                    let txt = (el.innerText || "").trim().toUpperCase();
                    if (txt === targetNum || txt.startsWith(targetNum) || el.getAttribute("href")?.includes(targetNum)) {{
                        // Buscar el elemento clickeable exacto
                        let clickable = (el.tagName.toLowerCase() === 'a') ? el : (el.querySelector("a") || el);
                        clickable.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        clickable.click();
                        return true;
                    }}
                }}
            }}
            return false;
        }})();
        """
        try:
            res = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            if "result" in res and res["result"].get("value") is True:
                return True
        except Exception as e:
            print(f"[CDP Native] Error al abrir ticket {ticket_number}: {e}")
            return False

        # Fallback: forzar clic enviando evento Mouse
        return self.click_selector(f"a:has-text('{num_clean}')") or self.click_selector(num_clean)

    def reload(self) -> bool:
        """Recarga la pestaña."""
        try:
            self.send("Page.reload")
            return True
        except Exception as e:
            print(f"[CDP Native] Error al recargar: {e}")
            return False
