"""
tab_engine.py
Motor de descubrimiento y control de pestañas vía Chrome DevTools Protocol (CDP).
Permite listar pestañas abiertas, seleccionar una, hacer scroll, clics, escribir texto
y obtener capturas de pantalla para visualizarlas en la interfaz.
"""

import json
import time
import requests
from typing import List, Dict, Any, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


class TabInfo:
    def __init__(self, tab_id: str, title: str, url: str, ws_url: str = ""):
        self.tab_id = tab_id
        self.title = title
        self.url = url
        self.ws_url = ws_url

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.tab_id,
            "title": self.title,
            "url": self.url
        }

    def __repr__(self):
        return f"<Tab {self.title[:30]} ({self.url[:40]})>"


class CDPBrowserController:
    def __init__(self, port: int = 9222):
        self.port = port
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.current_page: Optional[Page] = None
        self.current_tab_id: Optional[str] = None

    def is_cdp_available(self) -> bool:
        """Verifica si el navegador está respondiendo en el puerto CDP."""
        try:
            r = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=1.5)
            return r.status_code == 200
        except Exception:
            return False

    def list_tabs(self) -> List[TabInfo]:
        """Obtiene la lista de todas las pestañas abiertas en el navegador."""
        if not self.is_cdp_available():
            return []
        try:
            r = requests.get(f"http://127.0.0.1:{self.port}/json/list", timeout=2.0)
            data = r.json()
            tabs = []
            for item in data:
                # Filtrar solo páginas web reales (excluir service workers, extensions, etc.)
                if item.get("type") == "page":
                    tabs.append(TabInfo(
                        tab_id=item.get("id", ""),
                        title=item.get("title", "(Sin título)"),
                        url=item.get("url", ""),
                        ws_url=item.get("webSocketDebuggerUrl", "")
                    ))
            return tabs
        except Exception as e:
            print(f"[ERROR] Error al listar pestañas: {e}")
            return []

    def _ensure_browser_connected(self):
        """Conecta Playwright a la instancia de Chrome/Edge vía CDP."""
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        if self.browser is None or not self.browser.is_connected():
            self.browser = self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")

    def select_tab_by_id(self, tab_id: str) -> bool:
        """Selecciona y enlaza una pestaña específica por su ID."""
        try:
            self._ensure_browser_connected()
            # Activar en el navegador vía endpoint CDP
            try:
                requests.get(f"http://127.0.0.1:{self.port}/json/activate/{tab_id}", timeout=1.5)
            except Exception:
                pass

            # Encontrar el objeto Page correspondiente en Playwright
            for ctx in self.browser.contexts:
                for page in ctx.pages:
                    try:
                        # Si coincide la URL o el título
                        tabs = self.list_tabs()
                        target = next((t for t in tabs if t.tab_id == tab_id), None)
                        if target and (target.url in page.url or page.url in target.url):
                            self.current_page = page
                            self.current_tab_id = tab_id
                            page.bring_to_front()
                            return True
                    except Exception:
                        continue

            # Fallback: tomar la primera página activa si no hubo match estricto
            if self.browser.contexts and self.browser.contexts[0].pages:
                self.current_page = self.browser.contexts[0].pages[0]
                self.current_tab_id = tab_id
                self.current_page.bring_to_front()
                return True

            return False
        except Exception as e:
            print(f"[ERROR] No se pudo seleccionar la pestaña {tab_id}: {e}")
            return False

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
            # Intentar click directo o dentro de iFrame (común en ServiceNow)
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

    def click_at_coordinates(self, x: int, y: int) -> bool:
        """Hace clic en coordenadas absolutas de la página."""
        if not self.current_page:
            return False
        try:
            self.current_page.mouse.click(x, y)
            return True
        except Exception as e:
            print(f"[ERROR] Error al hacer clic en ({x}, {y}): {e}")
            return False

    def type_text(self, selector: str, text: str) -> bool:
        """Escribe texto en un campo de entrada."""
        if not self.current_page:
            return False
        try:
            if self.current_page.locator("iframe#gsft_main").count() > 0:
                frame = self.current_page.frame_locator("iframe#gsft_main")
                if frame.locator(selector).count() > 0:
                    frame.locator(selector).first.fill(text)
                    return True

            self.current_page.locator(selector).first.fill(text)
            return True
        except Exception as e:
            print(f"[ERROR] Error al escribir texto: {e}")
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

    def close(self):
        """Cierra la conexión CDP con Playwright sin cerrar el navegador del usuario."""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass

