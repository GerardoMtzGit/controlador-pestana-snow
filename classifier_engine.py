"""
classifier_engine.py
Motor de clasificación y enrutamiento inteligente de tickets de ServiceNow.
Compara la descripción del ticket (Description, Short Description, More Information)
contra las directrices y reglas provistas en formato Markdown para:
1. Determinar el Queue (Assignment Group) de destino.
2. Proveer una posible solución o recomendación de acción.
3. Mostrar los resultados en una tabla estructurada y clara.
"""

import os
import re
from typing import Dict, Any, List, Optional
import pandas as pd


# Reglas por defecto basadas en el árbol oficial de decisión de mySchneider Web (Q1-Q11)
DEFAULT_ROUTING_MARKDOWN = """# Árbol de Decisión de Enrutamiento de Tickets mySchneider Web

## Q1: Identidad o Acceso
### Q1a: Okta / CIAM Team
- **Condiciones / Palabras clave:** okta, ciam, iam, corrección cuenta, mfa, idmsuserail, otp, login fallido okta, token expirado
- **Queue / Cola Sugerida:** Secure Identity Run Global L2
- **Posible Solución:** Escalar al equipo de Okta/CIAM para revisión de permisos en Azure AD / Okta, reseteo de MFA o verificación de UserAIL. Contacto: Secure_Identity-L2@schneider-electric.com.

### Q1b: Transversal Team (Identidad/Perfil)
- **Condiciones / Palabras clave:** login portal, perfil cliente, acceso p360, mySchneider login, registro perfil, cuenta bloqueada portal
- **Queue / Cola Sugerida:** My Schneider Web Transversal Global L2
- **Posible Solución:** Verificar estado de activación del perfil en mySchneider Web, sincronización de cuenta en P360 y desbloqueo de acceso. Contacto: MySchneider-WebTransversalSupport@se.com.

## Q2: P360, Registro y Datos (Transversal Team)
- **Condiciones / Palabras clave:** bt, aof, manage member, registro contactos, registro guiado, reasignación cuentas, calidad datos, aws db, reportes myschneider
- **Queue / Cola Sugerida:** My Schneider Web Transversal Global L2
- **Posible Solución:** Revisar registro de miembro en P360, reasignar cuenta de cliente o validar consistencia de datos en AWS DB. Contacto: MySchneider-WebTransversalSupport@se.com.

## Q3: Órdenes y Cotizaciones (Orders Team)
- **Condiciones / Palabras clave:** orden, ordenes, pedido, pedidos, cotización, cotizaciones, quote, quotes, carrito, cart, cpq, factura, invoices, delivery notes, albarán, precio y disponibilidad, p&a
- **Queue / Cola Sugerida:** My Schneider Web OX L2
- **Posible Solución:** Analizar flujo de orden en middleware OX, validar integración con SAP y verificar estatus de cotización o carrito de compras. Contacto: MySchneider-WebOxSupport@se.com.

## Q4: Capacidades de Canal / DCM (Partners Team)
- **Condiciones / Palabras clave:** zinfi, partner, partners, canal, oportunidades, rewards, programa recompensas, bopp, pdt, account documents, topics for you, training partner, capacitacion canal
- **Queue / Cola Sugerida:** BFO mySchneider Global L2
- **Posible Solución:** Verificar enrolamiento del partner en ZINFI o portal de canales, sincronización de recompensas (Rewards) y asignación de permisos de socio. Contacto: WebPartner-Support@se.com.

## Q5: Registros Físicos BFO (Accounts & Contacts Team)
- **Condiciones / Palabras clave:** bfo cuenta, bfo contacto, registro fisico bfo, fusion cuentas salesforce, modificar cuenta bfo
- **Queue / Cola Sugerida:** BFO Accounts and Contacts L3
- **Posible Solución:** Realizar modificación o fusión directa de registros físicos de Account/Contact en la base backend de Salesforce bFO. Contacto: dl.in.bfo.platform.team@se.com.

## Q6: OCM / Chat (Customer Support Team)
- **Condiciones / Palabras clave:** ocm, chat, soporte ccc, agente en vivo, widget chat
- **Queue / Cola Sugerida:** BFO Customer Support L3
- **Posible Solución:** Revisar disponibilidad de cola de chat OCM y configuración de enrutamiento de agentes CCC. Contacto: bfo.ccc@se.com.

## Q7: Field Services & UI mySchneider
- **Condiciones / Palabras clave:** contratos, installed base, ib, visitas servicio, derechos digitales, entitlements, servicemax, service board, work orders, ordenes trabajo
- **Queue / Cola Sugerida:** BFS My Schneider L3
- **Posible Solución:** Validar contrato de servicio, visibilidad de base instalada (IB) en el portal o sincronización con ServiceMax. Contacto: pranay.gupta@se.com.

## Q8: Digital Supply Chain (DSC Team)
- **Condiciones / Palabras clave:** digital supply chain, dsc, zuora, gse, dpb, activacion licencias, software license
- **Queue / Cola Sugerida:** Digital Supply Chain Global L2 General
- **Posible Solución:** Gestionar activación o reasignación de licencias de software en plataforma Zuora / DPB. Contacto: DSC_Support_L2@se.com.

## Q9: Ecosistema de Productos (Product Ecosystem Team)
- **Condiciones / Palabras clave:** pes, pdp, página producto, catálogo, catalogo, selector productos, hmc, ficha técnica, rango producto
- **Queue / Cola Sugerida:** Secom PES Global L2
- **Posible Solución:** Corregir datos de catálogo de producto en HMC/PES y verificar publicación en páginas PDP de se.com. Contacto: Antonius.hery@se.com.

## Q10: Configuración y Portal Core (Core Team)
- **Condiciones / Palabras clave:** traducción, traduccion, enlaces rapidos, quick links, service map, notificaciones, notification engine, auto-logout, cierre sesion, lentitud portal, glaze
- **Queue / Cola Sugerida:** My Schneider Web Global L2
- **Posible Solución:** Ajustar configuración de portal core, revisar motor de notificaciones o desplegar fix de etiquetas de idioma. Contacto: dl.global.myschneider-web.core.support@se.com.

## Fallback General (Sin coincidencia específica)
- **Condiciones / Palabras clave:** consulta general, sin categoria, helpdesk
- **Queue / Cola Sugerida:** Service Desk APAC L1
- **Posible Solución:** Realizar triage inicial y recopilar información adicional del usuario antes de reasignar.
"""


