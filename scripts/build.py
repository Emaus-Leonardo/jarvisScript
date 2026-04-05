#!/usr/bin/env python3
# ============================================================
# JARVIS - Build Script (.exe)
# ============================================================
# Gera o executável usando PyInstaller.
# Uso: python scripts/build.py (a partir da raiz do projeto)

import subprocess
import sys
import os

def main():
    # Garante que estamos na raiz do projeto
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    # Verifica se PyInstaller está instalado
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("[*] Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    print("[*] Gerando executável...")
    print()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "Jarvis",
        "--add-data", "config.py;.",
        "--add-data", "core;core",
        "--add-data", "gui;gui",
        "--add-data", "data;data",
        # Hidden imports que PyInstaller pode não detectar
        "--hidden-import", "sounddevice",
        "--hidden-import", "speech_recognition",
        "--hidden-import", "numpy",
        "--hidden-import", "scipy",
        "--hidden-import", "scipy.signal",
        "--hidden-import", "scipy.fft",
        # Entry point
        "main.py",
    ]

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print()
        print("=" * 50)
        print("  BUILD CONCLUIDO!")
        print("  Executavel: dist/Jarvis.exe")
        print("=" * 50)
        print()
        print("  IMPORTANTE: Copie a pasta data/ (com clap_fingerprint.json)")
        print("  para a mesma pasta do Jarvis.exe")
        print("  (ou calibre novamente pela interface)")
    else:
        print()
        print("[ERRO] Build falhou. Verifique os erros acima.")
        sys.exit(1)


if __name__ == "__main__":
    main()
