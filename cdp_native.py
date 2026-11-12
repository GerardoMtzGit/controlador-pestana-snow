"""
cdp_native.py
Cliente nativo CDP (Chrome DevTools Protocol) ultra ligero y resiliente.
Apertura física de tickets directamente en la PESTAÑA ORIGEN del navegador:
1. Identifica el sys_id o la URL del formulario del ticket en ServiceNow.
2. Abre el ticket EXACTAMENTE UNA SOLA VEZ (sin duplicar aperturas).
3. Función de retroceso / volver a la vista anterior (history.back).
4. Actualización sincronizada de fotograma espejo.
"""

import json
import base64
import requests
import asyncio
import websockets
from typing import List, Dict, Any, Optional

try:
    import win32gui
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


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

    def bring_window_to_front(self):
        """Enfoca y trae al frente la ventana real del navegador Chrome en Windows."""
        try:
            self.send("Page.bringToFront")
        except Exception:
            pass

        if WIN32_AVAILABLE:
            try:
                def enum_handler(hwnd, _):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if any(k in title.lower() for k in ["chrome", "edge", "servicenow"]):
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            win32gui.SetForegroundWindow(hwnd)
                win32gui.EnumWindows(enum_handler, None)
            except Exception:
                pass

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
        """Scroll vertical fluido en la pestaña origen."""
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

    def go_back(self) -> bool:
        """
        Regresa a la vista anterior (historial del navegador o del iFrame gsft_main de ServiceNow).
        """
        expr = """
        (function() {
            let ifr = document.querySelector("iframe#gsft_main");
            if (ifr && ifr.contentWindow && ifr.contentWindow.history && ifr.contentWindow.history.length > 1) {
                ifr.contentWindow.history.back();
                return { mode: "iframe_history_back" };
            }
            if (window.history && window.history.length > 1) {
                window.history.back();
                return { mode: "window_history_back" };
            }
            return { mode: "none" };
        })();
        """
        try:
            self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return True
        except Exception as e:
            print(f"[CDP Native] Error en go_back: {e}")
            return False

    def detect_tickets_in_table(self) -> Dict[str, Any]:
        """
        Escanea la pestaña origen de ServiceNow para listar tickets y extraer sus datos clave.
        """
        expr = """
        (function() {
            let logs = [];
            let foundTickets = [];
            let totalQueueCount = "";

            logs.push("URL pestaña origen: " + window.location.href);

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
                                logs.push("iFrame detectado: " + (child.id || child.name || 'sin_id'));
                            }
                        } catch(err) {}
                    }
                    collectShadowRoots(child);
                }
            }

            collectShadowRoots(document.body || document.documentElement);

            let ticketRegex = /\\b(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})\\b/gi;

            for (let root of allRoots) {
                let textContent = root.textContent || (root.body ? root.body.innerText : "") || "";
                if (textContent) allTexts.push(textContent);

                let qMatch = textContent.match(/\\b(\\d+)\\s+to\\s+(\\d+)\\s+of\\s+(\\d+)\\b/i) ||
                             textContent.match(/\\b(\\d+)\\s+of\\s+(\\d+)\\b/i) ||
                             textContent.match(/\\bTotal:\\s*(\\d+)\\b/i);
                if (qMatch && !totalQueueCount) {
                    totalQueueCount = qMatch[0];
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
                            let sysId = el.getAttribute("sys_id") || (row ? row.getAttribute("sys_id") : "") || "";
                            let href = el.getAttribute("href") || "";

                            if (row) {
                                desc = (row.innerText || "").replace(num, "").trim().substring(0, 140);
                            }
                            foundTickets.push({
                                number: num,
                                description: desc || "Ticket en lista",
                                sys_id: sysId,
                                href: href
                            });
                        }
                    }
                }
            }

            if (foundTickets.length === 0) {
                let fullJoinedText = allTexts.join("\\n");
                let matches = fullJoinedText.match(ticketRegex);
                if (matches) {
                    for (let rawNum of matches) {
                        let num = rawNum.toUpperCase();
                        if (!foundTickets.some(t => t.number === num)) {
                            foundTickets.push({
                                number: num,
                                description: "Ticket detectado en texto",
                                sys_id: "",
                                href: ""
                            });
                        }
                    }
                }
            }

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
            return {"tickets": [], "totalQueueText": "0 tickets", "logs": []}
        except Exception as ex:
            return {"tickets": [], "totalQueueText": "0 tickets", "logs": [str(ex)]}

    def locate_and_open_ticket(self, ticket_number: str) -> Dict[str, Any]:
        """
        PASO 2: Apertura EXACTA UNA SOLA VEZ en la PESTAÑA ORIGEN del Navegador:
        - Si el elemento tiene un href válido de ServiceNow, se navega solo por ese medio.
        - Si no tiene href, se ejecuta únicamente el clic en el elemento.
        - Evita doble activación (un solo disparo garantizado).
        """
        num_clean = ticket_number.strip().upper()
        self.bring_window_to_front()

        expr = f"""
        (function() {{
            let targetNum = "{num_clean}";
            let allRoots = [];

            function scanNode(node) {{
                if (!node) return;
                allRoots.push(node);
                if (node.shadowRoot) scanNode(node.shadowRoot);
                let children = node.children || [];
                for (let i = 0; i < children.length; i++) {{
                    let child = children[i];
                    if (child.tagName && child.tagName.toLowerCase() === 'iframe') {{
                        try {{
                            if (child.contentDocument) scanNode(child.contentDocument);
                        }} catch(e) {{}}
                    }}
                    scanNode(child);
                }}
            }}

            scanNode(document.body || document.documentElement);

            let matchFound = null;

            for (let root of allRoots) {{
                let candidates = Array.from(root.querySelectorAll("a, td, span, tr, [role='gridcell'], div"));
                for (let el of candidates) {{
                    let txt = (el.innerText || el.textContent || "").trim().toUpperCase();
                    let href = el.getAttribute ? (el.getAttribute("href") || "") : "";

                    if (txt === targetNum || (txt.startsWith(targetNum) && txt.length < targetNum.length + 3) || href.includes(targetNum)) {{
                        let clickable = (el.tagName && el.tagName.toLowerCase() === 'a') ? el : (el.querySelector("a") || el);

                        let targetHref = clickable.getAttribute ? (clickable.getAttribute("href") || "") : "";
                        let sysId = clickable.getAttribute("sys_id") || el.getAttribute("sys_id") || "";
                        let tr = clickable.closest("tr");
                        if (!sysId && tr) sysId = tr.getAttribute("sys_id") || "";

                        if (clickable.scrollIntoView) {{
                            clickable.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }}

                        // ESTRATEGIA 1: Si hay URL directa de ServiceNow, navegar de forma única
                        if (targetHref && targetHref !== "#" && !targetHref.startsWith("javascript:void")) {{
                            try {{
                                let ifr = document.querySelector("iframe#gsft_main");
                                if (ifr && ifr.contentWindow) {{
                                    ifr.contentWindow.location.href = targetHref;
                                }} else {{
                                    window.location.href = targetHref;
                                }}
                                return {{
                                    found: true,
                                    ticket: targetNum,
                                    action: "single_href_nav",
                                    href: targetHref
                                }};
                            }} catch(e) {{}}
                        }}

                        // ESTRATEGIA 2: Si tiene sys_id identificado
                        if (sysId) {{
                            let tablePrefix = targetNum.startsWith("INC") ? "incident" : (targetNum.startsWith("SCTASK") ? "sc_task" : "task");
                            let directUrl = tablePrefix + ".do?sys_id=" + sysId;
                            try {{
                                let ifr = document.querySelector("iframe#gsft_main");
                                if (ifr && ifr.contentWindow) {{
                                    ifr.contentWindow.location.href = directUrl;
                                }} else {{
                                    window.location.href = directUrl;
                                }}
                                return {{
                                    found: true,
                                    ticket: targetNum,
                                    action: "single_sysid_nav",
                                    url: directUrl
                                }};
                            }} catch(e) {{}}
                        }}

                        // ESTRATEGIA 3: Clic único y enfocado
                        try {{
                            clickable.focus();
                            clickable.click();
                            return {{
                                found: true,
                                ticket: targetNum,
                                action: "single_dom_click"
                            }};
                        }} catch(e) {{}}

                        break;
                    }}
                }}
            }}

            return {{ found: false, ticket: targetNum }};
        }})();
        """
        try:
            res = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            result_obj = res.get("result", {})
            val = result_obj.get("value")
            if val is None and isinstance(result_obj.get("result"), dict):
                val = result_obj["result"].get("value")

            if isinstance(val, dict) and val.get("found"):
                print(f"[PASO 2] Ticket {num_clean} abierto (DISPARO ÚNICO): {val.get('action')}")
                return val
        except Exception as e:
            print(f"[CDP Native] Error al abrir ticket {ticket_number}: {e}")

        # Fallback único
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
