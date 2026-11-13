import os
import time
import threading
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID")
CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET")

TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/"
    "opensky-network/protocol/openid-connect/token"
)

API_URL = "https://opensky-network.org/api/states/all"

# Default lama dipertahankan untuk kompatibilitas
PARAMS = {
    "lamin": -6.5,
    "lamax": -5.8,
    "lomin": 106.5,
    "lomax": 107.2,
}

_token_lock = threading.Lock()
_token = None
_token_valid_until = 0.0


def get_access_token():
    global _token, _token_valid_until

    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError(
            "OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET "
            "tidak ditemukan di .env"
        )

    with _token_lock:
        if _token and time.monotonic() < _token_valid_until:
            return _token

        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            timeout=30,
        )

        response.raise_for_status()
        body = response.json()

        _token = body["access_token"]
        expires_in = int(body.get("expires_in", 1800))

        _token_valid_until = (
            time.monotonic() + max(0, expires_in - 60)
        )

        return _token


def get_aircraft_states(bbox=None):
    """
    Jika bbox diberikan, OpenSky menggunakan wilayah dinamis.
    Jika tidak diberikan, tetap memakai bounding box Jakarta lama.
    """

    params = dict(bbox) if bbox is not None else PARAMS.copy()

    response = requests.get(
        API_URL,
        headers={
            "Authorization": f"Bearer {get_access_token()}"
        },
        params=params,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    data = get_aircraft_states()
    states = data.get("states") or []

    print("=== OPENSKY AIR TRAFFIC ===")
    print(f"Jumlah pesawat: {len(states)}")
