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

    def extract_ticket_form_data(self) -> Dict[str, str]:
        """
        PASO 3: Extrae los campos clave del formulario de ServiceNow actualmente abierto:
        - Number
        - State
        - Affected user
        - Channel
        - Reported by
        - Impact
        - Category
        - Urgency
        - Subcategory
        - Priority
        - Service
        - Assignment group
        - Configuration Item
        - Assigned to
        - Short description
        - Description
        """
        expr = """
        (function() {
            let result = {
                "Number": "",
                "State": "",
                "Affected user": "",
                "Channel": "",
                "Reported by": "",
                "Impact": "",
                "Category": "",
                "Urgency": "",
                "Subcategory": "",
                "Priority": "",
                "Service": "",
                "Assignment group": "",
                "Configuration Item": "",
                "Assigned to": "",
                "Short description": "",
                "Description": ""
            };

            // 1. Intentar leer vía g_form de ServiceNow si está disponible en iframe o window
            let gForm = null;
            try {
                let ifr = document.querySelector("iframe#gsft_main");
                if (ifr && ifr.contentWindow && ifr.contentWindow.g_form) {
                    gForm = ifr.contentWindow.g_form;
                } else if (window.g_form) {
                    gForm = window.g_form;
                }
            } catch(e) {}

            if (gForm) {
                try {
                    let getGFVal = function(fieldName) {
                        try {
                            if (gForm.getDisplayBox && gForm.getDisplayBox(fieldName) && gForm.getDisplayBox(fieldName).value) {
                                return gForm.getDisplayBox(fieldName).value.trim();
                            }
                            if (gForm.getDisplayValue) {
                                let dv = gForm.getDisplayValue(fieldName);
                                if (dv) return dv.trim();
                            }
                            if (gForm.getValue) {
                                let v = gForm.getValue(fieldName);
                                if (v) return v.trim();
                            }
                        } catch(err) {}
                        return "";
                    };

                    result["Number"] = getGFVal("number");
                    result["State"] = getGFVal("state");
                    result["Affected user"] = getGFVal("caller_id") || getGFVal("u_affected_user") || getGFVal("requested_for");
                    result["Channel"] = getGFVal("contact_type") || getGFVal("channel");
                    result["Reported by"] = getGFVal("opened_by") || getGFVal("u_reported_by");
                    result["Impact"] = getGFVal("impact");
                    result["Category"] = getGFVal("category");
                    result["Urgency"] = getGFVal("urgency");
                    result["Subcategory"] = getGFVal("subcategory");
                    result["Priority"] = getGFVal("priority");
                    result["Service"] = getGFVal("business_service") || getGFVal("service");
                    result["Assignment group"] = getGFVal("assignment_group");
                    result["Configuration Item"] = getGFVal("cmdb_ci") || getGFVal("configuration_item");
                    result["Assigned to"] = getGFVal("assigned_to");
                    result["Short description"] = getGFVal("short_description");
                    result["Description"] = getGFVal("description");
                } catch(e) {}
            }

            // 2. Escaneo DOM exhaustivo (Polaris Next Experience + iframe#gsft_main + Shadow DOM)
            let allRoots = [];
            function scanNode(node) {
                if (!node) return;
                allRoots.push(node);
                if (node.shadowRoot) scanNode(node.shadowRoot);
                let children = node.children || [];
                for (let i = 0; i < children.length; i++) {
                    let child = children[i];
                    if (child.tagName && child.tagName.toLowerCase() === 'iframe') {
                        try {
                            if (child.contentDocument) scanNode(child.contentDocument);
                        } catch(e) {}
                    }
                    scanNode(child);
                }
            }
            scanNode(document.body || document.documentElement);

            function getElementVal(el) {
                if (!el) return "";
                let tag = el.tagName ? el.tagName.toLowerCase() : "";
                if (tag === 'select') {
                    let opt = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
                    return opt ? (opt.text || opt.value || "").trim() : "";
                }
                if (tag === 'textarea' || tag === 'input') {
                    return (el.value || "").trim();
                }
                return (el.innerText || el.textContent || "").trim();
            }

            function extractField(selectors, labelRegexes) {
                for (let root of allRoots) {
                    // Por selectores CSS
                    for (let sel of selectors) {
                        try {
                            let el = root.querySelector(sel);
                            if (el) {
                                let v = getElementVal(el);
                                if (v) return v;
                            }
                        } catch(e) {}
                    }

                    // Por texto de etiqueta (Label)
                    try {
                        let labels = Array.from(root.querySelectorAll("label, span.label-text, div.label, span[id*='label']"));
                        for (let lbl of labels) {
                            let txt = (lbl.innerText || lbl.textContent || "").trim();
                            for (let pat of labelRegexes) {
                                if (pat.test(txt)) {
                                    let forId = lbl.getAttribute("for");
                                    if (forId) {
                                        let disp = root.querySelector("[id='sys_display." + forId + "']");
                                        if (disp && disp.value) return disp.value.trim();
                                        let target = root.querySelector("[id='" + forId + "']");
                                        if (target) {
                                            let v = getElementVal(target);
                                            if (v) return v;
                                        }
                                    }
                                    let container = lbl.closest(".form-group, .form-field, tr, div.row, div[role='row']");
                                    if (container) {
                                        let disp = container.querySelector("input[id*='sys_display.'], input[name*='sys_display.']");
                                        if (disp && disp.value) return disp.value.trim();
                                        let el = container.querySelector("select, textarea, input:not([type='hidden']), span.form-control-static, p.form-control-static, span.sn-widget-read-only");
                                        if (el) {
                                            let v = getElementVal(el);
                                            if (v) return v;
                                        }
                                    }
                                }
                            }
                        }
                    } catch(e) {}
                }
                return "";
            }

            // Mapeo de campos
            let fieldsMap = [
                { key: "Number", selectors: ["input[id*='.number']", "input[name*='.number']", "input[id*='sys_readonly.'][id*='.number']", "[data-field='number']"], labels: [/^Number/i, /^Número/i] },
                { key: "State", selectors: ["select[id*='.state']", "select[name*='.state']", "input[id*='.state']", "[data-field='state']"], labels: [/^State/i, /^Estado/i] },
                { key: "Affected user", selectors: ["input[id*='sys_display.'][id*='caller_id']", "input[id*='sys_display.'][id*='u_affected_user']", "input[id*='caller_id']", "input[id*='u_affected_user']", "[data-field='caller_id']", "[data-field='u_affected_user']"], labels: [/Affected user/i, /^Caller/i, /Usuario afectado/i, /^Solicitante/i] },
                { key: "Channel", selectors: ["select[id*='.contact_type']", "select[name*='.contact_type']", "select[id*='.channel']", "input[id*='.contact_type']", "[data-field='contact_type']"], labels: [/^Channel/i, /^Contact type/i, /^Canal/i, /^Tipo de contacto/i] },
                { key: "Reported by", selectors: ["input[id*='sys_display.'][id*='opened_by']", "input[id*='sys_display.'][id*='u_reported_by']", "input[id*='.opened_by']", "input[id*='.u_reported_by']", "[data-field='opened_by']"], labels: [/Reported by/i, /Opened by/i, /Reportado por/i, /Abierto por/i] },
                { key: "Impact", selectors: ["select[id*='.impact']", "input[id*='.impact']", "[data-field='impact']"], labels: [/^Impact/i, /^Impacto/i] },
                { key: "Category", selectors: ["select[id*='.category']", "input[id*='.category']", "[data-field='category']"], labels: [/^Category/i, /^Categoría/i] },
                { key: "Urgency", selectors: ["select[id*='.urgency']", "input[id*='.urgency']", "[data-field='urgency']"], labels: [/^Urgency/i, /^Urgencia/i] },
                { key: "Subcategory", selectors: ["select[id*='.subcategory']", "input[id*='.subcategory']", "[data-field='subcategory']"], labels: [/^Subcategory/i, /^Subcategoría/i] },
                { key: "Priority", selectors: ["select[id*='.priority']", "input[id*='.priority']", "p[id*='.priority']", "[data-field='priority']"], labels: [/^Priority/i, /^Prioridad/i] },
                { key: "Service", selectors: ["input[id*='sys_display.'][id*='business_service']", "input[id*='sys_display.'][id*='service']", "input[id*='.business_service']", "input[id*='.service']", "[data-field='business_service']"], labels: [/^Service/i, /^Business Service/i, /^Servicio/i] },
                { key: "Assignment group", selectors: ["input[id*='sys_display.'][id*='assignment_group']", "input[name*='assignment_group']", "[data-field='assignment_group']"], labels: [/Assignment group/i, /Grupo de asignación/i] },
                { key: "Configuration Item", selectors: ["input[id*='sys_display.'][id*='cmdb_ci']", "input[id*='sys_display.'][id*='configuration_item']", "input[id*='.cmdb_ci']", "[data-field='cmdb_ci']"], labels: [/Configuration Item/i, /Configuración ID/i, /Elemento de configuración/i, /^CI/i] },
                { key: "Assigned to", selectors: ["input[id*='sys_display.'][id*='assigned_to']", "input[name*='assigned_to']", "[data-field='assigned_to']"], labels: [/Assigned to/i, /Asignado a/i] },
                { key: "Short description", selectors: ["input[id*='.short_description']", "input[name*='short_description']", "[data-field='short_description']"], labels: [/Short description/i, /Descripción corta/i, /Resumen/i] },
                { key: "Description", selectors: ["textarea[id*='.description']", "textarea[name*='description']", "[data-field='description']"], labels: [/^Description$/i, /^Descripción$/i] }
            ];

            for (let f of fieldsMap) {
                if (!result[f.key]) {
                    result[f.key] = extractField(f.selectors, f.labels);
                }
            }

            // Fallback para Number desde el título de la página
            if (!result["Number"]) {
                let docTitle = document.title || "";
                let m = docTitle.match(/\\b(INC\\d{5,10}|SCTASK\\d{5,10}|TASK\\d{5,10}|RITM\\d{5,10}|REQ\\d{5,10})\\b/i);
                if (m) {
                    result["Number"] = m[1].toUpperCase();
                }
            }

            return result;
        })();
        """
        try:
            res = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            result_obj = res.get("result", {})
            val = result_obj.get("value")
            if val is None and isinstance(result_obj.get("result"), dict):
                val = result_obj["result"].get("value")

            if isinstance(val, dict):
                print(f"[CDP Native] Formulario extraído: Number={val.get('Number')} | State={val.get('State')} | Priority={val.get('Priority')}")
                return val
        except Exception as e:
            print(f"[CDP Native] Error al extraer formulario: {e}")

        return {
            "Number": "", "State": "", "Affected user": "", "Channel": "", "Reported by": "",
            "Impact": "", "Category": "", "Urgency": "", "Subcategory": "", "Priority": "",
            "Service": "", "Assignment group": "", "Configuration Item": "", "Assigned to": "",
            "Short description": "", "Description": ""
        }

    def switch_form_tab(self, tab_name: str = "User Submitted Fields") -> bool:
        """
        Localiza y hace clic en una pestaña inferior del formulario de ServiceNow
        (ej: 'User Submitted Fields', 'Notes', 'Related Records', 'Other Information', etc.)
        """
        tab_clean = tab_name.replace('"', '\\"').replace("'", "\\'")
        js_code = """
        (function() {
            let targetTab = "TARGET_TAB_PLACEHOLDER".toLowerCase();
            let allRoots = [];
            function scanNode(node) {
                if (!node) return;
                allRoots.push(node);
                if (node.shadowRoot) scanNode(node.shadowRoot);
                let children = node.children || [];
                for (let i = 0; i < children.length; i++) {
                    let child = children[i];
                    if (child.tagName && child.tagName.toLowerCase() === 'iframe') {
                        try {
                            if (child.contentDocument) scanNode(child.contentDocument);
                        } catch(e) {}
                    }
                    scanNode(child);
                }
            }
            scanNode(document.body || document.documentElement);

            for (let root of allRoots) {
                let candidates = Array.from(root.querySelectorAll(
                    "[role='tab'], .tab_caption_text, .tabs2_tab, span.tab_header, div.tab_header, button, a, span, [data-tab-name], [data-section-name]"
                ));

                for (let el of candidates) {
                    let txt = (el.innerText || el.textContent || "").trim().toLowerCase();
                    let dataTab = (el.getAttribute("data-tab-name") || el.getAttribute("data-section-name") || "").toLowerCase();

                    if (txt === targetTab || txt.includes(targetTab) || (dataTab && dataTab.includes(targetTab.replace(/\\s+/g, '_')))) {
                        let clickable = el;
                        let tabParent = el.closest("[role='tab'], .tabs2_tab, .tab_header, button, a");
                        if (tabParent) clickable = tabParent;

                        if (clickable.scrollIntoView) {
                            clickable.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }

                        clickable.focus && clickable.focus();
                        clickable.click();

                        try {
                            clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                            clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                            clickable.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                        } catch(e) {}

                        return true;
                    }
                }
            }
            return false;
        })();
        """.replace("TARGET_TAB_PLACEHOLDER", tab_clean)

        try:
            res = self.send("Runtime.evaluate", {"expression": js_code, "returnByValue": True})
            result_obj = res.get("result", {})
            val = result_obj.get("value")
            if val is True:
                print(f"[CDP Native] Pestaña '{tab_name}' activada con éxito.")
                return True
        except Exception as e:
            print(f"[CDP Native] Error al cambiar a pestaña '{tab_name}': {e}")
        return False

    def extract_user_submitted_fields(self) -> Dict[str, str]:
        """
        Extrae los campos dentro de la pestaña 'User Submitted Fields':
        - 'More Information, Please Provide a Detailed description of the issue. If no less Than Fifty Words'
        - 'User email used to login'
        """
        js_code = """
        (function() {
            let res = {
                "More Information (Issue Description)": "",
                "User email used to login": ""
            };

            let allRoots = [];
            function scanNode(node) {
                if (!node) return;
                allRoots.push(node);
                if (node.shadowRoot) scanNode(node.shadowRoot);
                let children = node.children || [];
                for (let i = 0; i < children.length; i++) {
                    let child = children[i];
                    if (child.tagName && child.tagName.toLowerCase() === 'iframe') {
                        try {
                            if (child.contentDocument) scanNode(child.contentDocument);
                        } catch(e) {}
                    }
                    scanNode(child);
                }
            }
            scanNode(document.body || document.documentElement);

            function getElementVal(el) {
                if (!el) return "";
                let tag = el.tagName ? el.tagName.toLowerCase() : "";
                if (tag === 'select') {
                    let opt = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
                    return opt ? (opt.text || opt.value || "").trim() : "";
                }
                if (tag === 'textarea' || tag === 'input') {
                    return (el.value || "").trim();
                }
                return (el.innerText || el.textContent || "").trim();
            }

            // Expresiones regulares para los dos campos requeridos
            let moreInfoRegex = /(more\\s*information|please\\s*provide\\s*a\\s*.*description|no\\s*less\\s*than\\s*(fifty|50)\\s*words|detailed\\s*description)/i;
            let userEmailRegex = /(user\\s*email|email\\s*used\\s*to\\s*login|used\\s*to\\s*login|email.*login)/i;

            for (let root of allRoots) {
                let elements = Array.from(root.querySelectorAll("label, span.label-text, th, td, div.form-group, div.form-field, div, span, tr"));

                for (let el of elements) {
                    let txt = (el.innerText || el.textContent || "").trim();

                    // Campo 1: More Information
                    if (!res["More Information (Issue Description)"] && moreInfoRegex.test(txt)) {
                        let forId = el.getAttribute ? el.getAttribute("for") : null;
                        if (forId) {
                            let target = root.querySelector("[id='" + forId + "']");
                            let v = getElementVal(target);
                            if (v && v !== txt) res["More Information (Issue Description)"] = v;
                        }
                        if (!res["More Information (Issue Description)"]) {
                            let container = el.closest(".form-group, .form-field, tr, div.row, div");
                            if (container) {
                                let inp = container.querySelector("textarea, input:not([type='hidden']), span.form-control-static, p.form-control-static");
                                let v = getElementVal(inp);
                                if (v && v !== txt) res["More Information (Issue Description)"] = v;
                            }
                        }
                        if (!res["More Information (Issue Description)"]) {
                            let nextEl = el.nextElementSibling;
                            if (nextEl) {
                                let inp = nextEl.querySelector("textarea, input") || nextEl;
                                let v = getElementVal(inp);
                                if (v && v !== txt) res["More Information (Issue Description)"] = v;
                            }
                        }
                    }

                    // Campo 2: User email used to login
                    if (!res["User email used to login"] && userEmailRegex.test(txt)) {
                        let forId = el.getAttribute ? el.getAttribute("for") : null;
                        if (forId) {
                            let disp = root.querySelector("[id='sys_display." + forId + "']");
                            if (disp && disp.value) res["User email used to login"] = disp.value.trim();
                            let target = root.querySelector("[id='" + forId + "']");
                            let v = getElementVal(target);
                            if (v && v !== txt) res["User email used to login"] = v;
                        }
                        if (!res["User email used to login"]) {
                            let container = el.closest(".form-group, .form-field, tr, div.row, div");
                            if (container) {
                                let disp = container.querySelector("input[id*='sys_display.']");
                                if (disp && disp.value) res["User email used to login"] = disp.value.trim();
                                let inp = container.querySelector("input:not([type='hidden']), span.form-control-static");
                                let v = getElementVal(inp);
                                if (v && v !== txt) res["User email used to login"] = v;
                            }
                        }
                        if (!res["User email used to login"]) {
                            let nextEl = el.nextElementSibling;
                            if (nextEl) {
                                let inp = nextEl.querySelector("input") || nextEl;
                                let v = getElementVal(inp);
                                if (v && v !== txt) res["User email used to login"] = v;
                            }
                        }
                    }
                }
            }

            // Fallback de email por regex si se encuentra en algún campo de texto
            if (!res["User email used to login"]) {
                for (let root of allRoots) {
                    let inputs = Array.from(root.querySelectorAll("input[type='text'], input[type='email'], span.form-control-static"));
                    for (let inp of inputs) {
                        let val = getElementVal(inp);
                        if (val && /^[\\w\\.-]+@[\\w\\.-]+\\.[a-zA-Z]{{2,}}$/.test(val)) {{
                            res["User email used to login"] = val;
                            break;
                        }}
                    }
                    if (res["User email used to login"]) break;
                }
            }

            return res;
        })();
        """
        try:
            res = self.send("Runtime.evaluate", {"expression": js_code, "returnByValue": True})
            result_obj = res.get("result", {})
            val = result_obj.get("value")
            if val is None and isinstance(result_obj.get("result"), dict):
                val = result_obj["result"].get("value")

            if isinstance(val, dict):
                print(f"[CDP Native] User Submitted Fields extraídos: Email={val.get('User email used to login')} | Info={val.get('More Information (Issue Description)')[:40] if val.get('More Information (Issue Description)') else ''}")
                return val
        except Exception as e:
            print(f"[CDP Native] Error al extraer User Submitted Fields: {e}")

        return {"More Information (Issue Description)": "", "User email used to login": ""}
