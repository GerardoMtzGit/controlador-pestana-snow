"""
tab_engine.py
Motor de descubrimiento y control de pestañas vía Chrome DevTools Protocol (CDP).
Diseñado para entornos corporativos:
- Escaneo multirango de puertos CDP (9222, 9223, etc.).
- Soporte para pestañas principales y de ServiceNow en segundo plano.
- Fallback a HTTP CDP si el WebSocket de Playwright tiene restricciones.
"""

import json
import time
import requests
from typing import List, Dict, Any, Optional

try:
    from playwright.sync_api import sync_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class TabInfo:
    def __init__(self, tab_id: str, title: str, url: str, ws_url: str = ""):
        self.tab_id = tab_id
        self.title = title or "(Pestaña sin título)"
        self.url = url or ""
        self.ws_url = ws_url

    @property
    def is_servicenow(self) -> bool:
        low_url = self.url.lower()
        low_title = self.title.lower()
        return any(k in low_url or k in low_title for k in [
            "service-now", "servicenow", "incident", "task", "sysparm", "myschneider", "sn_customerservice"
        ])

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.tab_id,
            "title": self.title,
            "url": self.url,
            "is_snow": str(self.is_servicenow)
        }

    def __repr__(self):
        return f"<Tab {self.title[:30]} ({self.url[:30]})>"


class CDPBrowserController:
    def __init__(self, ports: Optional[List[int]] = None):
        self.candidate_ports = ports or [9222, 9223, 9224]
        self.active_port: Optional[int] = None
        self.playwright = None
        self.browser: Optional[Any] = None
        self.current_page: Optional[Any] = None
        self.current_tab_id: Optional[str] = None

    def detect_active_port(self) -> Optional[int]:
        """Busca cuál puerto de depuración está activo en la máquina."""
        for p in self.candidate_ports:
            try:
                r = requests.get(f"http://127.0.0.1:{p}/json/version", timeout=0.8)
                if r.status_code == 200:
                    self.active_port = p
                    return p
            except Exception:
                continue
        return None

    def is_cdp_available(self) -> bool:
        """Verifica si el navegador está respondiendo en el puerto CDP detectado."""
        port = self.detect_active_port()
        return port is not None

    def list_tabs(self) -> List[TabInfo]:
        """Obtiene la lista de todas las pestañas abiertas en el navegador."""
        port = self.detect_active_port()
        if not port:
            return []

        try:
            r = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=1.5)
            data = r.json()
            tabs = []
            for item in data:
                # Incluir tipo 'page'
                if item.get("type") == "page":
                    tabs.append(TabInfo(
                        tab_id=item.get("id", ""),
                        title=item.get("title", "(Sin título)"),
                        url=item.get("url", ""),
                        ws_url=item.get("webSocketDebuggerUrl", "")
                    ))

            # Ordenar para que las pestañas de ServiceNow aparezcan primero
            tabs.sort(key=lambda t: 0 if t.is_servicenow else 1)
            return tabs
        except Exception as e:
            print(f"[ERROR] Error al listar pestañas: {e}")
            return []

    def _ensure_browser_connected(self):
        """Conecta Playwright a la instancia de Chrome/Edge vía CDP."""
        if not PLAYWRIGHT_AVAILABLE:
            return

        port = self.detect_active_port()
        if not port:
            raise ConnectionError("No se detectó ningún navegador con depuración.")

        if self.playwright is None:
            self.playwright = sync_playwright().start()

        if self.browser is None or not self.browser.is_connected():
            self.browser = self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")

    def select_tab_by_id(self, tab_id: str) -> bool:
        """Selecciona y enlaza una pestaña específica por su ID."""
        port = self.detect_active_port()
        if not port:
            return False

        try:
            # 1. Traer la pestaña al frente en Windows vía HTTP CDP
            try:
                requests.get(f"http://127.0.0.1:{port}/json/activate/{tab_id}", timeout=1.5)
            except Exception:
                pass

            self._ensure_browser_connected()
            tabs = self.list_tabs()
            target = next((t for t in tabs if t.tab_id == tab_id), None)

            # 2. Localizar el objeto Page en Playwright
            if self.browser:
                for ctx in self.browser.contexts:
                    for page in ctx.pages:
                        try:
                            if target and (target.url in page.url or page.url in target.url or target.title in page.title()):
                                self.current_page = page
                                self.current_tab_id = tab_id
                                page.bring_to_front()
                                return True
                        except Exception:
                            continue

                # Si no hubo coincidencia estricta pero hay páginas
                if self.browser.contexts and self.browser.contexts[0].pages:
                    self.current_page = self.browser.contexts[0].pages[0]
                    self.current_tab_id = tab_id
                    return True

            self.current_tab_id = tab_id
            return True
        except Exception as e:
            print(f"[ERROR] No se pudo seleccionar la pestaña {tab_id}: {e}")
            self.current_tab_id = tab_id
            return True

    def scroll(self, direction: str = "down", amount: int = 400) -> bool:
        """Realiza scroll hacia arriba o hacia abajo en la pestaña activa."""
        if not self.current_page:
            return False
        try:
            delta = amount if direction.lower() == "down" else -amount
            self.current_page.evaluate(f"window.scrollBy({{ top: {delta}, behavior: 'smooth' }});")
            return True
        except Exception as e:
            print(f"[ERROR] Error al hacer scroll: {e}")
            return False

    def click_element(self, selector: str) -> bool:
        """Hace clic en un elemento CSS / XPath o texto en la pestaña activa."""
        if not self.current_page:
            return False
        try:
            # Soportar ServiceNow iFrame (gsft_main)
            if self.current_page.locator("iframe#gsft_main").count() > 0:
                frame = self.current_page.frame_locator("iframe#gsft_main")
                if frame.locator(selector).count() > 0:
                    frame.locator(selector).first.click(timeout=3000)
                    return True

            self.current_page.locator(selector).first.click(timeout=3000)
            return True
        except Exception as e:
            print(f"[ERROR] Error al hacer clic en {selector}: {e}")
            return False

    def reload(self) -> bool:
        """Recarga la pestaña activa."""
        if not self.current_page:
            return False
        try:
            self.current_page.reload()
            return True
        except Exception as e:
            print(f"[ERROR] Error al recargar: {e}")
            return False

    def take_screenshot(self) -> Optional[bytes]:
        """Obtiene una captura de pantalla en bytes de la pestaña actual."""
        if not self.current_page:
            return None
        try:
            return self.current_page.screenshot(type="jpeg", quality=75)
        except Exception as e:
            print(f"[ERROR] Error al capturar pantalla: {e}")
            return None
