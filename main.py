# --- 1. IMPORTATIONS ---
import os
import io
import base64
import time
from contextlib import asynccontextmanager
from typing import List, Tuple, Optional, Dict
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, Path, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import numpy as np
import soundfile as sf
import librosa
import matplotlib.pyplot as plt
from scipy.ndimage import label
import noisereduce as nr

from megamicros_aidb.query import AidbSession

# --- 2. CONFIGURATION ET CYCLE DE VIE ---
load_dotenv()
aidb_session = AidbSession()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Démarrage du serveur..."); DB_HOST = os.getenv("AIDB_HOST"); DB_LOGIN = os.getenv("AIDB_LOGIN"); DB_PASSWORD = os.getenv("AIDB_PASSWORD")
    if not all([DB_HOST, DB_LOGIN, DB_PASSWORD]):
        print("ERREUR CRITIQUE: Variables d'environnement manquantes.")
    else:
        try:
            print(f"Ouverture de la connexion vers {DB_HOST}..."); aidb_session.open(dbhost=DB_HOST, login=DB_LOGIN, password=DB_PASSWORD); print("Connexion à AIDB établie.")
        except Exception as e: print(f"ERREUR CRITIQUE de connexion à AIDB: {e}")
    yield
    print("Arrêt du serveur...");
    if aidb_session:
        aidb_session.close(); print("Connexion AIDB fermée.")

app = FastAPI(
    title="API d'Analyse et Classification Audio Porcin",
    description="API pour l'analyse de fichiers audio depuis la base de données AIDB.",
    version="API-FINAL",
    lifespan=lifespan
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# --- 3. MODÈLES DE DONNÉES (PYDANTIC) ---
class SegmentDetail(BaseModel):
    segment_number: int
    start_time_seconds: float
    end_time_seconds: float
    audio_base64: str
    predicted_animal_type: Optional[str] = None

class AnalysisResponse(BaseModel):
    message: str
    plot_image_base64: str
    segments_details: List[SegmentDetail]


# --- 4. FONCTIONS UTILITAIRES ---
F0_TRUIE_MAX_SEUIL = 200
F0_PORCELET_MIN_SEUIL = 400

def reduire_bruit_spectral(audio_data: np.ndarray, sr: int, debut_bruit: float, fin_bruit: float, facteur_reduction: float) -> np.ndarray:
    start_noise_sample = int(debut_bruit * sr); end_noise_sample = int(fin_bruit * sr)
    if start_noise_sample >= end_noise_sample or end_noise_sample > len(audio_data):
        return audio_data
    noise_clip = audio_data[start_noise_sample:end_noise_sample]
    return nr.reduce_noise(y=audio_data, y_noise=noise_clip, sr=sr, prop_decrease=facteur_reduction)

def detecter_et_fusionner_segments(audio_data: np.ndarray, sr: int, seuil_pct: int, duree_fenetre: float, duree_buffer: float) -> List[Tuple[float, float]]:
    frame_length = int(duree_fenetre * sr); hop_length = int(frame_length / 2)
    if frame_length <= 0: return []
    rms = librosa.feature.rms(y=audio_data.astype(np.float32), frame_length=frame_length, hop_length=hop_length)[0]
    if rms.size == 0: return []
    threshold = np.max(rms) * (seuil_pct / 100.0); groups, num_groups = label(rms > threshold)
    if num_groups == 0: return []
    raw_segments = []
    for i in range(1, num_groups + 1):
        indices = np.where(groups == i)[0]
        start_t = librosa.frames_to_time(indices[0], sr=sr, hop_length=hop_length)
        end_t = librosa.frames_to_time(indices[-1], sr=sr, hop_length=hop_length)
        raw_segments.append((start_t, end_t))
    total_duration = len(audio_data) / sr
    extended = [(max(0, s - duree_buffer), min(total_duration, e + duree_buffer)) for s, e in raw_segments]
    extended.sort(key=lambda x: x[0]); merged = [extended[0]]
    for start, end in extended[1:]:
        if start <= merged[-1][1]: merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else: merged.append((start, end))
    return merged

def generer_graphique_rms(audio_data: np.ndarray, sr: int, segments: List[Tuple[float, float]], seuil_pct: int) -> bytes:
    rms = librosa.feature.rms(y=audio_data, frame_length=2048, hop_length=512)[0]
    threshold = np.max(rms) * (seuil_pct / 100.0)
    fig, ax = plt.subplots(figsize=(15, 5)); time_axis_rms = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)
    ax.plot(time_axis_rms, rms, label='RMS du signal nettoyé', alpha=0.8)
    ax.axhline(y=threshold, color='r', linestyle='--', label=f'Seuil ({seuil_pct}%)')
    if segments:
        ax.plot([], [], color='red', alpha=0.4, linewidth=10, label='Segment Détecté')
        for start, end in segments: ax.axvspan(start, end, color='red', alpha=0.3)
    ax.set_title('Analyse RMS sur Signal Nettoyé et Segments Détectés'); ax.set_xlabel('Temps (s)'); ax.set_ylabel('Amplitude RMS'); ax.legend(); ax.grid(True)
    buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight'); plt.close(fig); buf.seek(0)
    return buf.getvalue()

