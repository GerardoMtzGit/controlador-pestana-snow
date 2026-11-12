"""
similarity_engine.py
Motor de análisis de similitud histórica y recomendación de colas (Queues) mediante:
1. Comparación semántica y vectorial de 'Description' (Paso 3) vs CSV histórico.
2. Agrupación y estadísticas de colas donde se cerraron los tickets más similares.
3. Integración con LLM local Gemma (vía Ollama o inferencia local) para síntesis inteligente.
4. Fallback 100% determinista y offline con scikit-learn (TF-IDF + Coseno).
"""

import os
import re
import json
import requests
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


OLLAMA_API_URL = "http://localhost:11434/api/generate"


class LocalGemmaClient:
    """Cliente para comunicarse con el modelo local Gemma a través del runtime local Ollama."""

    @staticmethod
    def is_available() -> bool:
        """Verifica si el servicio local Ollama está activo y respondiendo."""
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=1.2)
            return r.status_code == 200
        except Exception:
            return False

    @staticmethod
    def get_available_models() -> List[str]:
        """Obtiene la lista de modelos locales descargados en Ollama."""
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=1.5)
            if r.status_code == 200:
                data = r.json()
                return [m.get("name") for m in data.get("models", [])]
        except Exception:
            pass
        return []

    @staticmethod
    def generate_synthesis(current_desc: str, top_matches_summary: str, model_name: str = "gemma:2b") -> Optional[str]:
        """Envía el contexto a Gemma local para generar una recomendación ejecutiva de enrutamiento."""
        prompt = f"""Eres un experto en enrutamiento y soporte técnico para ServiceNow mySchneider.
Analiza la siguiente descripción de un nuevo ticket y los tickets históricos más similares encontrados en la base de datos:

[DESCRIPCIÓN DEL TICKET ACTUAL]
{current_desc}

[TICKETS HISTÓRICOS SIMILARES Y COLAS DONDE SE CERRARON]
{top_matches_summary}

Instrucciones:
1. Explica en 2 o 3 líneas por qué este ticket debe enviarse a la cola predominante.
2. Da una posible solución o recomendación técnica basada en cómo se resolvieron los tickets parecidos.
Sé conciso, directo y profesional."""

        try:
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9
                }
            }
            r = requests.post(OLLAMA_API_URL, json=payload, timeout=25.0)
            if r.status_code == 200:
                res_data = r.json()
                return res_data.get("response", "").strip()
        except Exception as e:
            print(f"[Gemma Local] No se pudo conectar a Gemma: {e}")
        return None


