"""Klien HTTP Hermes Gateway lokal untuk demonstrasi skripsi (tanpa kontrol drone).

Lokasi standar native Windows:
  %LOCALAPPDATA%\\hermes\\.env

Jangan letakkan API_SERVER_KEY pada React, git, atau respons FastAPI.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


HERMES_API_BASE = "http://127.0.0.1:8642"


class HermesGatewayError(RuntimeError):
    pass


def _read_env_key(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    try:
        rows = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise HermesGatewayError("Tidak dapat membaca konfigurasi Hermes lokal.") from exc
    value = None
    for row in rows:
        stripped = row.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw = stripped.split("=", 1)
        if key.strip() == name:
            value = raw.strip().strip('"').strip("'")
    return value


def get_hermes_api_key() -> str:
    """Ambil kunci dari environment atau .env Hermes di LOCALAPPDATA.

    Dibaca ulang setiap permintaan; perubahan kunci tidak mengharuskan restart
    FastAPI. Proses Hermes Gateway tetap perlu restart jika konfigurasinya berubah.
    """
    key = os.environ.get("API_SERVER_KEY", "").strip()
    if not key:
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            key = _read_env_key(Path(local) / "hermes" / ".env", "API_SERVER_KEY") or ""
    if not key:
        raise HermesGatewayError(
            "API_SERVER_KEY Hermes tidak ditemukan. Periksa file "
            "%LOCALAPPDATA%\\hermes\\.env dan konfigurasi gateway."
        )
    return key


def ask_hermes(system_prompt: str, user_prompt: str) -> str:
    """Meminta penjelasan, bukan keputusan kontrol penerbangan.

    Timeout baca 90 detik karena model gratis OpenRouter bisa lambat.
    """
    try:
        response = requests.post(
            f"{HERMES_API_BASE}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {get_hermes_api_key()}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "model": "hermes-agent",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            timeout=(5, 90),
        )
    except requests.Timeout as exc:
        raise HermesGatewayError(
            "Hermes tidak merespons dalam batas waktu. Coba lagi atau periksa model OpenRouter."
        ) from exc
    except requests.RequestException as exc:
        raise HermesGatewayError(
            "Tidak dapat menghubungi Hermes pada 127.0.0.1:8642. "
            "Pastikan 'hermes gateway' masih berjalan."
        ) from exc

    if response.status_code in (401, 403):
        raise HermesGatewayError(
            "API_SERVER_KEY ditolak Hermes. Periksa token lalu restart gateway."
        )
    if response.status_code == 429:
        raise HermesGatewayError("Hermes/OpenRouter membatasi permintaan (rate limit).")
    if not response.ok:
        # Jangan membocorkan respons upstream yang berpotensi berisi kredensial.
        raise HermesGatewayError(
            f"Hermes gagal (HTTP {response.status_code}); "
            "periksa terminal Gateway dan model OpenRouter aktif."
        )

    try:
        payload: dict[str, Any] = response.json()
        message = payload["choices"][0]["message"]["content"]
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise HermesGatewayError("Struktur respons Hermes tidak dikenal.") from exc
    if not isinstance(message, str) or not message.strip():
        raise HermesGatewayError("Hermes tidak memberikan teks jawaban.")
    # Hermes kadang mengembalikan pesan kegagalan provider sebagai teks respons.
    if "provider said: http" in message.lower() or "model is unavailable for free" in message.lower():
        raise HermesGatewayError(
            "Model OpenRouter sedang tidak tersedia. Periksa model Hermes aktif."
        )
    return message.strip()[:10000]
