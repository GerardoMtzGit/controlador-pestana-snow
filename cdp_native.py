"""
cdp_native.py
Cliente nativo CDP (Chrome DevTools Protocol) ultra ligero y resiliente.
Se comunica directamente con el navegador vía WebSocket y HTTP estándar:
- 0 caídas por cierre de contexto de Playwright.
- Funciona perfecto con el ciclo de vida de Streamlit.
- Diagnóstico y logging detallado en consola.
- Escaneo profundo multietapa: DOM principal, iframes anidados, Web Components con Shadow DOM
  (now-content-renderer, macroponent-*, etc. de Next Experience).
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

    async def _send_command(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 4.0) -> Dict[str, Any]:
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

    def send(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 4.0) -> Dict[str, Any]:
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
        selector_clean = selector.replace('"', '\\"').replace("'", "\\'")
        expr = f"""
        (function() {{
            function tryClick(doc) {{
                try {{
                    let el = doc.querySelector("{selector_clean}");
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
                if (b.innerText && b.innerText.trim().toLowerCase().includes("{selector_clean.lower()}")) {{
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

    def detect_tickets_in_table(self) -> Dict[str, Any]:
        """
        Escanea exhaustivamente el DOM visible, incluyendo todos los Web Components y Shadow Roots
        de ServiceNow Next Experience (Polaris) e iframes encapsulados.
        """
        expr = """
        (function() {
            let logs = [];
            let foundTickets = [];
            let totalQueueCount = "";

            logs.push("URL actual: " + window.location.href);
            logs.push("Título: " + document.title);

            // Función recursiva para atravesar Shadow DOM y recopilar todos los nodos y documentos
            let allRoots = [document];
            let allTexts = [];

            function collectShadowRoots(node) {
                if (!node) return;
                if (node.shadowRoot) {
                    allRoots.push(node.shadowRoot);
                    collectShadowRoots(node.shadowRoot);
                }
                let children = node.children || [];
                for (let i = 0; i < children.length; i++) {
                    let child = children[i];
                    if (child.tagName && child.tagName.toLowerCase() === 'iframe') {
                        try {
                            if (child.contentDocument) {
                                allRoots.push(child.contentDocument);
                                collectShadowRoots(child.contentDocument.body);
                                logs.push("iFrame penetrado con exito: " + (child.id || child.name || child.src));
                            }
                        } catch(err) {
                            logs.push("iFrame protegido por CORS/origen: " + err.message);
                        }
                    }
                    collectShadowRoots(child);
                }
            }

            collectShadowRoots(document.body || document.documentElement);
            logs.push("Roots inspeccionados (incluyendo Shadow DOM): " + allRoots.length);

            // Regex de tickets de ServiceNow
            let ticketRegex = /\\b(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})\\b/gi;

            for (let root of allRoots) {
                // 1. Extraer conteo de Queue en texto
                let textContent = root.textContent || (root.body ? root.body.innerText : "") || "";
                if (textContent) allTexts.push(textContent);

                let qMatch = textContent.match(/\\b(\\d+)\\s+to\\s+(\\d+)\\s+of\\s+(\\d+)\\b/i) ||
                             textContent.match(/\\b(\\d+)\\s+of\\s+(\\d+)\\b/i) ||
                             textContent.match(/\\bTotal:\\s*(\\d+)\\b/i);
                if (qMatch && !totalQueueCount) {
                    totalQueueCount = qMatch[0];
                    logs.push("Conteo de cola detectado: " + totalQueueCount);
                }

                // 2. Buscar enlaces o elementos clickeables que contengan números de ticket
                let candidates = Array.from(root.querySelectorAll("a, td, span, div, p"));
                for (let el of candidates) {
                    let txt = (el.innerText || el.textContent || "").trim();
                    let m = txt.match(/^\\b(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})\\b$/i);
                    if (m) {
                        let num = m[1].toUpperCase();
                        if (!foundTickets.some(t => t.number === num)) {
                            // Extraer descripción del contenedor padre o fila si es posible
                            let row = el.closest("tr, div[role='row'], [role='gridcell']");
                            let desc = "";
                            if (row) {
                                desc = (row.innerText || "").replace(num, "").trim().substring(0, 140);
                            }
                            foundTickets.push({
                                number: num,
                                description: desc || "Ticket en lista",
                                hasLink: true
                            });
                        }
                    }
                }
            }

            // 3. Si aún no encuentra por selectores, aplicar Regex a todo el texto concatenado
            if (foundTickets.length === 0) {
                logs.push("Búsqueda estructurada no halló tickets. Aplicando Regex en los textos de todos los Roots...");
                let fullJoinedText = allTexts.join("\\n");
                let matches = fullJoinedText.match(ticketRegex);
                if (matches) {
                    logs.push("Coincidencias en texto: " + matches.length);
                    for (let rawNum of matches) {
                        let num = rawNum.toUpperCase();
                        if (!foundTickets.some(t => t.number === num)) {
                            foundTickets.push({
                                number: num,
                                description: "Ticket detectado en texto",
                                hasLink: false
                            });
                        }
                    }
                }
            }

            logs.push("Total de tickets unicos detectados: " + foundTickets.length);

            return {
                tickets: foundTickets,
                totalQueueText: totalQueueCount || (foundTickets.length + " ticket(s) en vista"),
                logs: logs
            };
        })();
        """
        try:
            res = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            # Manejar la estructura anidada de Chrome DevTools: res['result']['value']
            val = res.get("result", {}).get("value")
            if isinstance(val, dict):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    pass
            return {
                "tickets": [],
                "totalQueueText": "0 tickets",
                "logs": [f"Retorno inesperado de CDP: {res}"]
            }
        except Exception as ex:
            print(f"[CDP Native] Error al detectar tickets: {ex}")
            return {
                "tickets": [],
                "totalQueueText": "0 tickets",
                "logs": [f"Error ejecutando script de escaneo: {ex}"]
            }

    def open_ticket_by_number(self, ticket_number: str) -> bool:
        """
        Ubica la celda o enlace correspondiente al ticket en la columna Number
        (incluso dentro de Shadow DOM o iframes de ServiceNow) y hace clic en él.
        """
        num_clean = ticket_number.strip().upper()
        expr = f"""
        (function() {{
            let targetNum = "{num_clean}";
            let allRoots = [document];

            function collectShadowRoots(node) {{
                if (!node) return;
                if (node.shadowRoot) {{
                    allRoots.push(node.shadowRoot);
                    collectShadowRoots(node.shadowRoot);
                }}
                let children = node.children || [];
                for (let i = 0; i < children.length; i++) {{
                    let child = children[i];
                    if (child.tagName && child.tagName.toLowerCase() === 'iframe') {{
                        try {{
                            if (child.contentDocument) {{
                                allRoots.push(child.contentDocument);
                                collectShadowRoots(child.contentDocument.body);
                            }}
                        }} catch(e) {{}}
                    }}
                    collectShadowRoots(child);
                }}
            }}

            collectShadowRoots(document.body || document.documentElement);

            for (let root of allRoots) {{
                let candidates = Array.from(root.querySelectorAll("a, td, span, tr, [role='gridcell'], div"));
                for (let el of candidates) {{
                    let txt = (el.innerText || el.textContent || "").trim().toUpperCase();
                    let href = el.getAttribute ? (el.getAttribute("href") || "") : "";
                    if (txt === targetNum || txt.includes(targetNum) || href.includes(targetNum)) {{
                        let clickable = (el.tagName && el.tagName.toLowerCase() === 'a') ? el : (el.querySelector("a") || el);
                        if (clickable && clickable.scrollIntoView) {{
                            clickable.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }}
                        if (clickable && clickable.click) {{
                            clickable.click();
                            return true;
                        }}
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

        # Fallback
        return self.click_selector(f"a:has-text('{num_clean}')") or self.click_selector(num_clean)

    def reload(self) -> bool:
        """Recarga la pestaña."""
        try:
            self.send("Page.reload")
            return True
        except Exception as e:
            print(f"[CDP Native] Error al recargar: {e}")
            return False
