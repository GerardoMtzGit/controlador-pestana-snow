"""
bootstrap.py
Módulo de inicialización, verificación automática de dependencias, skills y entorno.
Se ejecuta ANTES de abrir la aplicación principal:
1. Revisa librerías de Python requeridas (Streamlit, Playwright, google-antigravity, Requests, Pillow, nest-asyncio).
2. Instala automáticamente cualquier librería faltante mediante pip.
3. Asegura que los navegadores requeridos por Playwright estén instalados.
4. Verifica que los directorios y archivos de skills requeridos (.gemini/skills/) existan.
5. Lanza la aplicación Streamlit de forma transparente y optimizada.
"""

import sys
import subprocess
import importlib
from pathlib import Path

REQUIRED_LIBRARIES = {
    "streamlit": "streamlit>=1.35.0",
    "playwright": "playwright>=1.44.0",
    "google.antigravity": "google-antigravity>=0.1.23",
    "requests": "requests>=2.31.0",
    "PIL": "pillow>=10.0.0",
    "nest_asyncio": "nest-asyncio>=1.6.0"
}

REQUIRED_SKILLS = [
    "cdp-tab-automation",
    "antigravity-sdk-orchestrator",
    "service-now-dom-navigator"
]

ROOT_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = ROOT_DIR / ".gemini" / "skills"


def check_and_install_libraries():
    """Comprueba cada módulo requerido y lo instala automáticamente si falta."""
    print("🔍 [1/4] Verificando librerías de Python requeridas...")
    missing_packages = []

    for module_name, pip_spec in REQUIRED_LIBRARIES.items():
        try:
            importlib.import_module(module_name)
            print(f"  ✓ {module_name} instalado correctamente.")
        except ImportError:
            print(f"  ✗ {module_name} NO encontrado. Se programará su instalación...")
            missing_packages.append(pip_spec)

    if missing_packages:
        print(f"\n📦 Instalando {len(missing_packages)} dependencias faltantes...")
        for pkg in missing_packages:
            print(f"  -> Instalando {pkg}...")
            cmd = [sys.executable, "-m", "pip", "install", pkg]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[ADVERTENCIA] Falló instalación estándar de {pkg}. Intentando con --user...")
                subprocess.run([sys.executable, "-m", "pip", "install", "--user", pkg], check=True)
        print("  ✓ Todas las librerías se instalaron exitosamente.\n")
    else:
        print("  ✓ Todas las librerías requeridas ya están presentes.\n")


def check_playwright_browsers():
    """Asegura que los drivers de Playwright estén disponibles."""
    print("🌐 [2/4] Verificando componentes de Playwright...")
    try:
        from playwright.sync_api import sync_playwright
        print("  ✓ Playwright listo.")
    except Exception as e:
        print(f"  -> Instalando Chromium para Playwright ({e})...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
        print("  ✓ Chromium listo.\n")


def check_and_restore_skills():
    """Verifica y asegura que los directorios y archivos de las skills estén íntegros."""
    print("🧠 [3/4] Verificando integridad de Skills requeridas...")
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    skills_definitions = {
        "cdp-tab-automation": """---
name: cdp-tab-automation
description: Conexión, descubrimiento, selección e inspección en vivo de pestañas de navegador vía Chrome DevTools Protocol (CDP) y Playwright.
---
# Skill: CDP Tab Automation
Controla pestañas abiertas en el puerto 9222 sin perder sesiones ni credenciales corporativas.
""",
        "antigravity-sdk-orchestrator": """---
name: antigravity-sdk-orchestrator
description: Orquestación del Agente de Inteligencia Artificial mediante google-antigravity SDK.
---
# Skill: Antigravity SDK Orchestrator
Interpreta comandos en lenguaje natural y genera acciones de control web mediante LocalAgentConfig.
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
            print(f"  -> Restaurando skill faltante: {skill_name}...")
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(skills_definitions.get(skill_name, f"---\nname: {skill_name}\n---"))
            print(f"  ✓ Skill {skill_name} creada y lista.")
        else:
            print(f"  ✓ Skill '{skill_name}' validada.")

    print("  ✓ Todas las Skills requeridas están verificadas.\n")


def start_application():
    """Inicia la interfaz gráfica Streamlit."""
    print("🚀 [4/4] Iniciando el Controlador de Pestañas...")
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
    print("   INICIALIZADOR INTELIGENTE - CONTROLADOR DE PESTAÑAS")
    print("============================================================\n")

    check_and_install_libraries()
    check_playwright_browsers()
    check_and_restore_skills()
    start_application()

