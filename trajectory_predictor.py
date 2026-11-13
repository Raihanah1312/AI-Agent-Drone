
import math

EARTH_RADIUS_M = 6371000.0


def predict_position(lat, lon, speed_mps, heading_deg, dt_s):
    """
    Prediksi koordinat pesawat berdasarkan kecepatan
    dan heading konstan.

    heading 0 = utara, 90 = timur.
    dt_s = selisih waktu dari pengamatan (detik).
    """

    distance_m = speed_mps * dt_s
    angular_distance = distance_m / EARTH_RADIUS_M

    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    bearing = math.radians(heading_deg)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1)
        * math.sin(angular_distance)
        * math.cos(bearing)
    )

    lon2 = lon1 + math.atan2(
        math.sin(bearing)
        * math.sin(angular_distance)
        * math.cos(lat1),
        math.cos(angular_distance)
        - math.sin(lat1) * math.sin(lat2)
    )

    return (
        math.degrees(lat2),
        (math.degrees(lon2) + 180) % 360 - 180
    )


if __name__ == "__main__":
    # Pengujian sederhana tanpa OpenSky
    lat, lon = predict_position(
        lat=-6.1754,
        lon=106.8272,
        speed_mps=100.0,
        heading_deg=90.0,
        dt_s=60.0
    )

    print("=== TEST PREDIKSI POSISI PESAWAT ===")
    print(f"Latitude  : {lat:.6f}")
    print(f"Longitude : {lon:.6f}")
    print("Pergerakan: 6 km ke arah timur (simulasi)")
