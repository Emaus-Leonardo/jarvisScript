# ============================================================
# Jarvis - Módulo de Reconhecimento de Voz
# ============================================================

import speech_recognition as sr
import threading
import queue

from config import WAKE_PHRASE, VOICE_COMMANDS


class VoiceListener:
    """Escuta continuamente por comandos de voz em thread separada."""

    def __init__(self, command_queue: queue.Queue):
        self.command_queue = command_queue
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.running = False
        self._thread = None

        # Calibrar para ruído ambiente
        with self.microphone as source:
            print("[VOZ] Calibrando microfone para ruído ambiente...")
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
            print("[VOZ] Calibração concluída.")

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        print("[VOZ] Escutando comandos de voz...")

    def stop(self):
        self.running = False

    def _listen_loop(self):
        while self.running:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)

                try:
                    text = self.recognizer.recognize_google(audio, language="pt-BR").lower()
                    print(f"[VOZ] Ouvido: \"{text}\"")
                    self._process_text(text)
                except sr.UnknownValueError:
                    pass  # não entendeu — normal
                except sr.RequestError as e:
                    print(f"[VOZ] Erro no serviço de reconhecimento: {e}")

            except sr.WaitTimeoutError:
                pass  # timeout — normal, continua escutando
            except Exception as e:
                print(f"[VOZ] Erro: {e}")

    def _process_text(self, text: str):
        """Verifica se o texto contém wake word + comando."""
        if WAKE_PHRASE not in text:
            return

        # Remove a wake word e procura o comando
        after_wake = text.split(WAKE_PHRASE, 1)[1].strip()
        # Remove pontuação e vírgulas comuns
        after_wake = after_wake.strip(",. ")

        for trigger, action in VOICE_COMMANDS.items():
            if trigger in after_wake:
                print(f"[VOZ] Comando reconhecido: '{trigger}' → ação '{action}'")
                self.command_queue.put(("voice", action))
                return

        print(f"[VOZ] Wake word detectada mas comando não reconhecido: \"{after_wake}\"")
