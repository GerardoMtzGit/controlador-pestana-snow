"""
classifier_engine.py
Motor de clasificación y enrutamiento jerárquico estricto de tickets para mySchneider Web.
Evalúa en orden secuencial del Paso 1 al Paso 12 conforme a la directriz oficial:
1. Equipo Destino
2. Cola Asignada (Queue)
3. Justificación / Posible Solución
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd


USER_ROUTING_MARKDOWN = """# Rol y Objetivo
Eres un asistente experto en soporte técnico y ruteo de tickets para la plataforma mySchneider Web. Tu tarea es analizar la "Descripción del Ticket" proporcionada por el usuario y determinar el equipo y la cola (Queue) exacta a la que debe ser enviado, siguiendo estrictamente el flujo de jerarquía y decisión detallado a continuación.

---

## Flujo de Evaluación Jerárquica (Evalúa en orden del Paso 1 al 12)

### PASO 1: Identidad y Accesos (Identity & Access)
* **¿De qué trata?** Login, MFA, OTP, Okta/IAM, IDMSUserAIL, o acceso a P360.
* **Sub-decisión:**
  * **1.1.** Si es una corrección de plataforma IAM/Okta, corrección de datos de usuario/cuenta en Okta, problema de MFA relacionado con identidad, IDMSUserAIL o problemas de OTP:
    * **Equipo:** Okta / CIAM Team
    * **Cola:** `Secure Identity Run Global L2`
  * **1.2.** Si es un problema de perfil de cliente y login, o un problema relacionado con el acceso a P360:
    * **Equipo:** Transversal Team
    * **Cola:** `My Schneider Web Transversal Global L2`
  * *Si no coincide con ninguno de estos, pasa al Paso 2.*

### PASO 2: Equipo Transversal (Transversal Team)
* **¿De qué trata?** Actualizaciones BT/AOF en P360, contactos primarios/secundarios en P360, accesos de "Manage Member" en P360, estado de registro de contactos en P360, otros temas de P360, registro en mySchneider, reasignación de cuentas (Account re-assignment), o problemas de calidad de datos en AWS DB.
* **Cola asignada:** `My Schneider Web Transversal Global L2`

### PASO 3: Órdenes y Cotizaciones (Orders Team)
* **¿De qué trata?** Registro, gestión, entrada, historial o acceso de órdenes, precio y disponibilidad, funcionalidad del carrito (cart), cotizaciones, CPQ, facturas (invoices), o notas de entrega (delivery notes).
* **Cola asignada:** `My Schneider Web OX L2`

### PASO 4: Capacidades de Canal (Partners Team)
* **¿De qué trata?** Oportunidades, recompensas, programas, PDT / Documentos de cuenta, BOPP, entrenamiento/training, funcionalidad relacionada con Zinfi, o "Topics for you".
* **Cola asignada:** `BFO mySchneider Global L2`

### PASO 5: Cuentas y Contactos Físicos (Accounts & Contacts Team)
* **¿De qué trata?** Análisis de problemas y modificaciones en registros físicos de Cuentas o Contactos en BFO.
* **Cola asignada:** `BFO Accounts and Contacts L3`

### PASO 6: OCM o Chat (OCM / Chat Team)
* **¿De qué trata?** Todos los temas relacionados con OCM o Chat.
* **Cola asignada:** `BFO Customer Support L3`

### PASO 7: Servicios de Campo e Interfaz de Usuario (BFS / Field Services)
* **¿De qué trata?** Parte de UI de mySchneider, contratos, IB (Installed Base), derechos digitales (digital entitlements), visitas de servicio, problemas de registro en la UI, visibilidad, Service Board, ServiceMax Go, Mobile, u órdenes de trabajo/hojas de tiempo.
* **Cola asignada:** `BFS My Schneider L3` (o `BFS Global L3` para temas puramente de Field Services operativos).

### PASO 8: Cadena de Suministro Digital (Digital Supply Chain - DSC)
* **¿De qué trata?** Aplicaciones de Digital Supply Chain, Zuora, GSE, DPB, o licencias de software.
* **Cola asignada:** `Digital Supply Chain Global L2 General`

### PASO 9: Ecosistema de Productos (Product Ecosystem Team)
* **¿De qué trata?** Aplicación PES de se.com (Product Selector, HMC, etc.).
* **Cola asignada:** `Secom PES Global L2`

