# ============================================================
# Jarvis - Módulo de Ações
# ============================================================

import subprocess
import os
import time

from config import PROGRAMS


def execute_action(action_name: str):
    """Abre os programas associados a uma ação."""
    programs = PROGRAMS.get(action_name)
    if not programs:
        print(f"[AÇÃO] Ação desconhecida: {action_name}")
        return

    print(f"\n{'=' * 50}")
    print(f"  JARVIS - Executando: {action_name}")
    print(f"{'=' * 50}")

    for prog in programs:
        name = prog["name"]
        path = prog["path"]
        args = prog.get("args", [])

        try:
            if path.startswith("shell:"):
                # Para apps da Windows Store
                os.startfile(path)
            elif os.path.exists(path):
                cmd = [path] + args
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.DETACHED_PROCESS,
                )
            else:
                # Tenta como comando do sistema
                subprocess.Popen(
                    f'start "" "{path}"',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            print(f"  [OK] {name}")
            time.sleep(0.5)  # pequeno delay entre aberturas

        except Exception as e:
            print(f"  [ERRO] {name}: {e}")

    print()