class HistoricalCSVAnalyzer:
    """Analizador de similitud entre la descripción activa y un archivo CSV histórico de ServiceNow."""

    def __init__(self):
        self.df_historical: Optional[pd.DataFrame] = None
        self.desc_col: str = ""
        self.queue_col: str = ""
        self.num_col: str = ""
        self.state_col: str = ""

    def load_csv(self, file_or_buffer) -> Tuple[bool, str]:
        """Carga y valida el archivo CSV histórico, detectando automáticamente las columnas clave."""
        try:
            # Soportar codificaciones habituales de ServiceNow (UTF-8, Latin-1, cp1252)
            for enc in ["utf-8", "latin-1", "cp1252"]:
                try:
                    if hasattr(file_or_buffer, "seek"):
                        file_or_buffer.seek(0)
                    df = pd.read_csv(file_or_buffer, encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return False, "No se pudo leer el archivo con codificación UTF-8 ni Latin-1."

            if df.empty:
                return False, "El archivo CSV está vacío."

            self.df_historical = df
            self._detect_columns()

            if not self.desc_col:
                return False, "No se encontró una columna de descripción ('Description', 'Descripción', etc.) en el CSV."

            msg = f"CSV cargado exitosamente: {len(df)} registros. " \
                  f"Columnas detectadas -> Descripción: '{self.desc_col}', Cola: '{self.queue_col or 'N/A'}', Ticket: '{self.num_col or 'N/A'}'"
            return True, msg
        except Exception as e:
            return False, f"Error al procesar el archivo CSV: {e}"

    def _detect_columns(self):
        """Detecta las columnas más probables para descripción, cola (queue), número y estado."""
        if self.df_historical is None:
            return

        cols = list(self.df_historical.columns)

        # 1. Columna de Descripción (prioridad a Description sobre Short Description)
        desc_candidates = []
        for c in cols:
            cl = c.strip().lower()
            if cl == "description" or cl == "descripción" or cl == "issue_description":
                desc_candidates.insert(0, c)
            elif "description" in cl or "descripción" in cl:
                if "short" not in cl:
                    desc_candidates.append(c)
                else:
                    # Dejar Short description solo como último recurso
                    desc_candidates.append(c)

        self.desc_col = desc_candidates[0] if desc_candidates else cols[0]

        # 2. Columna de Queue / Cola / Assignment Group
        queue_candidates = []
        for c in cols:
            cl = c.strip().lower()
            if any(k in cl for k in ["assignment_group", "assignment group", "queue", "cola", "closed_by_group", "assigned_to_group", "group"]):
                queue_candidates.append(c)
        self.queue_col = queue_candidates[0] if queue_candidates else ""

        # 3. Columna de Número de Ticket
        num_candidates = []
        for c in cols:
            cl = c.strip().lower()
            if cl in ["number", "número", "numero", "ticket", "incident_number", "task_number", "id"]:
                num_candidates.append(c)
            elif "number" in cl or "ticket" in cl:
                num_candidates.append(c)
        self.num_col = num_candidates[0] if num_candidates else ""

        # 4. Columna de Estado / Cierre
        state_candidates = []
        for c in cols:
            cl = c.strip().lower()
            if any(k in cl for k in ["state", "estado", "close_code", "resolution", "closed_at"]):
                state_candidates.append(c)
        self.state_col = state_candidates[0] if state_candidates else ""

    def analyze_similarity(self, query_description: str, top_k: int = 15, threshold: float = 0.15) -> Dict[str, Any]:
        """
        Compara la descripción del ticket actual contra todas las descripciones del CSV histórico
        utilizando TF-IDF y similitud del coseno.
        """
        if self.df_historical is None or self.df_historical.empty or not self.desc_col:
            return {
                "success": False,
                "error": "No hay un archivo CSV histórico cargado.",
                "matches_count": 0,
                "queue_breakdown": {},
                "top_queue": "",
                "detailed_matches": []
            }

        query_clean = query_description.strip()
        if not query_clean:
            return {
                "success": False,
                "error": "La descripción del ticket en el Paso 3 está vacía.",
                "matches_count": 0,
                "queue_breakdown": {},
                "top_queue": "",
                "detailed_matches": []
            }

        # Preparar corpus
        corpus_series = self.df_historical[self.desc_col].fillna("").astype(str)
        corpus = corpus_series.tolist()

        # Vectorizar con TF-IDF (soporta n-gramas 1-2 para captar frases y términos técnicos de ServiceNow)
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words=None,
            max_features=25000,
            token_pattern=r"(?u)\b\w+\b"
        )

        all_texts = [query_clean] + corpus
        try:
            tfidf_matrix = vectorizer.fit_transform(all_texts)
        except Exception as e:
            return {
                "success": False,
                "error": f"Error al vectorizar descripciones: {e}",
                "matches_count": 0,
                "queue_breakdown": {},
                "top_queue": "",
                "detailed_matches": []
            }

        query_vec = tfidf_matrix[0:1]
        historical_vecs = tfidf_matrix[1:]

        similarities = cosine_similarity(query_vec, historical_vecs).flatten()

        # Obtener los índices más similares ordenados descendente
        sorted_indices = similarities.argsort()[::-1]

        matches = []
        for idx in sorted_indices:
            sim_score = float(similarities[idx])
            if sim_score < threshold and len(matches) >= 3:
                break
            if len(matches) >= top_k:
                break

            row = self.df_historical.iloc[idx]
            t_num = str(row[self.num_col]) if self.num_col and pd.notna(row[self.num_col]) else f"HIST-{idx+1}"
            raw_desc = str(row[self.desc_col]) if pd.notna(row[self.desc_col]) else ""
            queue_val = str(row[self.queue_col]) if self.queue_col and pd.notna(row[self.queue_col]) else "Sin Cola Especificada"
            state_val = str(row[self.state_col]) if self.state_col and pd.notna(row[self.state_col]) else "Cerrado / Resuelto"

            # Truncar descripción larga para vista
            shortened_desc = raw_desc if len(raw_desc) <= 150 else raw_desc[:147] + "..."

            matches.append({
                "Ticket Histórico": t_num,
                "Descripción Histórica": shortened_desc,
                "Queue de Cierre": queue_val,
                "Similitud (%)": round(sim_score * 100, 1),
                "Estado / Cierre": state_val,
                "_raw_desc": raw_desc,
                "_score": sim_score
            })

        # Si no hubo coincidencias con threshold alto, tomar al menos los top 3 relativos
        if not matches and len(sorted_indices) > 0:
            for idx in sorted_indices[:3]:
                sim_score = float(similarities[idx])
                row = self.df_historical.iloc[idx]
                t_num = str(row[self.num_col]) if self.num_col and pd.notna(row[self.num_col]) else f"HIST-{idx+1}"
                raw_desc = str(row[self.desc_col]) if pd.notna(row[self.desc_col]) else ""
                queue_val = str(row[self.queue_col]) if self.queue_col and pd.notna(row[self.queue_col]) else "Sin Cola Especificada"
                state_val = str(row[self.state_col]) if self.state_col and pd.notna(row[self.state_col]) else "Cerrado"
                matches.append({
                    "Ticket Histórico": t_num,
                    "Descripción Histórica": raw_desc[:147] + "..." if len(raw_desc) > 150 else raw_desc,
                    "Queue de Cierre": queue_val,
                    "Similitud (%)": round(sim_score * 100, 1),
                    "Estado / Cierre": state_val,
                    "_raw_desc": raw_desc,
                    "_score": sim_score
                })

        # Desglose estadístico por Queue
        queue_counts = {}
        for m in matches:
            q = m["Queue de Cierre"]
            queue_counts[q] = queue_counts.get(q, 0) + 1

        # Ordenar colas por mayor frecuencia de cierre
        sorted_queues = sorted(queue_counts.items(), key=lambda x: x[1], reverse=True)
        top_queue = sorted_queues[0][0] if sorted_queues else ""

        # Construir resumen textual de matches para Gemma
        summary_lines = []
        for idx, m in enumerate(matches[:5], 1):
            summary_lines.append(
                f"- Ticket: {m['Ticket Histórico']} | Queue: {m['Queue de Cierre']} | Similitud: {m['Similitud (%)']}% | Descripción: {m['Descripción Histórica'][:90]}"
            )
        matches_text_for_llm = "\n".join(summary_lines)

        # Consultar síntesis a Gemma Local si está disponible
        gemma_synthesis = None
        if LocalGemmaClient.is_available():
            available_models = LocalGemmaClient.get_available_models()
            model_to_use = "gemma:2b"
            for m in available_models:
                if "gemma" in m.lower():
                    model_to_use = m
                    break
            gemma_synthesis = LocalGemmaClient.generate_synthesis(query_clean, matches_text_for_llm, model_to_use)

        return {
            "success": True,
            "matches_count": len(matches),
            "queue_breakdown": dict(sorted_queues),
            "top_queue": top_queue,
            "detailed_matches": matches,
            "gemma_synthesis": gemma_synthesis,
            "gemma_available": LocalGemmaClient.is_available()
        }