### PASO 10: Experiencia de Portal y Configuración (Core Team)
* **¿De qué trata?** Experiencia del portal mySchneider o temas de configuración: traducciones, enlaces rápidos, configuración de mapas de servicio, notificaciones y alertas (Notification Engine), problemas de rendimiento, problemas de cierre de sesión automático (auto logout), campañas Glaze, Partner Locator, Explore Communities, solicitud de configuración de canales, acceso al portal de transparencia de rebotes, reportes de rendimiento, o protección de cuenta (MFA configuraciones de portal).
* **Cola asignada:** `My Schneider Web Global L2`

### PASO 11: Colas de Soporte Secundarias (Other Support Queues)
Si no encaja en los pasos 1–10, evalúa las siguientes categorías especializadas:
* **Orders & Quotes Avanzadas:** 
  * `MYSE EDFX Global L2` (Problemas compartidos por mySW OX / base de datos SAP).
  * `Bridge MYSE(CR) Global L2` / `Bridge SAX(CR) Global L2` (Órdenes y precio/disponibilidad APAC/EMEA).
  * `Quotation CPQ Global L2` (Creación, vista, conversión de cotizaciones).
  * `Quotation CPQ Admin Global L2` (Onboarding de usuarios a la plataforma CPQ).
* **Integración y Plataforma:**
  * `SAPDTC DCX MYSE WW L2` (Sync e integración mySW–mySE–SAP).
  * `Titan Sales Marketing Global L2` (Sync e integración ERP S4/HANA).
  * `APIM Global L2` (APIs en plataforma SEAPIM).
  * `Reverse Proxy Global L2` (Problemas de reverse proxy).
* **Entrenamiento y Configuración:**
  * `mySchneider Configuration Global L2` (Contenido editorial o programas).
  * `mySchneider LMS Global L2` (Datos de capacitación, CSOD, Cornerstones).
  * `Selection & Configuration Global L3` (Configurador y Harmony Selector).
* **Accesos y Cuentas Secundarias:**
  * `bFO Global Delivery L3` (Accesos bFO, enlace ICR, contactos/cuentas, API updates).
  * `Partner Locator Global L2` (Acceso a cuentas de Partner Locator).
* **Apps y Web:**
  * `My Schneider App Global L2` (Problemas en la app MySE).
  * `Secom PS Global L2` (Product Selector).
  * `Customer Datalink Globaldelivery Global L3` (Soportes de nuevas aplicaciones).
* **Analítica y Voz del Cliente:**
  * `Web Statistics Global L2` (GA, Google Analytics, Content Square, GA4 data).
  * `Customer Voice Global L2` (Alertas Medallia, CSLD, Experiencia Digital).
* **Devoluciones e Instalaciones (Returns & IB):**
  * `Reverselogix Global L2` / `My Schneider Web Returns Global L2` (Plataforma de devoluciones).
  * `IBP Global L2` (Problemas de Installed Base).
* **MarTech y EEM:**
  * `SMA BMA Global L2` (MarTech SFMC) / `SMA User Global L2` (Marketo / Acceso).
  * `EEM Global L2` (CVent / Nexus Hub Management).

### PASO 12: Cascada Final (Fallback / Service Desk)
* Si la descripción **no** coincide con ninguna regla anterior de los Pasos 1 al 11:
  * **Equipo:** Service Desk
  * **Cola:** `Service Desk APAC L1` o `FJTU Service Desk L1`
