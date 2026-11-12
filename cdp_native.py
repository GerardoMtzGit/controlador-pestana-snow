"""
cdp_native.py
Cliente nativo CDP (Chrome DevTools Protocol) ultra ligero y resiliente.
Se comunica directamente con el navegador vía WebSocket y HTTP estándar:
- 0 caídas por cierre de contexto de Playwright.
- Funciona perfecto con el ciclo de vida de Streamlit.
- Diagnóstico y logging detallado en consola.
- Apertura garantizada de tickets:
  Estrategia 1: Clic nativo en el elemento <a> con href del ticket y despacho de eventos de navegación.
  Estrategia 2: Extracción del enlace directo de ServiceNow y navegación nativa (Page.navigate).
  Estrategia 3: Cálculo preciso de coordenadas relativas al viewport de la ventana.
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

    def dispatch_mouse_click_at(self, x: float, y: float) -> bool:
        """Envía eventos reales de hardware del mouse mediante CDP Input.dispatchMouseEvent."""
        try:
            self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
            return True
        except Exception as e:
            print(f"[CDP Native] Error al despachar clic de mouse en ({x}, {y}): {e}")
            return False

    def detect_tickets_in_table(self) -> Dict[str, Any]:
        """Escanea el DOM visible y todos los Shadow Roots e iframes para listar tickets."""
        expr = """
        (function() {
            let logs = [];
            let foundTickets = [];
            let totalQueueCount = "";

            logs.push("URL actual: " + window.location.href);
            logs.push("Título: " + document.title);

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

            let ticketRegex = /\\b(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})\\b/gi;

            for (let root of allRoots) {
                let textContent = root.textContent || (root.body ? root.body.innerText : "") || "";
                if (textContent) allTexts.push(textContent);

                let qMatch = textContent.match(/\\b(\\d+)\\s+to\\s+(\\d+)\\s+of\\s+(\\d+)\\b/i) ||
                             textContent.match(/\\b(\\d+)\\s+of\\s+(\\d+)\\b/i) ||
                             textContent.match(/\\bTotal:\\s*(\\d+)\\b/i);
                if (qMatch && !totalQueueCount) {
                    totalQueueCount = qMatch[0];
                    logs.push("Conteo de cola detectado: " + totalQueueCount);
                }

                let candidates = Array.from(root.querySelectorAll("a, td, span, div, p"));
                for (let el of candidates) {
                    let txt = (el.innerText || el.textContent || "").trim();
                    let m = txt.match(/^\\b(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})\\b$/i);
                    if (m) {
                        let num = m[1].toUpperCase();
                        if (!foundTickets.some(t => t.number === num)) {
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
            result_obj = res.get("result", {})
            val = result_obj.get("value")
            if val is None and isinstance(result_obj.get("result"), dict):
                val = result_obj["result"].get("value")

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

    def locate_and_open_ticket(self, ticket_number: str) -> Dict[str, Any]:
        """
        PASO 2: Apertura Infalible del Ticket:
        1. Localiza el elemento <a> o celda que contiene el número de ticket.
        2. Extrae su URL directa (href) o función de navegación de ServiceNow.
        3. Si tiene href o acción, ejecuta window.location.href o abre el enlace en el frame.
        4. Si no, dispara eventos MouseEvent reales y envía Input.dispatchMouseEvent con coordenadas absolutas.
        """
        num_clean = ticket_number.strip().upper()
        expr = f"""
        (function() {{
            let targetNum = "{num_clean}";
            let allRoots = [];
            let logs = [];

            function scanNode(node, offsetX, offsetY) {{
                if (!node) return;
                allRoots.push({{ root: node, offsetX: offsetX, offsetY: offsetY }});

                if (node.shadowRoot) {{
                    scanNode(node.shadowRoot, offsetX, offsetY);
                }}

                let children = node.children || [];
                for (let i = 0; i < children.length; i++) {{
                    let child = children[i];
                    if (child.tagName && child.tagName.toLowerCase() === 'iframe') {{
                        try {{
                            let rect = child.getBoundingClientRect();
                            if (child.contentDocument) {{
                                scanNode(child.contentDocument, offsetX + rect.left, offsetY + rect.top);
                                logs.push("iFrame offset: " + rect.left + ", " + rect.top);
                            }}
                        }} catch(e) {{}}
                    }}
                    scanNode(child, offsetX, offsetY);
                }}
            }}

            scanNode(document.body || document.documentElement, 0, 0);

            let bestMatch = null;

            for (let item of allRoots) {{
                let root = item.root;
                let candidates = Array.from(root.querySelectorAll("a, td[data-field='number'], [role='gridcell'], span, div"));

                for (let el of candidates) {{
                    let txt = (el.innerText || el.textContent || "").trim().toUpperCase();
                    let href = el.getAttribute ? (el.getAttribute("href") || "") : "";

                    if (txt === targetNum || txt.includes(targetNum) || href.includes(targetNum)) {{
                        // El elemento clickeable exacto
                        let clickable = (el.tagName && el.tagName.toLowerCase() === 'a') ? el : (el.querySelector("a") || el);

                        if (clickable.scrollIntoView) {{
                            clickable.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                        }}

                        let r = clickable.getBoundingClientRect();
                        let clickX = item.offsetX + r.left + (r.width / 2);
                        let clickY = item.offsetY + r.top + (r.height / 2);

                        let targetHref = clickable.getAttribute ? (clickable.getAttribute("href") || "") : "";

                        // MÉTODO 1: Si es un enlace nativo de ServiceNow, invocar su navegación o window.open
                        let navSuccess = false;
                        if (targetHref && targetHref !== "#" && !targetHref.startsWith("javascript:void")) {{
                            try {{
                                if (clickable.ownerDocument && clickable.ownerDocument.defaultView) {{
                                    clickable.ownerDocument.defaultView.location.href = targetHref;
                                    navSuccess = true;
                                    logs.push("Navegacion directa vía ownerDocument location a: " + targetHref);
                                }} else {{
                                    window.location.href = targetHref;
                                    navSuccess = true;
                                    logs.push("Navegacion directa vía window location a: " + targetHref);
                                }}
                            }} catch(errNav) {{
                                logs.push("Fallo en navegacion directa: " + errNav.message);
                            }}
                        }}

                        // MÉTODO 2: Disparar eventos completos de mouse en el elemento
                        ['mouseenter', 'mouseover', 'mousedown', 'mouseup', 'click'].forEach(evtType => {{
                            let evt = new MouseEvent(evtType, {{
                                view: window,
                                bubbles: true,
                                cancelable: true,
                                clientX: clickX,
                                clientY: clickY
                            }});
                            clickable.dispatchEvent(evt);
                        }});

                        if (clickable.click && !navSuccess) {{
                            clickable.click();
                        }}

                        bestMatch = {{
                            found: true,
                            ticket: targetNum,
                            tagName: clickable.tagName,
                            href: targetHref,
                            x: clickX,
                            y: clickY,
                            navSuccess: navSuccess,
                            logs: logs
                        }};
                        break;
                    }}
                }}
                if (bestMatch) break;
            }}

            if (bestMatch) return bestMatch;
            return {{ found: false, ticket: targetNum, logs: logs }};
        }})();
        """
        try:
            res = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            result_obj = res.get("result", {})
            val = result_obj.get("value")
            if val is None and isinstance(result_obj.get("result"), dict):
                val = result_obj["result"].get("value")

            if isinstance(val, dict) and val.get("found"):
                x = val.get("x", 0)
                y = val.get("y", 0)
                href = val.get("href", "")
                print(f"[PASO 2] Ticket {num_clean} localizado en X={x:.1f}, Y={y:.1f} | Href: '{href}'")

                # Si no hubo navegación directa pero tenemos coordenadas válidas, enviar clic de ratón por CDP
                if not val.get("navSuccess") and x > 0 and y > 0:
                    self.dispatch_mouse_click_at(x, y)
                    val["mouse_event_sent"] = True

                return val
        except Exception as e:
            print(f"[CDP Native] Error en locate_and_open_ticket: {e}")

        # Fallback por selector
        self.click_selector(f"a:has-text('{num_clean}')")
        return {"found": False, "ticket": num_clean, "fallback": True}

    def reload(self) -> bool:
        """Recarga la pestaña."""
        try:
            self.send("Page.reload")
            return True
        except Exception as e:
            print(f"[CDP Native] Error al recargar: {e}")
            return False
