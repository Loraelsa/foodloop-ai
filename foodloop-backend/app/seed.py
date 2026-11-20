"""Demo vendors/NGOs. Names are fictional; locality centroids are approximate public map coordinates."""
LOCALITY_XY = {
    "BTM": (12.9166, 77.6101), "HSR": (12.9116, 77.6389), "Koramangala": (12.9352, 77.6245),
    "JP Nagar": (12.9063, 77.5857), "Whitefield": (12.9698, 77.7500), "Indiranagar": (12.9784, 77.6408),
    "Jayanagar": (12.9250, 77.5938), "Marathahalli": (12.9569, 77.7011), "Bannerghatta Road": (12.8890, 77.5970),
    "Bellandur": (12.9304, 77.6784), "Electronic City": (12.8452, 77.6602), "Brigade Road": (12.9716, 77.6070),
    "Sarjapur Road": (12.9100, 77.6850), "Ulsoor": (12.9810, 77.6200), "MG Road": (12.9756, 77.6068),
    "Banashankari": (12.9255, 77.5468), "Kalyan Nagar": (13.0270, 77.6400), "Richmond Road": (12.9660, 77.6000),
    "Frazer Town": (12.9985, 77.6130), "Malleshwaram": (13.0035, 77.5646),
}
_names = ["Saffron Tiffin Room", "Udupi Junction", "The Bread Basket", "Mithai Mahal", "Curd & Co.",
          "Biryani Boulevard", "Green Basket Fresh", "Dosa Dynasty", "Punjab Rasoi", "Malabar Meals"]
_locs = ["Koramangala", "Jayanagar", "Indiranagar", "Malleshwaram", "BTM", "HSR", "JP Nagar", "Marathahalli", "MG Road", "Whitefield"]
VENDORS = [dict(name=n, locality=l, lat=LOCALITY_XY[l][0], lng=LOCALITY_XY[l][1], status="approved") for n, l in zip(_names, _locs)]
NGOS = [dict(name="Annapurna Seva Trust", lat=12.9299, lng=77.5826, capacity_kg=120, status="verified"),
        dict(name="Robin Hood Collective", lat=12.9279, lng=77.6271, capacity_kg=80, status="verified")]