"""


class HierarchicalStepRule:
    """Regla correspondiente a un paso de la jerarquía de evaluación."""
    def __init__(self, step_num: str, team: str, queue: str, keywords: List[str], justification_template: str):
        self.step_num = step_num
        self.team = team
        self.queue = queue
        self.keywords = [k.strip().lower() for k in keywords if k.strip()]
        self.justification_template = justification_template

    def matches(self, text: str) -> Optional[str]:
        """Comprueba si el texto contiene alguna de las condiciones/palabras clave y retorna la coincidencia."""
        if not text:
            return None
        text_lower = text.lower()
        for kw in self.keywords:
            # Coincidencia de palabra completa o frase
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower) or kw in text_lower:
                return kw
        return None


class TicketClassifierEngine:
    """Motor de evaluación jerárquica estricta (Paso 1 -> Paso 12)."""

    def __init__(self, markdown_content: Optional[str] = None):
        self.markdown_content = markdown_content or USER_ROUTING_MARKDOWN
        self.hierarchical_rules: List[HierarchicalStepRule] = []
        self._init_rules()

    def update_rules_from_markdown(self, markdown_text: str):
        """Actualiza el Markdown activo."""
        self.markdown_content = markdown_text
        self._init_rules()

    def _init_rules(self):
        """Define en estricto orden secuencial (Paso 1 a Paso 12) la jerarquía de enrutamiento."""
        self.hierarchical_rules = [
            # PASO 1.1: Okta / CIAM Team
            HierarchicalStepRule(
                step_num="Paso 1.1",
                team="Okta / CIAM Team",
                queue="Secure Identity Run Global L2",
                keywords=[
                    "okta", "ciam", "iam", "idmsuserail", "userail", "otp",
                    "mfa identity", "corrección okta", "corrección de plataforma iam",
                    "corrección datos usuario okta", "token okta", "mfa okta"
                ],
                justification_template="Coincidencia con incidencia de plataforma Okta/CIAM, MFA de identidad o UserAIL ({matched_kw})."
            ),
            # PASO 1.2: Transversal Team (Login y P360)
            HierarchicalStepRule(
                step_num="Paso 1.2",
                team="Transversal Team",
                queue="My Schneider Web Transversal Global L2",
                keywords=[
                    "perfil de cliente y login", "problema de login", "acceso a p360",
                    "login p360", "perfil cliente portal", "login portal", "login myschneider",
                    "login issue", "cannot login", "no puede iniciar sesion", "error login"
                ],
                justification_template="Problema relacionado con perfil de cliente, login en portal o acceso a P360 ({matched_kw})."
            ),
            # PASO 2: Equipo Transversal (P360, Registros, AWS DB)
            HierarchicalStepRule(
                step_num="Paso 2",
                team="Transversal Team",
                queue="My Schneider Web Transversal Global L2",
                keywords=[
                    "p360", "bt/aof", "bt aof", "manage member", "contacto primario", "contacto secundario",
                    "estado de registro de contactos", "registro en myschneider", "reasignación de cuentas",
                    "account re-assignment", "account reassignment", "aws db", "calidad de datos",
                    "primary contact", "secondary contact", "p360 member"
                ],
                justification_template="Gestión de contactos/BT/AOF en P360, registro de cuenta o calidad de datos AWS DB ({matched_kw})."
            ),
            # PASO 3: Órdenes y Cotizaciones (Orders Team)
            HierarchicalStepRule(
                step_num="Paso 3",
                team="Orders Team",
                queue="My Schneider Web OX L2",
                keywords=[
                    "orden", "ordenes", "órdenes", "order", "orders", "precio y disponibilidad",
                    "p&a", "price and availability", "carrito", "cart", "cotización", "cotizaciones",
                    "quote", "quotes", "quotation", "cpq", "factura", "facturas", "invoice", "invoices",
                    "albarán", "albaran", "delivery note", "delivery notes", "nota de entrega", "notas de entrega"
                ],
                justification_template="Consulta, registro o gestión de órdenes, precio y disponibilidad, carrito o cotizaciones ({matched_kw})."
            ),
            # PASO 4: Capacidades de Canal (Partners Team)
            HierarchicalStepRule(
                step_num="Paso 4",
                team="Partners Team",
                queue="BFO mySchneider Global L2",
                keywords=[
                    "zinfi", "oportunidades", "oportunidad", "opportunity", "opportunities",
                    "recompensas", "rewards", "reward", "programa de canales", "programas",
                    "pdt", "documentos de cuenta", "account documents", "bopp", "topics for you",
                    "training partner", "capacitación partner", "canal partner", "entrenamiento partner"
                ],
                justification_template="Capacidades de canal, programa de Rewards, Zinfi o gestión de oportunidades ({matched_kw})."
            ),
            # PASO 5: Cuentas y Contactos Físicos (Accounts & Contacts Team)
            HierarchicalStepRule(
                step_num="Paso 5",
                team="Accounts & Contacts Team",
                queue="BFO Accounts and Contacts L3",
                keywords=[
                    "registros físicos", "registro físico", "physical record", "cuentas bfo",
                    "contactos en bfo", "modificaciones en bfo", "bfo contact", "bfo account",
                    "modificar registro bfo"
                ],
                justification_template="Modificación y análisis de registros físicos de cuentas o contactos en BFO ({matched_kw})."
            ),
            # PASO 6: OCM o Chat (OCM / Chat Team)
            HierarchicalStepRule(
                step_num="Paso 6",
                team="OCM / Chat Team",
                queue="BFO Customer Support L3",
                keywords=["ocm", "chat", "agente en vivo", "live chat", "chat widget", "ccc support", "soporte ccc"],
                justification_template="Incidencia relacionada con plataforma OCM o funcionalidad de Chat ({matched_kw})."
            ),
            # PASO 7: Servicios de Campo e Interfaz (BFS / Field Services)
            HierarchicalStepRule(
                step_num="Paso 7",
                team="BFS / Field Services",
                queue="BFS My Schneider L3",
                keywords=[
                    "installed base", "ib", "contratos", "derechos digitales", "digital entitlements",
                    "visitas de servicio", "service board", "servicemax", "servicemax go", "mobile",
                    "hojas de tiempo", "órdenes de trabajo", "work orders", "time sheets", "ter"
                ],
                justification_template="Servicios de campo, base instalada (IB), contratos o ServiceMax ({matched_kw})."
            ),
            # PASO 8: Cadena de Suministro Digital (DSC Team)
            HierarchicalStepRule(
                step_num="Paso 8",
                team="Digital Supply Chain - DSC",
                queue="Digital Supply Chain Global L2 General",
                keywords=[
                    "digital supply chain", "dsc", "zuora", "gse", "dpb",
                    "licencias de software", "software license", "licencia software"
                ],
                justification_template="Aplicación de Digital Supply Chain, Zuora, GSE, DPB o licenciamiento ({matched_kw})."
            ),
            # PASO 9: Ecosistema de Productos (Product Ecosystem Team)
            HierarchicalStepRule(
                step_num="Paso 9",
                team="Product Ecosystem Team",
                queue="Secom PES Global L2",
                keywords=[
                    "pes", "product selector", "selector de productos", "hmc", "se.com pes", "página de producto", "pdp"
                ],
                justification_template="Ecosistema de productos, aplicación PES de se.com o catálogo HMC ({matched_kw})."
            ),
            # PASO 10: Experiencia de Portal y Configuración (Core Team)
            HierarchicalStepRule(
                step_num="Paso 10",
                team="Core Team",
                queue="My Schneider Web Global L2",
                keywords=[
                    "traducciones", "traducción", "translation", "enlaces rápidos", "quick links",
                    "mapas de servicio", "service map", "notificaciones", "alertas", "notification engine",
                    "cierre de sesión automático", "auto logout", "auto-logout", "campañas glaze", "glaze",
                    "partner locator", "explore communities", "portal de transparencia", "rendimiento portal"
                ],
                justification_template="Configuración de portal core, traducciones, mapas de servicio o Notification Engine ({matched_kw})."
            ),
            # PASO 11: Colas Secundarias Especializadas
            HierarchicalStepRule(
                step_num="Paso 11.1 (EDFX)",
                team="Orders & Quotes Avanzadas",
                queue="MYSE EDFX Global L2",
                keywords=["edfx", "myse edfx", "base de datos sap ox"],
                justification_template="Problema avanzado compartido por mySW OX y base de datos SAP (EDFX)."
            ),
            HierarchicalStepRule(
                step_num="Paso 11.2 (SAPDTC)",
                team="Integración y Plataforma",
                queue="SAPDTC DCX MYSE WW L2",
                keywords=["sapdtc", "integracion sap", "integración sap", "mysw-myse-sap"],
                justification_template="Sincronización e integración de plataforma mySW–mySE–SAP."
            ),
            HierarchicalStepRule(
                step_num="Paso 11.3 (Titan)",
                team="Integración y Plataforma",
                queue="Titan Sales Marketing Global L2",
                keywords=["titan", "s4/hana", "s4hana", "erp s4"],
                justification_template="Sincronización con ERP S/4HANA (Titan)."
            ),
            HierarchicalStepRule(
                step_num="Paso 11.4 (APIM)",
                team="Integración y Plataforma",
                queue="APIM Global L2",
                keywords=["apim", "seapim", "api gateway"],
                justification_template="APIs y servicios en gateway SEAPIM."
            ),
            HierarchicalStepRule(
                step_num="Paso 11.5 (LMS)",
                team="Entrenamiento y Configuración",
                queue="mySchneider LMS Global L2",
                keywords=["lms", "csod", "cornerstone", "cornerstones", "capacitación lms"],
                justification_template="Plataforma de capacitación LMS / CSOD / Cornerstones."
            ),
            HierarchicalStepRule(
                step_num="Paso 11.6 (App Móvil)",
                team="Apps y Web",
                queue="My Schneider App Global L2",
                keywords=["app móvil", "app movil", "myse app", "aplicación móvil"],
                justification_template="Incidencia en la app móvil mySchneider."
            ),
            HierarchicalStepRule(
                step_num="Paso 11.7 (Analítica)",
                team="Analítica y Voz del Cliente",
                queue="Web Statistics Global L2",
                keywords=["google analytics", "ga4", "content square", "estadísticas web"],
                justification_template="Analítica web, GA4 o Content Square."
            ),
            HierarchicalStepRule(
                step_num="Paso 11.8 (Customer Voice)",
                team="Analítica y Voz del Cliente",
                queue="Customer Voice Global L2",
                keywords=["medallia", "customer voice", "csld", "voz del cliente"],
                justification_template="Alertas Medallia o métricas de experiencia digital Customer Voice."
            ),
            HierarchicalStepRule(
                step_num="Paso 11.9 (Devoluciones)",
                team="Returns & IB",
                queue="Reverselogix Global L2",
                keywords=["reverselogix", "devoluciones", "returns platform", "web returns"],
                justification_template="Plataforma de devoluciones Reverselogix / Returns."
            )
        ]

    def classify_ticket(self, ticket_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Evalúa un ticket individual de forma estrictamente jerárquica del Paso 1 al Paso 12.
        Retorna:
        - Número de Ticket
        - Descripción
        - Equipo Destino
        - Posible Queue
        - Justificación
        - Paso Evaluado
        """
        t_num = ticket_data.get("Number", "TICKET").strip()

        # Recopilar todos los campos descriptivos disponibles
        short_desc = ticket_data.get("Short description", "").strip()
        full_desc = ticket_data.get("Description", "").strip()
        more_info = ticket_data.get("More Information (Issue Description)", "").strip()

        combined_text = f"{short_desc} {full_desc} {more_info}".strip()
        if not combined_text:
            combined_text = ticket_data.get("description", "Sin descripción registrada").strip()

        # Evaluación jerárquica secuencial estricta (Paso 1 al 11)
        for rule in self.hierarchical_rules:
            matched_kw = rule.matches(combined_text)
            if matched_kw:
                justification = rule.justification_template.format(matched_kw=matched_kw)
                display_desc = short_desc or more_info or full_desc or combined_text
                if len(display_desc) > 130:
                    display_desc = display_desc[:127] + "..."

                return {
                    "Número de Ticket": t_num,
                    "Descripción": display_desc,
                    "Equipo Destino": rule.team,
                    "Posible Queue": rule.queue,
                    "Justificación": justification,
                    "Paso Evaluado": rule.step_num
                }

        # PASO 12: Cascada Final (Fallback / Service Desk)
        display_desc = short_desc or more_info or full_desc or combined_text
        if len(display_desc) > 130:
            display_desc = display_desc[:127] + "..."

        return {
            "Número de Ticket": t_num,
            "Descripción": display_desc,
            "Equipo Destino": "Service Desk",
            "Posible Queue": "Service Desk APAC L1",
            "Justificación": "No coincide con ninguna regla específica de los Pasos 1 al 11. Derivado a Service Desk para triage inicial.",
            "Paso Evaluado": "Paso 12 (Fallback)"
        }

    def classify_all_tickets(self, tickets_list: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Aplica la jerarquía del Paso 1 al Paso 12 sobre la lista de tickets."""
        results = []
        for t in tickets_list:
            results.append(self.classify_ticket(t))
        return results
