from logging import Logger
from typing import Dict, Any
from faster_whisper import WhisperModel
import requests
import tempfile
import os
import re
from dataclasses import dataclass
from typing import List


@dataclass
class TranscribedSequence:
    start: float
    end: float
    duration: float
    text: str
    number: int


@dataclass
class TranscriptionResult:
    audio_duration: float
    sequences: List[TranscribedSequence]
    full_text: str


class AudioTranscriber:
    def __init__(self, logger:Logger, model_size="tiny", device="cpu", language=None):
        self.model_size = model_size
        self.logger =logger
        self.device = device
        self.language = language

        # Chargement du modèle Whisper
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="int8"
        )

    def _download_temp_audio(self, url: str) -> str:
        """Télécharge un fichier audio dans un fichier temporaire."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            temp_path = tmp.name

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        with open(temp_path, "wb") as f:
            f.write(response.content)

        return temp_path

    def _extract_numbers(self, text: str):
        """Retourne une liste d'entiers trouvés dans le texte."""
        return list(map(int, re.findall(r"\d+", text)))

    def transcribe_audio(self, url: str) -> TranscriptionResult:
        """
        Télécharge, transcrit et renvoie un objet structuré :
        {
            "audio_duration": float,
            "sequences": [
                {
                    "start": float,
                    "end": float,
                    "duration": float,
                    "text": str,
                    "numbers": [int, ...]
                }
            ]
        }
        """
        temp_path = self._download_temp_audio(url)

        try:
            segments, info = self.model.transcribe(
                temp_path,
                beam_size=5,
                language=self.language,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            sequences: List[TranscribedSequence] = []

            for seg in segments:
                text = seg.text.strip()
                numbers = self._extract_numbers(text)

                if numbers:
                    sequences.append(
                        TranscribedSequence(
                            start=seg.start,
                            end=seg.end,
                            duration=seg.end - seg.start,
                            text=text,
                            number=numbers[0]
                        )
                    )

            self.logger.debug(f'Debug sequences : {sequences}')
            return TranscriptionResult(
                audio_duration=info.duration,
                sequences=sequences[-6:], # get the last 6 numbers in the sequence
                full_text=" ".join([s.text.strip() for s in sequences])
            )

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
