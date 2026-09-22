"""District reference data for the five demo states: district HQ coordinates (approximate,
town centre) and a representative PIN code. Used to seed demo partners and to locate an
applicant from a PIN code when the phone cannot share GPS. Offline, no geocoding API."""

from dataclasses import dataclass


@dataclass(frozen=True)
class District:
    code: str
    name: str
    state_code: str
    lat: float
    lng: float
    pincode: str
    languages: tuple[str, ...]


def _d(code: str, name: str, state: str, lat: float, lng: float, pin: str, langs: tuple[str, ...]) -> District:
    return District(code, name, state, lat, lng, pin, langs)


GJ = ("gu", "hi", "en")
RJ = ("hi", "en")
UP = ("hi", "ur", "en")
MH = ("mr", "hi", "en")
TN = ("ta", "en")

DISTRICTS: list[District] = [
    _d("GJ-DAH", "Dahod", "GJ", 22.8345, 74.2553, "389151", GJ),
    _d("GJ-PAN", "Godhra (Panchmahal)", "GJ", 22.7751, 73.6147, "389001", GJ),
    _d("GJ-VAD", "Vadodara", "GJ", 22.3072, 73.1812, "390001", GJ),
    _d("GJ-CHU", "Chhota Udaipur", "GJ", 22.3048, 74.0115, "391165", GJ),
    _d("GJ-AHM", "Ahmedabad", "GJ", 23.0225, 72.5714, "380001", GJ),
    _d("GJ-SUR", "Surat", "GJ", 21.1702, 72.8311, "395003", GJ),
    _d("GJ-RAJ", "Rajkot", "GJ", 22.3039, 70.8022, "360001", GJ),
    _d("GJ-BHA", "Bhavnagar", "GJ", 21.7645, 72.1519, "364001", GJ),
    _d("GJ-MEH", "Mehsana", "GJ", 23.5880, 72.3693, "384001", GJ),
    _d("GJ-BAN", "Palanpur (Banaskantha)", "GJ", 24.1724, 72.4346, "385001", GJ),
    _d("RJ-BAR", "Barmer", "RJ", 25.7521, 71.3967, "344001", RJ),
    _d("RJ-JSM", "Jaisalmer", "RJ", 26.9157, 70.9083, "345001", RJ),
    _d("RJ-JDP", "Jodhpur", "RJ", 26.2389, 73.0243, "342001", RJ),
    _d("RJ-BLT", "Balotra", "RJ", 25.8324, 72.2400, "344022", RJ),
    _d("RJ-JAL", "Jalore", "RJ", 25.3450, 72.6156, "343001", RJ),
    _d("RJ-PAL", "Pali", "RJ", 25.7711, 73.3234, "306401", RJ),
    _d("RJ-BIK", "Bikaner", "RJ", 28.0229, 73.3119, "334001", RJ),
    _d("RJ-AJM", "Ajmer", "RJ", 26.4499, 74.6399, "305001", RJ),
    _d("RJ-JAI", "Jaipur", "RJ", 26.9124, 75.7873, "302001", RJ),
    _d("RJ-UDA", "Udaipur", "RJ", 24.5854, 73.7125, "313001", RJ),
    _d("UP-LKO", "Lucknow", "UP", 26.8467, 80.9462, "226001", UP),
    _d("UP-BBK", "Barabanki", "UP", 26.9270, 81.1830, "225001", UP),
    _d("UP-STP", "Sitapur", "UP", 27.5680, 80.6790, "261001", UP),
    _d("UP-UNN", "Unnao", "UP", 26.5393, 80.4878, "209801", UP),
    _d("UP-RBL", "Raebareli", "UP", 26.2309, 81.2336, "229001", UP),
    _d("UP-HRD", "Hardoi", "UP", 27.3980, 80.1310, "241001", UP),
    _d("UP-KNP", "Kanpur", "UP", 26.4499, 80.3319, "208001", UP),
    _d("UP-AYD", "Ayodhya", "UP", 26.7922, 82.1998, "224001", UP),
    _d("UP-VNS", "Varanasi", "UP", 25.3176, 82.9739, "221001", UP),
    _d("UP-PRY", "Prayagraj", "UP", 25.4358, 81.8463, "211001", UP),
    _d("MH-PUN", "Pune", "MH", 18.5204, 73.8567, "411001", MH),
    _d("MH-MUM", "Mumbai", "MH", 19.0760, 72.8777, "400001", MH),
    _d("MH-NAG", "Nagpur", "MH", 21.1458, 79.0882, "440001", MH),
    _d("MH-NAS", "Nashik", "MH", 19.9975, 73.7898, "422001", MH),
    _d("MH-CSN", "Chhatrapati Sambhajinagar", "MH", 19.8762, 75.3433, "431001", MH),
    _d("MH-SOL", "Solapur", "MH", 17.6599, 75.9064, "413001", MH),
    _d("MH-KOL", "Kolhapur", "MH", 16.7050, 74.2433, "416003", MH),
    _d("MH-AMR", "Amravati", "MH", 20.9374, 77.7796, "444601", MH),
    _d("MH-LAT", "Latur", "MH", 18.4088, 76.5604, "413512", MH),
    _d("MH-NAN", "Nanded", "MH", 19.1383, 77.3210, "431601", MH),
    _d("TN-MDU", "Madurai", "TN", 9.9252, 78.1198, "625001", TN),
    _d("TN-DGL", "Dindigul", "TN", 10.3624, 77.9695, "624001", TN),
    _d("TN-VNR", "Virudhunagar", "TN", 9.5851, 77.9579, "626001", TN),
    _d("TN-SVG", "Sivaganga", "TN", 9.8433, 78.4809, "630561", TN),
    _d("TN-THN", "Theni", "TN", 10.0104, 77.4768, "625531", TN),
    _d("TN-RMD", "Ramanathapuram", "TN", 9.3639, 78.8395, "623501", TN),
    _d("TN-TRY", "Tiruchirappalli", "TN", 10.7905, 78.7047, "620001", TN),
    _d("TN-CHN", "Chennai", "TN", 13.0827, 80.2707, "600001", TN),
    _d("TN-CBE", "Coimbatore", "TN", 11.0168, 76.9558, "641001", TN),
    _d("TN-TNV", "Tirunelveli", "TN", 8.7139, 77.7567, "627001", TN),
]

BY_CODE = {d.code: d for d in DISTRICTS}
BY_PIN = {d.pincode: d for d in DISTRICTS}


def district_for_pincode(pincode: str) -> District | None:
    """Exact demo PIN first, then the nearest district sharing the 3-digit sorting prefix."""
    if pincode in BY_PIN:
        return BY_PIN[pincode]
    matches = [d for d in DISTRICTS if d.pincode[:3] == pincode[:3]]
    return matches[0] if matches else None
