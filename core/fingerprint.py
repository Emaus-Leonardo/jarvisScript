# ============================================================
# Jarvis - Módulo de Fingerprint Espectral
# ============================================================
# Grava palmas do usuário, extrai perfil espectral e salva.
# Na detecção, compara o espectro do som capturado com o perfil.

import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal import butter, filtfilt
import json
import os
from datetime import datetime

from config import (
    SAMPLE_RATE, N_FFT, FREQ_BANDS, FINGERPRINT_FILE,
    CLAP_SIMILARITY_THRESHOLD,
)


def bandpass_filter(data: np.ndarray, low: float, high: float, fs: int, order: int = 4) -> np.ndarray:
    """Aplica filtro passa-banda Butterworth."""
    nyq = fs / 2
    b, a = butter(order, [low / nyq, high / nyq], btype="band")
    return filtfilt(b, a, data)


def extract_spectral_features(audio: np.ndarray, fs: int = SAMPLE_RATE) -> np.ndarray:
    """
    Extrai vetor de features espectrais de um trecho de áudio.

    Features por banda:
      - energia relativa (proporção da energia total)
      - centroide espectral normalizado
      - taxa de cruzamento por zero (ZCR)
      - rolloff espectral
    """
    if len(audio) < N_FFT:
        audio = np.pad(audio, (0, N_FFT - len(audio)))

    # Centraliza a janela FFT ao redor do pico de energia
    # Pad simétrico garante que o pico fique sempre no centro exato
    peak_idx = int(np.argmax(np.abs(audio)))
    half = N_FFT // 2
    padded = np.pad(audio, (half, half), mode='constant')
    segment = padded[peak_idx:peak_idx + N_FFT]

    # Janela de Hann para reduzir vazamento espectral
    windowed = segment * np.hanning(N_FFT)

    # FFT
    spectrum = np.abs(rfft(windowed))
    freqs = rfftfreq(N_FFT, 1.0 / fs)
    total_energy = np.sum(spectrum ** 2) + 1e-10

    features = []
    for low, high in FREQ_BANDS:
        mask = (freqs >= low) & (freqs < high)
        band_spectrum = spectrum[mask]
        band_freqs = freqs[mask]

        if len(band_spectrum) == 0:
            features.extend([0.0, 0.0, 0.0, 0.0])
            continue

        # Energia relativa da banda
        band_energy = np.sum(band_spectrum ** 2)
        rel_energy = band_energy / total_energy

        # Centroide espectral normalizado dentro da banda
        if band_energy > 0:
            centroid = np.sum(band_freqs * band_spectrum ** 2) / (band_energy + 1e-10)
            centroid_norm = (centroid - low) / (high - low + 1e-10)
        else:
            centroid_norm = 0.0

        # ZCR (no domínio do tempo, filtrado para a banda)
        try:
            filtered = bandpass_filter(segment, low, high, fs)
            zcr = np.sum(np.abs(np.diff(np.sign(filtered)))) / (2 * len(filtered))
        except Exception:
            zcr = 0.0

        # Rolloff espectral (freq abaixo da qual está 85% da energia da banda)
        cumsum = np.cumsum(band_spectrum ** 2)
        rolloff_idx = np.searchsorted(cumsum, 0.85 * cumsum[-1])
        rolloff_norm = rolloff_idx / (len(band_spectrum) + 1e-10)

        features.extend([rel_energy, centroid_norm, zcr, rolloff_norm])

    # Features globais adicionais (usando segment centrado no pico)
    # Decaimento temporal (razão energia 2ª metade / 1ª metade)
    half = len(segment) // 2
    e1 = np.sum(segment[:half] ** 2) + 1e-10
    e2 = np.sum(segment[half:] ** 2) + 1e-10
    decay_ratio = e2 / e1

    # Crest factor (pico / RMS)
    rms = np.sqrt(np.mean(segment ** 2)) + 1e-10
    crest = np.max(np.abs(segment)) / rms

    features.extend([decay_ratio, crest])

    return np.array(features, dtype=np.float64)


def compute_similarity(features: np.ndarray, fingerprint: np.ndarray) -> float:
    """
    Calcula similaridade entre features extraídas e o fingerprint salvo.
    Usa correlação de Pearson normalizada → resultado entre -1 e 1.
    """
    if features.shape != fingerprint.shape:
        return 0.0

    f = features - np.mean(features)
    g = fingerprint - np.mean(fingerprint)

    norm_f = np.linalg.norm(f) + 1e-10
    norm_g = np.linalg.norm(g) + 1e-10

    return float(np.dot(f, g) / (norm_f * norm_g))


def is_clap(audio: np.ndarray, fingerprint: np.ndarray) -> tuple[bool, float]:
    """Retorna (é_palma, similaridade)."""
    features = extract_spectral_features(audio)
    sim = compute_similarity(features, fingerprint)
    return sim >= CLAP_SIMILARITY_THRESHOLD, sim


def save_fingerprint(fingerprint: np.ndarray, samples_info: list[dict] = None, path: str = FINGERPRINT_FILE):
    """Salva fingerprint em JSON com metadados da calibração."""
    data = {
        "version": 1,
        "created_at": datetime.now().isoformat(),
        "sample_rate": SAMPLE_RATE,
        "n_fft": N_FFT,
        "freq_bands": FREQ_BANDS,
        "num_samples_used": len(samples_info) if samples_info else 0,
        "samples_info": samples_info or [],
        "fingerprint": fingerprint.tolist(),
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[+] Fingerprint salvo em {path}")


def load_fingerprint(path: str = FINGERPRINT_FILE) -> np.ndarray | None:
    """Carrega fingerprint do JSON. Compatível com .npy legado."""
    if not os.path.exists(path):
        # Tenta carregar .npy legado
        npy_path = path.replace(".json", ".npy")
        if os.path.exists(npy_path):
            print(f"[INFO] Migrando fingerprint legado {npy_path} → {path}")
            fp = np.load(npy_path)
            save_fingerprint(fp, path=path)
            return fp
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"[INFO] Fingerprint carregado (criado em {data.get('created_at', '?')}, {data.get('num_samples_used', '?')} amostras)")
    return np.array(data["fingerprint"], dtype=np.float64)


def build_fingerprint_from_samples(samples: list[np.ndarray]) -> tuple[np.ndarray, list[dict]]:
    """Constrói fingerprint médio a partir de várias amostras de palma.
    Retorna (fingerprint, info de cada amostra)."""
    all_features = []
    samples_info = []
    for i, s in enumerate(samples):
        feat = extract_spectral_features(s)
        all_features.append(feat)
        samples_info.append({
            "index": i + 1,
            "rms": float(np.sqrt(np.mean(s ** 2))),
            "peak": float(np.max(np.abs(s))),
            "features": feat.tolist(),
        })
    fingerprint = np.mean(all_features, axis=0)
    return fingerprint, samples_info
