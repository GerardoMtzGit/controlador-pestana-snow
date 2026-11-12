"""
tab_engine.py
Motor híbrido de descubrimiento y control de pestañas vía Chrome DevTools Protocol (CDP).
Arquitectura ultra resiliente con detección, logging y apertura automática de tickets.
"""

import json
import time
import requests
from typing import List, Dict, Any, Optional
from cdp_native import CDPNativeClient


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
        self.current_tab_id: Optional[str] = None
        self.native_client: Optional[CDPNativeClient] = None
        self.last_screenshot_bytes: Optional[bytes] = None

    def detect_active_port(self) -> Optional[int]:
        """Busca cuál puerto de depuración está activo en la máquina."""
        for p in self.candidate_ports:
            try:
                r = requests.get(f"http://127.0.0.1:{p}/json/version", timeout=0.6)
                if r.status_code == 200:
                    self.active_port = p
                    return p
            except Exception:
                continue
        return None

    def is_cdp_available(self) -> bool:
        """Verifica si el navegador está respondiendo en el puerto CDP detectado."""
        return self.detect_active_port() is not None

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

    def _get_active_native_client(self) -> Optional[CDPNativeClient]:
        """Obtiene o actualiza el cliente CDP nativo para la pestaña activa."""
        if not self.current_tab_id:
            return None

        port = self.detect_active_port()
        if not port:
            return None

        tabs = self.list_tabs()
        target = next((t for t in tabs if t.tab_id == self.current_tab_id), None)
        if target and target.ws_url:
            self.native_client = CDPNativeClient(target.ws_url)
            return self.native_client

        return self.native_client

    def select_tab_by_id(self, tab_id: str) -> bool:
        """Selecciona y enlaza una pestaña específica por su ID de forma permanente."""
        self.current_tab_id = tab_id
        port = self.detect_active_port()

        if port:
            try:
                requests.get(f"http://127.0.0.1:{port}/json/activate/{tab_id}", timeout=1.0)
            except Exception:
                pass

        self._get_active_native_client()
        self.take_screenshot()
        return True

    def scan_tickets_with_diagnostics(self) -> Dict[str, Any]:
        """
        Escanea la tabla de ServiceNow, genera logs detallados en la consola
        y retorna la lista de tickets junto con el texto de la cola (Queue).
        """
        print("\n" + "="*50)
        print("🔍 [INICIANDO ESCANEO DE TICKETS EN SERVICENOW]")
        print("="*50)

        client = self._get_active_native_client()
        if not client:
            print("[ERROR] No hay cliente CDP nativo conectado para la pestaña actual.")
            return {
                "tickets": [],
                "totalQueueText": "Error: Navegador desconectado",
                "logs": ["No hay conexión CDP activa."]
            }

        diag = client.detect_tickets_in_table()
        logs = diag.get("logs", [])
        tickets = diag.get("tickets", [])
        queue_text = diag.get("totalQueueText", "")

        for line in logs:
            print(f"  [DOM Log] {line}")

        print(f"\n📊 [RESULTADO] Tickets encontrados: {len(tickets)} | Estado de la cola: {queue_text}")
        for idx, t in enumerate(tickets, 1):
            print(f"   {idx}. {t.get('number')} -> {t.get('description', '')[:60]}")
        print("="*50 + "\n")

        return diag

    def open_ticket(self, ticket_number: str) -> bool:
        """Ubica el ticket en la columna Number y hace clic para abrirlo."""
        print(f"🎯 [ACCIÓN] Solicitando abrir ticket {ticket_number}...")
        client = self._get_active_native_client()
        if not client:
            print("[ERROR] Cliente no disponible.")
            return False

        success = client.open_ticket_by_number(ticket_number)
        print(f"  ✓ Resultado del clic: {'Éxito' if success else 'Falló'}")
        time.sleep(1.2)
        self.take_screenshot()
        return success

    def scroll(self, direction: str = "down", amount: int = 400) -> bool:
        """Realiza scroll hacia arriba o hacia abajo en la pestaña activa."""
        client = self._get_active_native_client()
        if not client:
            return False

        delta = amount if direction.lower() == "down" else -amount
        success = client.scroll(delta)
        time.sleep(0.1)
        self.take_screenshot()
        return success

    def click_element(self, selector: str) -> bool:
        """Hace clic en un elemento CSS / XPath o texto en la pestaña activa."""
        client = self._get_active_native_client()
        if not client:
            return False

        success = client.click_selector(selector)
        time.sleep(0.2)
        self.take_screenshot()
        return success

    def reload(self) -> bool:
        """Recarga la pestaña activa."""
        client = self._get_active_native_client()
        if not client:
            return False

        success = client.reload()
        time.sleep(0.8)
        self.take_screenshot()
        return success

    def take_screenshot(self) -> Optional[bytes]:
        """Obtiene una captura de pantalla en bytes usando el protocolo CDP directo."""
        client = self._get_active_native_client()
        if client:
            try:
                frame = client.capture_screenshot()
                if frame:
                    self.last_screenshot_bytes = frame
                    return frame
            except Exception:
                pass

        return self.last_screenshot_bytes
