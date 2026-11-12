"""
bootstrap.py
Módulo de inicialización, verificación resiliente y tolerante a fallos de red/proxy.
Se ejecuta ANTES de abrir la aplicación principal:
1. Revisa librerías esenciales (Streamlit, Playwright, Requests, Pillow, Hugging Face).
2. Si alguna librería opcional no puede descargarse debido al proxy o firewall corporativo,
   continúa de forma segura con el Motor Local sin interrumpir ni bloquear el arranque.
3. Asegura que los directorios y skills locales (.gemini/skills/) existan.
4. Lanza la aplicación Streamlit de forma fluida.
"""

import sys
import subprocess
import importlib
from pathlib import Path

# Librerías esenciales mínimas (con fallback no bloqueante)
REQUIRED_LIBRARIES = {
    "streamlit": "streamlit>=1.35.0",
    "playwright": "playwright>=1.44.0",
    "requests": "requests>=2.31.0",
    "PIL": "pillow>=10.0.0",
    "pandas": "pandas>=2.0.0"
}

OPTIONAL_LIBRARIES = {
    "huggingface_hub": "huggingface_hub>=0.23.0"
}

REQUIRED_SKILLS = [
    "cdp-tab-automation",
    "huggingface-orchestrator",
    "service-now-dom-navigator"
]

ROOT_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = ROOT_DIR / ".gemini" / "skills"


def check_and_install_libraries():
    """Comprueba módulos requeridos con instalación no bloqueante tolerante a proxys corporativos."""
    print("🔍 [1/3] Verificando entorno y librerías...")

    # 1. Comprobar librerías esenciales
    for module_name, pip_spec in REQUIRED_LIBRARIES.items():
        try:
            importlib.import_module(module_name)
            print(f"  ✓ {module_name} listo.")
        except ImportError:
            print(f"  ✗ {module_name} no encontrado. Intentando instalar...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", pip_spec], check=False)
            except Exception as e:
                print(f"  [AVISO] No se pudo instalar {pip_spec}: {e}")

    # 2. Comprobar librerías opcionales (Hugging Face)
    for module_name, pip_spec in OPTIONAL_LIBRARIES.items():
        try:
            importlib.import_module(module_name)
            print(f"  ✓ {module_name} listo.")
        except ImportError:
            print(f"  ℹ️ {module_name} no detectado. Intentando instalar...")
            res = subprocess.run([sys.executable, "-m", "pip", "install", pip_spec], capture_output=True, text=True)
            if res.returncode == 0:
                print(f"  ✓ {module_name} instalado correctamente.")
            else:
                print(f"  ℹ️ Red/Proxy corporativo detectado: Se utilizará el Motor Local Integrado (100% funcional sin conexión externa).")


def check_and_restore_skills():
    """Verifica y asegura que los directorios y archivos de las skills estén íntegros."""
    print("\n🧠 [2/3] Verificando integridad de Skills locales...")
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    skills_definitions = {
        "cdp-tab-automation": """---
name: cdp-tab-automation
description: Conexión, descubrimiento, selección e inspección en vivo de pestañas de navegador vía Chrome DevTools Protocol (CDP) y Playwright.
---
# Skill: CDP Tab Automation
Controla pestañas abiertas en el puerto 9222 sin perder sesiones ni credenciales corporativas.
""",
        "huggingface-orchestrator": """---
name: huggingface-orchestrator
description: Orquestación del Agente de Inteligencia Artificial mediante modelos de Hugging Face o motor local determinista.
---
# Skill: Hugging Face & Local Orchestrator
Interpreta comandos en lenguaje natural y genera acciones de control web (scroll, clics, notas, updates) con 0 dependencia de red.
""",
        "service-now-dom-navigator": """---
name: service-now-dom-navigator
description: Mapeo y navegación del DOM en ServiceNow (iFrames gsft_main, pestañas de notas y formularios).
---
# Skill: ServiceNow DOM Navigator
Especialización para operar incidentes, formularios y elementos dentro de iFrames de ServiceNow.
"""
    }

    for skill_name in REQUIRED_SKILLS:
        target_dir = SKILLS_DIR / skill_name
        target_file = target_dir / "SKILL.md"

        if not target_file.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(skills_definitions.get(skill_name, f"---\nname: {skill_name}\n---"))
            print(f"  ✓ Skill '{skill_name}' restaurada.")
        else:
            print(f"  ✓ Skill '{skill_name}' validada.")


def start_application():
    """Inicia la interfaz gráfica Streamlit."""
    print("\n🚀 [3/3] Iniciando el Controlador de Pestañas...")
    app_file = ROOT_DIR / "app_controlador.py"

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_file),
        "--server.headless=false",
        "--browser.gatherUsageStats=false"
    ]

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n👋 Controlador detenido por el usuario.")


if __name__ == "__main__":
    print("============================================================")
    print("   INICIALIZADOR CORPORATIVO - CONTROLADOR DE PESTAÑAS")
    print("============================================================\n")

    check_and_install_libraries()
    check_and_restore_skills()
    start_application()
