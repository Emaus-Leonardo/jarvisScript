#!/usr/bin/env python3
# ============================================================
# Jarvis - Calibração de Palma
# ============================================================
# Executa sessão interativa para gravar palmas e criar fingerprint.

import numpy as np
import sounddevice as sd
import time

from config import SAMPLE_RATE, DETECTION_WINDOW, ENERGY_THRESHOLD
from core.fingerprint import (
    extract_spectral_features,
    build_fingerprint_from_samples,
    save_fingerprint,
    compute_similarity,
)

NUM_SAMPLES = 5
RECORD_DURATION = 3.0  # segundos de gravação por tentativa


def detect_impacts(audio: np.ndarray, fs: int, threshold: float) -> list[np.ndarray]:
    """Detecta picos de energia (impactos) num trecho de áudio."""
    window_samples = int(fs * DETECTION_WINDOW)
    impacts = []
    i = 0
    while i < len(audio) - window_samples:
        chunk = audio[i:i + window_samples]
        rms = np.sqrt(np.mean(chunk ** 2))
        if rms > threshold:
            impacts.append(chunk)
            i += window_samples * 2  # pula para evitar capturar o mesmo impacto
        else:
            i += window_samples // 4
    return impacts


def calibrate():
    print("=" * 60)
    print("  JARVIS - Calibração de Fingerprint de Palma")
    print("=" * 60)
    print()
    print(f"Vou pedir para você bater {NUM_SAMPLES} palmas, uma de cada vez.")
    print("Cada gravação dura 3 segundos. Bata UMA palma durante a gravação.")
    print()

    input("Pressione ENTER quando estiver pronto...")
    print()

    clap_samples = []

    for i in range(NUM_SAMPLES):
        print(f"--- Palma {i + 1}/{NUM_SAMPLES} ---")
        print("Gravando em 2 segundos... prepare-se!")
        time.sleep(2)
        print(">>> BATA UMA PALMA AGORA! <<<")

        audio = sd.rec(
            int(SAMPLE_RATE * RECORD_DURATION),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        audio = audio.flatten()

        impacts = detect_impacts(audio, SAMPLE_RATE, ENERGY_THRESHOLD)

        if not impacts:
            print("[!] Nenhum impacto detectado. Tente bater mais forte.")
            print("    Vamos tentar novamente...")
            i -= 1
            continue

        # Pega o impacto mais forte
        loudest = max(impacts, key=lambda x: np.sqrt(np.mean(x ** 2)))
        clap_samples.append(loudest)
        print(f"[OK] Palma {i + 1} capturada! (RMS: {np.sqrt(np.mean(loudest ** 2)):.4f})")
        print()

    if len(clap_samples) < 3:
        print("[ERRO] Poucas amostras capturadas. Execute novamente.")
        return

    # Construir fingerprint
    fingerprint, samples_info = build_fingerprint_from_samples(clap_samples)
    save_fingerprint(fingerprint, samples_info=samples_info)

    # Teste de consistência
    print()
    print("--- Teste de consistência ---")
    sims = []
    for j, sample in enumerate(clap_samples):
        feat = extract_spectral_features(sample)
        sim = compute_similarity(feat, fingerprint)
        sims.append(sim)
        print(f"  Palma {j + 1}: similaridade = {sim:.3f}")

    avg_sim = np.mean(sims)
    print(f"\n  Similaridade média: {avg_sim:.3f}")

    if avg_sim > 0.7:
        print("  [EXCELENTE] Fingerprint de alta qualidade!")
    elif avg_sim > 0.5:
        print("  [BOM] Fingerprint aceitável.")
    else:
        print("  [ATENÇÃO] Consistência baixa. Considere recalibrar em ambiente silencioso.")

    print()
    print("--- Teste ao vivo (opcional) ---")
    resp = input("Quer testar com sons ao vivo? (s/n): ").strip().lower()
    if resp == "s":
        live_test(fingerprint)

    print()
    print("Calibração concluída! Execute jarvis.py para iniciar.")


def live_test(fingerprint: np.ndarray):
    """Teste interativo para verificar o fingerprint."""
    print()
    print("Vou gravar 5 segundos. Bata palmas, estale dedos, bata na mesa...")
    print("Gravando em 2 segundos...")
    time.sleep(2)
    print(">>> GRAVANDO <<<")

    audio = sd.rec(
        int(SAMPLE_RATE * 5),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    audio = audio.flatten()

    impacts = detect_impacts(audio, SAMPLE_RATE, ENERGY_THRESHOLD)
    print(f"\nDetectados {len(impacts)} impactos:")
    for k, imp in enumerate(impacts):
        feat = extract_spectral_features(imp)
        sim = compute_similarity(feat, fingerprint)
        rms = np.sqrt(np.mean(imp ** 2))
        label = "PALMA ✓" if sim >= 0.6 else "OUTRO ✗"
        print(f"  Impacto {k + 1}: sim={sim:.3f} rms={rms:.4f} → {label}")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    calibrate()