def get_f0_and_class(segment_data, sr):
    try:
        if len(segment_data) / sr < 0.2: return "Segment trop court"
        f0, vf, _ = librosa.pyin(segment_data, sr=sr, fmin=50, fmax=2000)
        f0_v = f0[vf & ~np.isnan(f0)]
        if f0_v.size > 0:
            f0_min, f0_max = float(np.min(f0_v)), float(np.max(f0_v))
            if f0_max < F0_TRUIE_MAX_SEUIL: return "Truie"
            elif f0_min > F0_PORCELET_MIN_SEUIL: return "Porcelet"
            else: return "Indéterminé"
        return "Indéterminé (F0 non détectée)"
    except Exception as e: print(f"Erreur F0: {e}"); return "Erreur analyse F0"


# --- 5. ENDPOINTS DE L'API ---
@app.get("/", summary="Statut de l'API")
async def read_root():
    return {"status": "API d'analyse audio en ligne", "documentation": "/docs"}

@app.post("/analyze/{audio_id}", response_model=AnalysisResponse)
async def analyze_audio(
    audio_id: int=Path(...),
    seuil_pct: int=Form(70),
    duree_fenetre: float=Form(1.0),
    duree_buffer: float=Form(1.0),
    debut_bruit: float=Form(2.0),
    fin_bruit: float=Form(5.0),
    facteur_reduction: float=Form(1.5)
):
    try:
        audio_bytes = aidb_session.downloadSourcefile(id=audio_id, as_wav=True, timeout=300)
        if not audio_bytes: raise HTTPException(status_code=404, detail="Fichier non trouvé.")
        audio_data, sampling_rate = sf.read(io.BytesIO(audio_bytes), dtype='float32')
        if audio_data.ndim > 1: audio_data = audio_data[:, 0]
        
        audio_nettoye = reduire_bruit_spectral(audio_data, sampling_rate, float(debut_bruit), float(fin_bruit), float(facteur_reduction))
        segments_time = detecter_et_fusionner_segments(audio_nettoye, sampling_rate, int(seuil_pct), float(duree_fenetre), float(duree_buffer))
        plot_bytes = generer_graphique_rms(audio_nettoye, sampling_rate, segments_time, int(seuil_pct))
        
        segments_details = []
        for i, (start_t, end_t) in enumerate(segments_time):
            start_sample = int(start_t * sampling_rate); end_sample = int(end_t * sampling_rate)
            segment_data = audio_nettoye[start_sample:end_sample]
            
            animal_type = get_f0_and_class(segment_data, sampling_rate)
            
            seg_buf = io.BytesIO(); sf.write(seg_buf, segment_data, sampling_rate, format='WAV', subtype='PCM_16')
            audio_base64 = base64.b64encode(seg_buf.getvalue()).decode('utf-8')
            
            segments_details.append(SegmentDetail(
                segment_number=i + 1, start_time_seconds=start_t, end_time_seconds=end_t,
                audio_base64=audio_base64, predicted_animal_type=animal_type
            ))
        
        return AnalysisResponse(
            message=f"{len(segments_details)} segments trouvés après réduction de bruit.",
            plot_image_base64=base64.b64encode(plot_bytes).decode('utf-8'),
            segments_details=segments_details
        )
            
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur interne: {e}")
