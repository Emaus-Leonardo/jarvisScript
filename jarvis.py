#!/usr/bin/env python3
# ============================================================
# JARVIS - Assistente de Ativação por Som e Voz
# ============================================================
# Escuta o microfone em tempo real.
# Detecta palmas via fingerprint espectral + comandos de voz.

import numpy as np
import sounddevice as sd
import queue
import time
import sys
import os

from config import (
    SAMPLE_RATE, BLOCK_SIZE, DETECTION_WINDOW, COOLDOWN,
    ENERGY_THRESHOLD, CLAPS_REQUIRED, CLAP_WINDOW,
    FINGERPRINT_FILE,
)
from fingerprint import (
    load_fingerprint,
    extract_spectral_features,
    compute_similarity,
    is_clap,
)
from actions import execute_action
from voice import VoiceListener


class JarvisDetector:
    """Detector principal — palmas + voz."""

    def __init__(self):
        self.fingerprint = load_fingerprint(FINGERPRINT_FILE)
        if self.fingerprint is None:
            print("[ERRO] Fingerprint não encontrado!")
            print("       Execute primeiro: python calibrate.py")
            sys.exit(1)

        self.command_queue = queue.Queue()
        self.audio_buffer = np.zeros(0, dtype=np.float32)
        self.clap_times: list[float] = []
        self.last_trigger_time = 0.0
        self.window_samples = int(SAMPLE_RATE * DETECTION_WINDOW)

        # Estado do detector de impacto
        self._in_impact = False
        self._impact_start = 0
        self._impact_cooldown = 0.0  # timestamp do fim do último impacto
        self._prev_block = np.zeros(BLOCK_SIZE, dtype=np.float32)  # pre-buffer

    def start(self):
        print()
        print("=" * 60)
        print("     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗")
        print("     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝")
        print("     ██║███████║██████╔╝██║   ██║██║███████╗")
        print("██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║")
        print("╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║")
        print(" ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝")
        print("=" * 60)
        print()
        print(f"  Palmas necessárias: {CLAPS_REQUIRED}")
        print(f"  Janela de detecção: {CLAP_WINDOW}s")
        print(f"  Fingerprint carregado: {FINGERPRINT_FILE}")
        print(f"  Comando de voz: \"Jarvis, bora trabalhar\"")
        print()
        print("  Escutando... (Ctrl+C para sair)")
        print("-" * 60)

        # Iniciar reconhecimento de voz em thread separada
        try:
            self.voice = VoiceListener(self.command_queue)
            self.voice.start()
        except Exception as e:
            print(f"[AVISO] Voz desabilitada: {e}")
            print("        Detecção de palmas continua ativa.")

        # Iniciar stream de áudio para detecção de palmas
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
            ):
                self._main_loop()
        except KeyboardInterrupt:
            print("\n[JARVIS] Encerrando...")
        except Exception as e:
            print(f"[ERRO] {e}")
            sys.exit(1)

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback do stream de áudio — processa blocos em tempo real."""
        if status:
            pass  # overflow/underflow — ignora silenciosamente

        audio = indata[:, 0]  # mono
        rms = np.sqrt(np.mean(audio ** 2))
        now = time.time()

        # Cooldown entre impactos — ignora energia residual/eco da palma anterior
        if not self._in_impact and rms > ENERGY_THRESHOLD:
            if now - self._impact_cooldown < 0.08:
                self._prev_block = audio.copy()
                return
            # Início de um impacto — prepend bloco anterior como lead-in
            self._in_impact = True
            self._impact_start = now
            self.audio_buffer = np.concatenate([self._prev_block, audio])

        elif self._in_impact:
            self.audio_buffer = np.concatenate([self.audio_buffer, audio])

            # Coletou amostras suficientes para a janela de detecção
            if len(self.audio_buffer) >= self.window_samples:
                self._in_impact = False
                self._impact_cooldown = now
                chunk = self.audio_buffer[:self.window_samples].copy()
                self.command_queue.put(("audio", chunk))
                self.audio_buffer = np.zeros(0, dtype=np.float32)

            # Timeout — impacto muito longo, provavelmente não é palma
            elif now - self._impact_start > 0.5:
                self._in_impact = False
                self._impact_cooldown = now
                self.audio_buffer = np.zeros(0, dtype=np.float32)

        else:
            # Atualiza pre-buffer quando idle (para lead-in do próximo impacto)
            self._prev_block = audio.copy()

    def _main_loop(self):
        """Loop principal — processa eventos da fila."""
        while True:
            try:
                event = self.command_queue.get(timeout=0.1)
            except queue.Empty:
                self._check_clap_timeout()
                continue

            event_type, data = event

            if event_type == "audio":
                self._process_audio_event(data)
            elif event_type == "voice":
                self._handle_action(data, source="VOZ")

    def _process_audio_event(self, audio: np.ndarray):
        """Analisa um trecho de áudio para ver se é palma."""
        now = time.time()

        # Cooldown após trigger
        if now - self.last_trigger_time < COOLDOWN:
            return

        clap_detected, similarity = is_clap(audio, self.fingerprint)

        if clap_detected:
            self.clap_times.append(now)
            rms = np.sqrt(np.mean(audio ** 2))
            count = len(self.clap_times)
            print(f"  [PALMA {count}/{CLAPS_REQUIRED}] sim={similarity:.3f} rms={rms:.4f}")

            if count >= CLAPS_REQUIRED:
                self._handle_action("work", source="PALMA")
                self.clap_times.clear()
        else:
            rms = np.sqrt(np.mean(audio ** 2))
            if similarity > 0.3:  # perto mas não suficiente
                print(f"  [---] som descartado: sim={similarity:.3f} rms={rms:.4f}")

    def _check_clap_timeout(self):
        """Remove palmas antigas se a janela expirou."""
        if not self.clap_times:
            return
        now = time.time()
        if now - self.clap_times[0] > CLAP_WINDOW:
            if self.clap_times:
                print(f"  [TIMEOUT] {len(self.clap_times)} palma(s) — janela expirou, resetando.")
            self.clap_times.clear()

    def _handle_action(self, action: str, source: str):
        """Executa uma ação."""
        self.last_trigger_time = time.time()
        print(f"\n>>> ATIVADO via {source}! <<<")
        execute_action(action)


def main():
    # Muda para o diretório do script para encontrar o fingerprint
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    detector = JarvisDetector()
    detector.start()


if __name__ == "__main__":
    main()
