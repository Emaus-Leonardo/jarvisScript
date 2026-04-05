#!/usr/bin/env python3
# ============================================================
# JARVIS - Interface Gráfica
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import time
import os
import numpy as np
import sounddevice as sd

from config import (
    SAMPLE_RATE, BLOCK_SIZE, DETECTION_WINDOW, COOLDOWN,
    ENERGY_THRESHOLD, CLAPS_REQUIRED, CLAP_WINDOW,
    FINGERPRINT_FILE, CLAP_SIMILARITY_THRESHOLD,
)
from core.fingerprint import (
    load_fingerprint, extract_spectral_features, compute_similarity,
    is_clap, save_fingerprint, build_fingerprint_from_samples,
)
from core.actions import execute_action
from core.voice import VoiceListener
from core.calibrate import detect_impacts


# --- Cores do tema ---
BG_DARK = "#0a0a0f"
BG_PANEL = "#12121a"
BG_CARD = "#1a1a2e"
FG_TEXT = "#e0e0e0"
FG_DIM = "#666680"
FG_ACCENT = "#00d4ff"
FG_GREEN = "#00ff88"
FG_RED = "#ff4466"
FG_YELLOW = "#ffaa00"
FG_PURPLE = "#aa66ff"
BTN_BG = "#1e1e3a"
BTN_HOVER = "#2a2a4a"


class JarvisGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JARVIS")
        self.root.geometry("720x620")
        self.root.minsize(600, 500)
        self.root.configure(bg=BG_DARK)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Estado
        self.listening = False
        self.fingerprint = None
        self.command_queue = queue.Queue()
        self.gui_queue = queue.Queue()
        self.stream = None
        self.voice_listener = None
        self.audio_buffer = np.zeros(0, dtype=np.float32)
        self.clap_times: list[float] = []
        self.last_trigger_time = 0.0
        self.window_samples = int(SAMPLE_RATE * DETECTION_WINDOW)
        self._in_impact = False
        self._impact_start = 0.0
        self.clap_count_display = 0

        # Calibração
        self._calibrating = False
        self._calib_step = 0
        self._calib_samples: list[np.ndarray] = []
        self._calib_total = 5

        self._build_ui()
        self._load_fingerprint()
        self._poll_gui_queue()

    # ===========================================================
    # UI
    # ===========================================================
    def _build_ui(self):
        # --- Header ---
        header = tk.Frame(self.root, bg=BG_DARK)
        header.pack(fill=tk.X, padx=20, pady=(15, 5))

        tk.Label(
            header, text="J.A.R.V.I.S", font=("Consolas", 28, "bold"),
            fg=FG_ACCENT, bg=BG_DARK,
        ).pack(side=tk.LEFT)

        self.status_label = tk.Label(
            header, text="  OFFLINE", font=("Consolas", 12),
            fg=FG_DIM, bg=BG_DARK,
        )
        self.status_label.pack(side=tk.LEFT, padx=(15, 0))

        # --- Info cards ---
        cards = tk.Frame(self.root, bg=BG_DARK)
        cards.pack(fill=tk.X, padx=20, pady=10)
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)
        cards.columnconfigure(2, weight=1)

        self.fp_card = self._make_card(cards, "FINGERPRINT", "--", 0)
        self.clap_card = self._make_card(cards, "PALMAS", f"0 / {CLAPS_REQUIRED}", 1)
        self.voice_card = self._make_card(cards, "VOZ", "OFF", 2)

        # --- Barra de nível de áudio ---
        meter_frame = tk.Frame(self.root, bg=BG_DARK)
        meter_frame.pack(fill=tk.X, padx=20, pady=(0, 5))
        tk.Label(meter_frame, text="MIC", font=("Consolas", 9), fg=FG_DIM, bg=BG_DARK).pack(side=tk.LEFT)
        self.level_canvas = tk.Canvas(meter_frame, height=12, bg=BG_CARD, highlightthickness=0)
        self.level_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.level_bar = self.level_canvas.create_rectangle(0, 0, 0, 12, fill=FG_GREEN, outline="")

        # --- Log ---
        log_frame = tk.Frame(self.root, bg=BG_PANEL, bd=0)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        self.log_text = tk.Text(
            log_frame, bg=BG_PANEL, fg=FG_TEXT, font=("Consolas", 10),
            insertbackground=FG_ACCENT, selectbackground="#2a2a4a",
            relief=tk.FLAT, padx=10, pady=10, wrap=tk.WORD,
            state=tk.DISABLED, cursor="arrow",
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Tags de cor
        self.log_text.tag_configure("info", foreground=FG_ACCENT)
        self.log_text.tag_configure("success", foreground=FG_GREEN)
        self.log_text.tag_configure("warning", foreground=FG_YELLOW)
        self.log_text.tag_configure("error", foreground=FG_RED)
        self.log_text.tag_configure("dim", foreground=FG_DIM)
        self.log_text.tag_configure("purple", foreground=FG_PURPLE)

        # --- Botões ---
        btn_frame = tk.Frame(self.root, bg=BG_DARK)
        btn_frame.pack(fill=tk.X, padx=20, pady=(5, 15))

        self.btn_calibrate = self._make_button(btn_frame, "CALIBRAR", self._start_calibration)
        self.btn_calibrate.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_toggle = self._make_button(btn_frame, "INICIAR", self._toggle_listening)
        self.btn_toggle.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_clear = self._make_button(btn_frame, "LIMPAR LOG", self._clear_log)
        self.btn_clear.pack(side=tk.RIGHT)

    def _make_card(self, parent, title, value, col):
        frame = tk.Frame(parent, bg=BG_CARD, padx=12, pady=8)
        frame.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0))
        tk.Label(frame, text=title, font=("Consolas", 9), fg=FG_DIM, bg=BG_CARD).pack(anchor=tk.W)
        val_label = tk.Label(frame, text=value, font=("Consolas", 14, "bold"), fg=FG_TEXT, bg=BG_CARD)
        val_label.pack(anchor=tk.W)
        return val_label

    def _make_button(self, parent, text, command):
        btn = tk.Button(
            parent, text=text, command=command,
            font=("Consolas", 10, "bold"), fg=FG_ACCENT, bg=BTN_BG,
            activeforeground=FG_TEXT, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=16, pady=6, cursor="hand2",
        )
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=BTN_HOVER))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=BTN_BG))
        return btn

    # ===========================================================
    # Log
    # ===========================================================
    def _log(self, text, tag="info"):
        self.gui_queue.put(("log", text, tag))

    def _do_log(self, text, tag):
        self.log_text.configure(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] ", "dim")
        self.log_text.insert(tk.END, text + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ===========================================================
    # GUI queue polling
    # ===========================================================
    def _poll_gui_queue(self):
        try:
            while True:
                msg = self.gui_queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._do_log(msg[1], msg[2])
                elif kind == "status":
                    self.status_label.configure(text=msg[1], fg=msg[2])
                elif kind == "fp_card":
                    self.fp_card.configure(text=msg[1], fg=msg[2])
                elif kind == "clap_card":
                    self.clap_card.configure(text=msg[1])
                elif kind == "voice_card":
                    self.voice_card.configure(text=msg[1], fg=msg[2])
                elif kind == "btn_toggle":
                    self.btn_toggle.configure(text=msg[1])
                elif kind == "btn_calibrate_state":
                    self.btn_calibrate.configure(state=msg[1])
                elif kind == "level":
                    self._update_level_bar(msg[1])
        except queue.Empty:
            pass
        self.root.after(50, self._poll_gui_queue)

    def _update_level_bar(self, rms):
        w = self.level_canvas.winfo_width()
        # Escala logarítmica, clamp 0-1
        db = max(0, min(1, (rms * 30)))
        bar_w = int(w * db)
        color = FG_GREEN if db < 0.6 else (FG_YELLOW if db < 0.85 else FG_RED)
        self.level_canvas.coords(self.level_bar, 0, 0, bar_w, 12)
        self.level_canvas.itemconfig(self.level_bar, fill=color)

    # ===========================================================
    # Fingerprint
    # ===========================================================
    def _load_fingerprint(self):
        fp = load_fingerprint(FINGERPRINT_FILE)
        if fp is not None:
            self.fingerprint = fp
            self.gui_queue.put(("fp_card", "OK", FG_GREEN))
            self._log("Fingerprint carregado com sucesso.", "success")
        else:
            self.gui_queue.put(("fp_card", "NAO ENCONTRADO", FG_RED))
            self._log("Nenhum fingerprint encontrado. Calibre primeiro.", "warning")

    # ===========================================================
    # Calibração
    # ===========================================================
    def _start_calibration(self):
        if self.listening:
            self._stop_listening()

        self._calibrating = True
        self._calib_step = 0
        self._calib_samples = []
        self.gui_queue.put(("btn_calibrate_state", tk.DISABLED))
        self.gui_queue.put(("btn_toggle", "INICIAR"))
        self._log("=" * 45, "purple")
        self._log("CALIBRACAO INICIADA", "purple")
        self._log(f"Bata {self._calib_total} palmas, uma por vez.", "info")
        self._log("Preparando... bata a primeira palma em 2s.", "info")
        self.root.after(2000, self._calib_record_step)

    def _calib_record_step(self):
        if not self._calibrating:
            return

        step = self._calib_step + 1
        self._log(f"--- Palma {step}/{self._calib_total} - GRAVANDO ---", "warning")
        self.gui_queue.put(("clap_card", f"CAL {step}/{self._calib_total}"))

        threading.Thread(target=self._calib_record_audio, daemon=True).start()

    def _calib_record_audio(self):
        try:
            audio = sd.rec(
                int(SAMPLE_RATE * 3.0),
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            )
            sd.wait()
            audio = audio.flatten()

            impacts = detect_impacts(audio, SAMPLE_RATE, ENERGY_THRESHOLD)

            if not impacts:
                self._log("Nenhum impacto detectado. Tente mais forte!", "error")
                self.root.after(1500, self._calib_record_step)
                return

            loudest = max(impacts, key=lambda x: np.sqrt(np.mean(x ** 2)))
            rms = np.sqrt(np.mean(loudest ** 2))
            self._calib_samples.append(loudest)
            self._calib_step += 1
            self._log(f"Palma {self._calib_step} capturada! (RMS: {rms:.4f})", "success")

            if self._calib_step >= self._calib_total:
                self._calib_finish()
            else:
                self._log("Proxima em 2s...", "dim")
                self.root.after(2000, self._calib_record_step)

        except Exception as e:
            self._log(f"Erro na gravacao: {e}", "error")
            self._calibrating = False
            self.gui_queue.put(("btn_calibrate_state", tk.NORMAL))

    def _calib_finish(self):
        self._calibrating = False

        fingerprint, samples_info = build_fingerprint_from_samples(self._calib_samples)
        save_fingerprint(fingerprint, samples_info=samples_info)
        self.fingerprint = fingerprint

        # Teste de consistência
        sims = []
        for s in self._calib_samples:
            feat = extract_spectral_features(s)
            sim = compute_similarity(feat, fingerprint)
            sims.append(sim)
        avg = np.mean(sims)

        quality = "EXCELENTE" if avg > 0.7 else ("BOM" if avg > 0.5 else "BAIXO")
        color = "success" if avg > 0.7 else ("info" if avg > 0.5 else "warning")

        self._log(f"Fingerprint salvo! Qualidade: {quality} (sim media: {avg:.3f})", color)
        self._log("=" * 45, "purple")

        self.gui_queue.put(("fp_card", "OK", FG_GREEN))
        self.gui_queue.put(("clap_card", f"0 / {CLAPS_REQUIRED}"))
        self.gui_queue.put(("btn_calibrate_state", tk.NORMAL))

    # ===========================================================
    # Listening (detecção)
    # ===========================================================
    def _toggle_listening(self):
        if self.listening:
            self._stop_listening()
        else:
            self._start_listening()

    def _start_listening(self):
        if self.fingerprint is None:
            messagebox.showwarning("Jarvis", "Calibre o fingerprint primeiro!")
            return
        if self._calibrating:
            return

        self.listening = True
        self.clap_times.clear()
        self.clap_count_display = 0
        self.gui_queue.put(("status", "  ONLINE", FG_GREEN))
        self.gui_queue.put(("btn_toggle", "PARAR"))
        self.gui_queue.put(("clap_card", f"0 / {CLAPS_REQUIRED}"))
        self._log("Escutando... palmas e voz ativados.", "success")

        # Voice listener
        try:
            self.voice_listener = VoiceListener(self.command_queue)
            self.voice_listener.start()
            self.gui_queue.put(("voice_card", "ON", FG_GREEN))
        except Exception as e:
            self._log(f"Voz desabilitada: {e}", "warning")
            self.gui_queue.put(("voice_card", "ERRO", FG_RED))

        # Audio stream
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=BLOCK_SIZE, callback=self._audio_callback,
        )
        self.stream.start()

        # Processing thread
        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._process_thread.start()

    def _stop_listening(self):
        self.listening = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if self.voice_listener:
            self.voice_listener.stop()
            self.voice_listener = None

        self.gui_queue.put(("status", "  OFFLINE", FG_DIM))
        self.gui_queue.put(("btn_toggle", "INICIAR"))
        self.gui_queue.put(("voice_card", "OFF", FG_DIM))
        self.gui_queue.put(("level", 0))
        self._log("Deteccao parada.", "dim")

    def _audio_callback(self, indata, frames, time_info, status):
        if not self.listening:
            return

        audio = indata[:, 0]
        rms = float(np.sqrt(np.mean(audio ** 2)))
        self.gui_queue.put(("level", rms))

        if not self._in_impact and rms > ENERGY_THRESHOLD:
            self._in_impact = True
            self._impact_start = time.time()
            self.audio_buffer = audio.copy()
        elif self._in_impact:
            self.audio_buffer = np.concatenate([self.audio_buffer, audio])
            if len(self.audio_buffer) >= self.window_samples:
                self._in_impact = False
                chunk = self.audio_buffer[:self.window_samples].copy()
                self.command_queue.put(("audio", chunk))
                self.audio_buffer = np.zeros(0, dtype=np.float32)
            elif time.time() - self._impact_start > 0.5:
                self._in_impact = False
                self.audio_buffer = np.zeros(0, dtype=np.float32)

    def _process_loop(self):
        while self.listening:
            try:
                event = self.command_queue.get(timeout=0.1)
            except queue.Empty:
                self._check_clap_timeout()
                continue

            event_type, data = event
            if event_type == "audio":
                self._process_audio(data)
            elif event_type == "voice":
                self._handle_action(data, "VOZ")

    def _process_audio(self, audio: np.ndarray):
        now = time.time()
        if now - self.last_trigger_time < COOLDOWN:
            return

        clap_detected, similarity = is_clap(audio, self.fingerprint)
        rms = float(np.sqrt(np.mean(audio ** 2)))

        if clap_detected:
            self.clap_times.append(now)
            count = len(self.clap_times)
            self._log(f"PALMA {count}/{CLAPS_REQUIRED}  (sim={similarity:.3f}  rms={rms:.4f})", "success")
            self.gui_queue.put(("clap_card", f"{count} / {CLAPS_REQUIRED}"))

            if count >= CLAPS_REQUIRED:
                self._handle_action("work", "PALMA")
                self.clap_times.clear()
                self.gui_queue.put(("clap_card", f"0 / {CLAPS_REQUIRED}"))
        elif similarity > 0.3:
            self._log(f"som descartado  (sim={similarity:.3f}  rms={rms:.4f})", "dim")

    def _check_clap_timeout(self):
        if not self.clap_times:
            return
        if time.time() - self.clap_times[0] > CLAP_WINDOW:
            n = len(self.clap_times)
            self.clap_times.clear()
            self.gui_queue.put(("clap_card", f"0 / {CLAPS_REQUIRED}"))
            self._log(f"Timeout: {n} palma(s) expirou, resetando.", "dim")

    def _handle_action(self, action: str, source: str):
        self.last_trigger_time = time.time()
        self._log(f">>> ATIVADO via {source}! <<<", "success")
        threading.Thread(target=execute_action, args=(action,), daemon=True).start()

    # ===========================================================
    # Lifecycle
    # ===========================================================
    def _on_close(self):
        self.listening = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.voice_listener:
            self.voice_listener.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
