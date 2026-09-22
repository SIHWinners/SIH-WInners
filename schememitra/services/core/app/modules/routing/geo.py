import math

EARTH_RADIUS_KM = 6371.0088
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """Cheap prefilter so SQLite only computes haversine for nearby rows."""
    dlat = radius_km / 111.0
    dlng = radius_km / max(1e-6, 111.0 * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def geohash(lat: float, lng: float, precision: int = 6) -> str:
    """Standard geohash; precision 6 ≈ 1.2 km cells, used as the partner-search cache key."""
    lat_rng, lng_rng = [-90.0, 90.0], [-180.0, 180.0]
    bits, bit, ch, even = [16, 8, 4, 2, 1], 0, 0, True
    out: list[str] = []
    while len(out) < precision:
        rng, value = (lng_rng, lng) if even else (lat_rng, lat)
        mid = (rng[0] + rng[1]) / 2
        if value >= mid:
            ch |= bits[bit]
            rng[0] = mid
        else:
            rng[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            out.append(_BASE32[ch])
            bit, ch = 0, 0
    return "".join(out)
