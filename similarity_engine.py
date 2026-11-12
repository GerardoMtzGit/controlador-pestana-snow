"""
similarity_engine.py
Motor de análisis de similitud histórica y recomendación de colas (Queues).
Diseñado para entornos corporativos con proxy estricto:
1. 0 dependencias obligatorias (incluye motor TF-IDF nativo en Python puro de 0 ms).
2. Si scikit-learn está disponible lo usa; si no, usa el motor nativo sin interrumpir.
3. Conexión automática con LLM local Gemma (vía Ollama localhost:11434).
4. Agrupación estadística y detección automática de columnas de ServiceNow.
"""

import os
import re
import json
import math
from collections import Counter
import requests
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

# Detección opcional de scikit-learn (tolerante a fallos de instalación)
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


OLLAMA_API_URL = "http://localhost:11434/api/generate"


class PurePythonTfidfVectorizer:
    """Vectorizador TF-IDF nativo en Python estándar sin dependencias externas (0 pip, 0 proxy blocks)."""

    def __init__(self, ngram_range=(1, 2)):
        self.ngram_range = ngram_range
        self.stop_words = {
            "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by",
            "is", "are", "was", "were", "it", "this", "that", "these", "those", "de", "la", "el",
            "en", "y", "o", "un", "una", "los", "las", "por", "para", "con", "es", "son", "su"
        }
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_count: int = 0

    def _tokenize(self, text: str) -> List[str]:
        words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", text.lower()) if w not in self.stop_words]
        tokens = list(words)
        if self.ngram_range[1] >= 2 and len(words) > 1:
            for i in range(len(words) - 1):
                tokens.append(f"{words[i]}_{words[i+1]}")
        return tokens

    def fit_transform(self, docs: List[str]) -> List[Dict[int, float]]:
        self.doc_count = len(docs)
        doc_tokens = [self._tokenize(d) for d in docs]

        df_counts = Counter()
        for dt in doc_tokens:
            for term in set(dt):
                df_counts[term] += 1

        self.vocab = {term: idx for idx, term in enumerate(df_counts.keys())}
        self.idf = {
            term: math.log((1.0 + self.doc_count) / (1.0 + count)) + 1.0
            for term, count in df_counts.items()
        }

        vectors = []
        for dt in doc_tokens:
            vec = {}
            term_counts = Counter(dt)
            total = len(dt) or 1
            for term, count in term_counts.items():
                if term in self.idf:
                    tf = count / total
                    vec[self.vocab[term]] = tf * self.idf[term]

            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            norm_vec = {k: v / norm for k, v in vec.items()}
            vectors.append(norm_vec)

        return vectors

    @staticmethod
    def cosine_similarity(vec_a: Dict[int, float], vec_b: Dict[int, float]) -> float:
        if not vec_a or not vec_b:
            return 0.0
        if len(vec_a) > len(vec_b):
            vec_a, vec_b = vec_b, vec_a
        return sum(val * vec_b.get(idx, 0.0) for idx, val in vec_a.items())


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

    def analyze_similarity(self, query_description: str, top_k: int = 15, threshold: float = 0.10) -> Dict[str, Any]:
        """
        Compara la descripción del ticket actual contra todas las descripciones del CSV histórico.
        Utiliza scikit-learn si está disponible; de lo contrario utiliza PurePythonTfidfVectorizer.
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

        corpus_series = self.df_historical[self.desc_col].fillna("").astype(str)
        corpus = corpus_series.tolist()

        try:
            if SKLEARN_AVAILABLE:
                vectorizer = TfidfVectorizer(
                    ngram_range=(1, 2),
                    stop_words=None,
                    max_features=25000,
                    token_pattern=r"(?u)\b\w+\b"
                )
                all_texts = [query_clean] + corpus
                tfidf_matrix = vectorizer.fit_transform(all_texts)
                query_vec = tfidf_matrix[0:1]
                historical_vecs = tfidf_matrix[1:]
                similarities = list(cosine_similarity(query_vec, historical_vecs).flatten())
            else:
                pure_vectorizer = PurePythonTfidfVectorizer(ngram_range=(1, 2))
                all_texts = [query_clean] + corpus
                vectors = pure_vectorizer.fit_transform(all_texts)
                query_vec = vectors[0]
                similarities = [pure_vectorizer.cosine_similarity(query_vec, v) for v in vectors[1:]]
        except Exception as e:
            return {
                "success": False,
                "error": f"Error al vectorizar descripciones: {e}",
                "matches_count": 0,
                "queue_breakdown": {},
                "top_queue": "",
                "detailed_matches": []
            }

        # Ordenar índices por mayor similitud
        indexed_scores = list(enumerate(similarities))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        matches = []
        for idx, sim_score in indexed_scores:
            if sim_score < threshold and len(matches) >= 3:
                break
            if len(matches) >= top_k:
                break

            row = self.df_historical.iloc[idx]
            t_num = str(row[self.num_col]) if self.num_col and pd.notna(row[self.num_col]) else f"HIST-{idx+1}"
            raw_desc = str(row[self.desc_col]).strip() if pd.notna(row[self.desc_col]) else ""
            queue_val = str(row[self.queue_col]).strip() if self.queue_col and pd.notna(row[self.queue_col]) else "Sin Cola Especificada"
            state_val = str(row[self.state_col]).strip() if self.state_col and pd.notna(row[self.state_col]) else "Cerrado / Resuelto"

            matches.append({
                "Ticket Histórico": t_num,
                "Descripción Histórica": raw_desc,
                "Queue de Cierre": queue_val,
                "Similitud (%)": round(float(sim_score) * 100, 1),
                "Estado / Cierre": state_val,
                "_raw_desc": raw_desc,
                "_score": float(sim_score)
            })

        # Si el umbral fue muy alto pero hay registros, tomar los 3 más parecidos
        if not matches and len(indexed_scores) > 0:
            for idx, sim_score in indexed_scores[:3]:
                row = self.df_historical.iloc[idx]
                t_num = str(row[self.num_col]) if self.num_col and pd.notna(row[self.num_col]) else f"HIST-{idx+1}"
                raw_desc = str(row[self.desc_col]).strip() if pd.notna(row[self.desc_col]) else ""
                queue_val = str(row[self.queue_col]).strip() if self.queue_col and pd.notna(row[self.queue_col]) else "Sin Cola Especificada"
                state_val = str(row[self.state_col]).strip() if self.state_col and pd.notna(row[self.state_col]) else "Cerrado"
                matches.append({
                    "Ticket Histórico": t_num,
                    "Descripción Histórica": raw_desc,
                    "Queue de Cierre": queue_val,
                    "Similitud (%)": round(float(sim_score) * 100, 1),
                    "Estado / Cierre": state_val,
                    "_raw_desc": raw_desc,
                    "_score": float(sim_score)
                })

        queue_counts = {}
        for m in matches:
            q = m["Queue de Cierre"]
            queue_counts[q] = queue_counts.get(q, 0) + 1

        sorted_queues = sorted(queue_counts.items(), key=lambda x: x[1], reverse=True)
        top_queue = sorted_queues[0][0] if sorted_queues else ""

        # Resumen para Gemma
        summary_lines = []
        for m in matches[:5]:
            summary_lines.append(
                f"- Ticket: {m['Ticket Histórico']} | Queue: {m['Queue de Cierre']} | Similitud: {m['Similitud (%)']}% | Descripción: {m['Descripción Histórica'][:90]}"
            )
        matches_text_for_llm = "\n".join(summary_lines)

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