class MarkdownRule:
    def __init__(self, title: str, keywords: List[str], queue: str, solution: str):
        self.title = title
        self.keywords = [k.strip().lower() for k in keywords if k.strip()]
        self.queue = queue.strip()
        self.solution = solution.strip()

    def score_text(self, text: str) -> int:
        if not text:
            return 0
        text_lower = text.lower()
        score = 0
        for kw in self.keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                score += 3
            elif kw in text_lower:
                score += 1
        return score


class TicketClassifierEngine:
    def __init__(self, markdown_content: Optional[str] = None):
        self.markdown_content = markdown_content or DEFAULT_ROUTING_MARKDOWN
        self.rules: List[MarkdownRule] = []
        self._parse_markdown_rules()

    def update_rules_from_markdown(self, markdown_text: str):
        """Actualiza las reglas a partir de un nuevo texto Markdown."""
        self.markdown_content = markdown_text
        self.rules = []
        self._parse_markdown_rules()

    def _parse_markdown_rules(self):
        """Parsea el texto Markdown extrayendo bloques de reglas, colas y soluciones."""
        normalized_md = self.markdown_content.replace("\r\n", "\n").replace("\r", "\n")
        sections = re.split(r"\n(?=#{1,3}\s+)", normalized_md)

        for sec in sections:
            lines = [l.strip() for l in sec.strip().split("\n") if l.strip()]
            if not lines:
                continue

            title = lines[0].replace("#", "").strip()
            queue = ""
            keywords: List[str] = []
            solution = ""

            for line in lines[1:]:
                clean_line = line.replace("**", "").replace("`", "").strip().lstrip("-* ").strip()

                # Buscar Cola / Queue
                q_match = re.search(r"^(?:Queue|Cola|Posible\s*Queue|Assignment\s*Group)[\s/A-Za-z]*[:=]\s*(.+)", clean_line, re.IGNORECASE)
                if q_match:
                    queue = q_match.group(1).strip()
                    continue

                # Buscar Condiciones / Palabras clave
                kw_match = re.search(r"^(?:Condiciones|Palabras\s*clave|Keywords|Match)[\s/A-Za-z]*[:=]\s*(.+)", clean_line, re.IGNORECASE)
                if kw_match:
                    raw_kws = kw_match.group(1).strip()
                    keywords = [k.strip() for k in re.split(r"[,;|/]", raw_kws) if k.strip()]
                    continue

                # Buscar Posible Solución / Recomendación
                sol_match = re.search(r"^(?:Posible\s*Solución|Solución|Acción|Recomendación|Contacto)[\s/A-Za-z]*[:=]\s*(.+)", clean_line, re.IGNORECASE)
                if sol_match:
                    solution = sol_match.group(1).strip()
                    continue

            if queue:
                if not keywords:
                    keywords = [w.lower() for w in re.findall(r"\b[A-Za-z]{3,}\b", title) if w.lower() not in ["team", "the", "que", "para", "con"]]
                if not solution:
                    solution = f"Enrutar a {queue} para atención técnica según directrices de {title}."

                self.rules.append(MarkdownRule(title=title, keywords=keywords, queue=queue, solution=solution))

    def classify_ticket(self, ticket_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Clasifica un ticket individual comparando su contenido con las reglas Markdown.
        Devuelve el número de ticket, descripción representativa, Queue sugerido y Posible Solución.
        """
        t_num = ticket_data.get("Number", "TICKET-SIN-NUMERO")

        # Texto conjunto a analizar
        short_desc = ticket_data.get("Short description", "")
        full_desc = ticket_data.get("Description", "")
        more_info = ticket_data.get("More Information (Issue Description)", "")

        combined_text = f"{short_desc} {full_desc} {more_info}".strip()
        if not combined_text:
            combined_text = ticket_data.get("description", "Sin descripción registrada")

        best_rule: Optional[MarkdownRule] = None
        max_score = 0

        for r in self.rules:
            s = r.score_text(combined_text)
            if s > max_score:
                max_score = s
                best_rule = r

        if best_rule and max_score > 0:
            suggested_queue = best_rule.queue
            suggested_solution = best_rule.solution
            confidence = "Alta" if max_score >= 3 else "Media"
        else:
            suggested_queue = "BFO mySchneider Global L2" if "zinfi" in combined_text.lower() else "Service Desk APAC L1"
            suggested_solution = "Revisar descripción detallada con el usuario y escalar al equipo correspondiente."
            confidence = "Revisión Manual"

        # Descripción breve para tabla
        display_desc = short_desc or more_info or full_desc or combined_text
        if len(display_desc) > 130:
            display_desc = display_desc[:127] + "..."

        return {
            "Número de Ticket": t_num,
            "Descripción": display_desc,
            "Posible Queue": suggested_queue,
            "Posible Solución": suggested_solution,
            "Confianza": confidence
        }

    def classify_all_tickets(self, tickets_list: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Clasifica una lista completa de tickets y retorna la tabla de decisiones."""
        results = []
        for t in tickets_list:
            results.append(self.classify_ticket(t))
        return results
