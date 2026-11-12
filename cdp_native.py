"""
cdp_native.py
Cliente nativo CDP (Chrome DevTools Protocol) ultra ligero y resiliente.
Apertura física de tickets directamente en la PESTAÑA ORIGEN del navegador:
1. Identifica el sys_id o la URL del formulario del ticket en ServiceNow.
2. Navega la pestaña origen directamente a la vista de edición del ticket.
3. Despacha comandos de navegación y activación de ventana en Chrome.
4. Soporte para simulación de clic de ratón por Playwright y coordenadas relativas.
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
        PASO 2: Apertura GARANTIZADA en la PESTAÑA ORIGEN del Navegador:
        1. Enfoca la ventana real del navegador.
        2. Localiza el ticket en la pestaña origen y extrae su sys_id o href.
        3. Si ServiceNow usa navegación AJAX o URL clásica (sc_task.do, incident.do, etc.),
           ejecuta la navegación en la pestaña origen sin depender de coordenadas erróneas.
        4. Si no hay URL directa, emite un clic por selector sobre el elemento que contiene el texto exacto.
        """
        num_clean = ticket_number.strip().upper()
        self.bring_window_to_front()

        expr = f"""
        (function() {{
            let targetNum = "{num_clean}";
            let allRoots = [];
            let logs = [];

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

                        // 1. Extraer destino de navegación real
                        let targetHref = clickable.getAttribute ? (clickable.getAttribute("href") || "") : "";
                        let onclick = clickable.getAttribute ? (clickable.getAttribute("onclick") || "") : "";
                        let sysId = clickable.getAttribute("sys_id") || el.getAttribute("sys_id") || "";
                        let tr = clickable.closest("tr");
                        if (!sysId && tr) sysId = tr.getAttribute("sys_id") || "";

                        // Hacer scroll para asegurar que el elemento esté en foco en la pestaña origen
                        if (clickable.scrollIntoView) {{
                            clickable.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }}

                        // DISPARAR CLICK DIRECTO EN EL NAVEGADOR
                        let clickTriggered = false;
                        try {{
                            clickable.focus();
                            clickable.click();
                            clickTriggered = true;
                        }} catch(e) {{}}

                        matchFound = {{
                            found: true,
                            ticket: targetNum,
                            tagName: clickable.tagName,
                            href: targetHref,
                            onclick: onclick,
                            sys_id: sysId,
                            clickTriggered: clickTriggered
                        }};
                        break;
                    }}
                }}
                if (matchFound) break;
            }}

            // Si encontramos href válido que no se haya abierto, forzar navegación de la página
            if (matchFound && matchFound.href && matchFound.href !== "#" && !matchFound.href.startsWith("javascript:void")) {{
                try {{
                    let docView = window;
                    let ifr = document.querySelector("iframe#gsft_main");
                    if (ifr && ifr.contentWindow) {{
                        ifr.contentWindow.location.href = matchFound.href;
                        matchFound.navMode = "iframe_location";
                    }} else {{
                        window.location.href = matchFound.href;
                        matchFound.navMode = "window_location";
                    }}
                }} catch(e) {{
                    matchFound.navError = e.message;
                }}
            }}

            // Si tenemos el sys_id y el prefijo de ticket (SCTASK -> sc_task.do, INC -> incident.do)
            if (matchFound && !matchFound.navMode && matchFound.sys_id) {{
                let tablePrefix = targetNum.startsWith("INC") ? "incident" : (targetNum.startsWith("SCTASK") ? "sc_task" : "task");
                let directUrl = tablePrefix + ".do?sys_id=" + matchFound.sys_id;
                try {{
                    let ifr = document.querySelector("iframe#gsft_main");
                    if (ifr && ifr.contentWindow) {{
                        ifr.contentWindow.location.href = directUrl;
                        matchFound.navMode = "sys_id_iframe_nav";
                    }} else {{
                        window.location.href = directUrl;
                        matchFound.navMode = "sys_id_window_nav";
                    }}
                }} catch(e) {{}}
            }}

            if (matchFound) return matchFound;
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
                print(f"[PASO 2] Ticket {num_clean} activado en la PESTAÑA ORIGEN:")
                print(f"  -> Método de navegación: {val.get('navMode', 'Clic Nativo en DOM')}")
                print(f"  -> Href: {val.get('href', 'N/A')} | Sys_ID: {val.get('sys_id', 'N/A')}")
                return val
        except Exception as e:
            print(f"[CDP Native] Error al abrir ticket {ticket_number}: {e}")

        # Fallback de clic por texto exacto
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
