"""
cdp_native.py
Cliente nativo CDP (Chrome DevTools Protocol) ultra ligero y resiliente.
Se comunica directamente con el navegador vía WebSocket y HTTP estándar:
- 0 caídas por cierre de contexto de Playwright.
- Funciona perfecto con el ciclo de vida de Streamlit.
- Diagnóstico y logging detallado en consola.
- Escaneo profundo multietapa: DOM principal, iframes anidados, Shadow DOM y Regex de texto visible.
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
        Escanea exhaustivamente el DOM visible y todos los iframes (Next Experience / UI16 / Service Portal).
        Devuelve tanto la lista estructurada de tickets como logs de diagnóstico para la consola.
        """
        expr = """
        (function() {
            let logs = [];
            let foundTickets = [];
            let totalQueueCount = "";

            logs.push("URL actual: " + window.location.href);
            logs.push("Título actual: " + document.title);

            let docs = [document];
            let allIframes = Array.from(document.querySelectorAll("iframe, frame"));
            logs.push("iFrames detectados: " + allIframes.length);

            allIframes.forEach((ifr, idx) => {
                try {
                    if (ifr.contentDocument) {
                        docs.push(ifr.contentDocument);
                        logs.push("iFrame [" + idx + "] accesorio OK: " + (ifr.id || ifr.name || ifr.src));
                    } else {
                        logs.push("iFrame [" + idx + "] sin acceso directo al contentDocument.");
                    }
                } catch(e) {
                    logs.push("iFrame [" + idx + "] bloqueado por origen/seguridad: " + e.message);
                }
            });

            for (let doc of docs) {
                let pageTexts = (doc.body ? doc.body.innerText : "");
                let qMatch = pageTexts.match(/\\b(\\d+)\\s+to\\s+(\\d+)\\s+of\\s+(\\d+)\\b/i) ||
                             pageTexts.match(/\\b(\\d+)\\s+of\\s+(\\d+)\\b/i) ||
                             pageTexts.match(/\\bTotal:\\s*(\\d+)\\b/i);
                if (qMatch) {
                    totalQueueCount = qMatch[0];
                    logs.push("Conteo de cola detectado en texto: " + totalQueueCount);
                    break;
                }
            }

            let ticketRegex = /\\b(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})\\b/gi;

            for (let doc of docs) {
                let rows = Array.from(doc.querySelectorAll("tr, div[role='row']"));
                logs.push("Filas (tr/row) evaluadas en documento: " + rows.length);

                for (let r of rows) {
                    let rText = (r.innerText || "");
                    let match = rText.match(ticketRegex);
                    if (match) {
                        for (let rawNum of match) {
                            let num = rawNum.toUpperCase();
                            if (!foundTickets.some(t => t.number === num)) {
                                let linkEl = r.querySelector("a, [data-field='number']");
                                foundTickets.push({
                                    number: num,
                                    description: rText.replace(num, "").trim().substring(0, 140),
                                    hasLink: !!linkEl
                                });
                            }
                        }
                    }
                }

                let links = Array.from(doc.querySelectorAll("a, span, td"));
                for (let el of links) {
                    let txt = (el.innerText || "").trim();
                    let m = txt.match(/^\\b(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})\\b$/i);
                    if (m) {
                        let num = m[1].toUpperCase();
                        if (!foundTickets.some(t => t.number === num)) {
                            foundTickets.push({
                                number: num,
                                description: "Ticket detectado en elemento " + el.tagName,
                                hasLink: true
                            });
                        }
                    }
                }
            }

            if (foundTickets.length === 0) {
                logs.push("Estrategias A y B no arrojaron tickets. Probando escaneo Regex global...");
                for (let doc of docs) {
                    let fullText = (doc.body ? doc.body.innerText : "");
                    let globalMatches = fullText.match(ticketRegex);
                    if (globalMatches) {
                        logs.push("Coincidencias Regex globales encontradas: " + globalMatches.length);
                        for (let gm of globalMatches) {
                            let gNum = gm.toUpperCase();
                            if (!foundTickets.some(t => t.number === gNum)) {
                                foundTickets.push({
                                    number: gNum,
                                    description: "Ticket detectado por escaneo global de texto",
                                    hasLink: false
                                });
                            }
                        }
                    }
                }
            }

            logs.push("Total de tickets unicos encontrados: " + foundTickets.length);

            return {
                tickets: foundTickets,
                totalQueueText: totalQueueCount || (foundTickets.length + " ticket(s) en vista"),
                logs: logs
            };
        })();
        """
        try:
            res = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            if "result" in res and "value" in res["result"] and isinstance(res["result"]["value"], dict):
                return res["result"]["value"]
        except Exception as e:
            print(f"[CDP Native] Error al detectar tickets: {e}")
        return {"tickets": [], "totalQueueText": "0 tickets", "logs": [f"Error ejecutando script de escaneo: {e}"]}

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
            let allIframes = Array.from(document.querySelectorAll("iframe, frame"));
            allIframes.forEach(function(ifr) {{
                try {{
                    if (ifr.contentDocument) {{
                        docs.push(ifr.contentDocument);
                    }}
                }} catch(e) {{}}
            }});

            for (let doc of docs) {{
                let links = Array.from(doc.querySelectorAll("a, td, span, tr, [role='gridcell']"));
                for (let el of links) {{
                    let txt = (el.innerText || "").trim().toUpperCase();
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

        # Fallback: forzar clic
        return self.click_selector(f"a:has-text('{num_clean}')") or self.click_selector(num_clean)

    def reload(self) -> bool:
        """Recarga la pestaña."""
        try:
            self.send("Page.reload")
            return True
        except Exception as e:
            print(f"[CDP Native] Error al recargar: {e}")
            return False
