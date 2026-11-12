"""
tab_engine.py
Motor de descubrimiento y control de pestañas vía Chrome DevTools Protocol (CDP).
Diseñado para entornos corporativos con persistencia de espejo (Screen Mirror):
- Mantiene la referencia de la pestaña seleccionada en st.session_state / memoria.
- Auto-reconexión si el socket de Playwright se desconecta o la página se refresca.
- Cache del último frame capturado para que la vista espejo NUNCA desaparezca.
- Captura directa vía CDP Page.captureScreenshot si el selector de Playwright se desvincula.
"""

import json
import time
import base64
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
        self.last_screenshot_bytes: Optional[bytes] = None

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
                if item.get("type") == "page":
                    tabs.append(TabInfo(
                        tab_id=item.get("id", ""),
                        title=item.get("title", "(Sin título)"),
                        url=item.get("url", ""),
                        ws_url=item.get("webSocketDebuggerUrl", "")
                    ))

            tabs.sort(key=lambda t: 0 if t.is_servicenow else 1)
            return tabs
        except Exception as e:
            print(f"[ERROR] Error al listar pestañas: {e}")
            return []

    def _ensure_browser_connected(self):
        """Conecta o reconecta Playwright a la instancia de Chrome/Edge vía CDP."""
        if not PLAYWRIGHT_AVAILABLE:
            return

        port = self.detect_active_port()
        if not port:
            return

        need_reconnect = False
        if self.playwright is None:
            self.playwright = sync_playwright().start()
            need_reconnect = True

        if self.browser is None or not self.browser.is_connected():
            need_reconnect = True

        if need_reconnect:
            try:
                self.browser = self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            except Exception as e:
                print(f"[WARN] Error al conectar Playwright: {e}")

    def _resolve_page(self) -> Optional[Any]:
        """Asegura que el objeto Page actual esté conectado y vivo."""
        try:
            if self.current_page and not self.current_page.is_closed():
                return self.current_page
        except Exception:
            pass

        self._ensure_browser_connected()
        if not self.browser or not self.current_tab_id:
            return None

        # Re-enlazar buscando por tab_id o URL
        tabs = self.list_tabs()
        target = next((t for t in tabs if t.tab_id == self.current_tab_id), None)

        try:
            for ctx in self.browser.contexts:
                for page in ctx.pages:
                    try:
                        if target and (target.url in page.url or page.url in target.url or target.title in page.title()):
                            self.current_page = page
                            return self.current_page
                    except Exception:
                        continue

            if self.browser.contexts and self.browser.contexts[0].pages:
                self.current_page = self.browser.contexts[0].pages[0]
                return self.current_page
        except Exception:
            pass

        return None

    def select_tab_by_id(self, tab_id: str) -> bool:
        """Selecciona y enlaza una pestaña específica por su ID de forma permanente."""
        self.current_tab_id = tab_id
        port = self.detect_active_port()

        if port:
            try:
                requests.get(f"http://127.0.0.1:{port}/json/activate/{tab_id}", timeout=1.5)
            except Exception:
                pass

        page = self._resolve_page()
        if page:
            try:
                page.bring_to_front()
            except Exception:
                pass

        # Tomar captura inicial para fijar el frame
        self.take_screenshot()
        return True

    def scroll(self, direction: str = "down", amount: int = 400) -> bool:
        """Realiza scroll hacia arriba o hacia abajo en la pestaña activa."""
        page = self._resolve_page()
        if not page:
            return False
        try:
            delta = amount if direction.lower() == "down" else -amount
            page.evaluate(f"window.scrollBy({{ top: {delta}, behavior: 'smooth' }});")
            time.sleep(0.15)
            self.take_screenshot()
            return True
        except Exception as e:
            print(f"[ERROR] Error al hacer scroll: {e}")
            return False

    def click_element(self, selector: str) -> bool:
        """Hace clic en un elemento CSS / XPath o texto en la pestaña activa."""
        page = self._resolve_page()
        if not page:
            return False
        try:
            if page.locator("iframe#gsft_main").count() > 0:
                frame = page.frame_locator("iframe#gsft_main")
                if frame.locator(selector).count() > 0:
                    frame.locator(selector).first.click(timeout=3000)
                    time.sleep(0.3)
                    self.take_screenshot()
                    return True

            page.locator(selector).first.click(timeout=3000)
            time.sleep(0.3)
            self.take_screenshot()
            return True
        except Exception as e:
            print(f"[ERROR] Error al hacer clic en {selector}: {e}")
            return False

    def reload(self) -> bool:
        """Recarga la pestaña activa."""
        page = self._resolve_page()
        if not page:
            return False
        try:
            page.reload()
            time.sleep(1.0)
            self.take_screenshot()
            return True
        except Exception as e:
            print(f"[ERROR] Error al recargar: {e}")
            return False

    def take_screenshot(self) -> Optional[bytes]:
        """
        Obtiene una captura de pantalla en bytes.
        Si la captura en vivo tarda o falla temporalmente, devuelve el último frame en caché
        para que la vista espejo NUNCA desaparezca de la pantalla.
        """
        page = self._resolve_page()
        if page:
            try:
                frame = page.screenshot(type="jpeg", quality=75, timeout=2500)
                if frame:
                    self.last_screenshot_bytes = frame
                    return frame
            except Exception as e:
                # Si falló la captura fresca, no borrar el frame previo
                pass

        # Fallback al último frame capturado
        return self.last_screenshot_bytes
