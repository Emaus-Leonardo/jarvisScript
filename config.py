# ============================================================
# Jarvis - Configuração
# ============================================================

# --- Áudio ---
SAMPLE_RATE = 44100
BLOCK_SIZE = 1024          # amostras por bloco do stream
DETECTION_WINDOW = 0.15    # segundos de áudio para análise de impacto
COOLDOWN = 1.5             # segundos entre detecções (evita dupla contagem)

# --- Detecção de palmas ---
ENERGY_THRESHOLD = 0.02         # limiar mínimo de energia RMS para trigger
CLAP_SIMILARITY_THRESHOLD = 0.6 # correlação mínima com fingerprint (0-1)
CLAPS_REQUIRED = 2               # quantas palmas para ativar
CLAP_WINDOW = 2.0                # segundos máx entre primeira e última palma

# --- Fingerprint espectral ---
FINGERPRINT_FILE = "data/clap_fingerprint.json"
N_FFT = 2048
FREQ_BANDS = [
    (200, 800),     # banda baixa — palma tem energia aqui
    (800, 2000),    # banda média
    (2000, 6000),   # banda alta — palma tem pico característico
    (6000, 12000),  # presença aguda
]

# --- Reconhecimento de voz ---
WAKE_PHRASE = "jarvis"
VOICE_COMMANDS = {
    "bora trabalhar": "work",
    "abrir tudo": "work",
}

# --- Programas para abrir ---
PROGRAMS = {
    "work": [
        {"name": "Spotify", "path": r"C:\Users\kirit\AppData\Roaming\Spotify\Spotify.exe"},
        {"name": "Discord", "path": r"C:\Users\kirit\AppData\Local\Discord\Update.exe", "args": ["--processStart", "Discord.exe"]},
        {"name": "Sakura Sound", "path": r"C:\Users\kirit\AppData\Local\Programs\Sakura Sound\Sakura Sound.exe"},
        {"name": "Antigravity", "path": r"D:\antigravity\Antigravity\Antigravity.exe"},
    ],
}
