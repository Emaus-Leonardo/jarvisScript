#!/usr/bin/env python3
# ============================================================
# JARVIS - Entry Point (GUI)
# ============================================================
# Executa a interface gráfica do Jarvis.
# Uso: python main.py

import os
import sys

# Garante que o diretório do projeto é o working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from gui.app import JarvisGUI


if __name__ == "__main__":
    app = JarvisGUI()
    app.run()
