"""Work out the province from a town name, for sources (like Eskom) that only give the town."""
import re

PROVINCES = ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo", "Mpumalanga",
             "North West", "Northern Cape", "Western Cape"]

TOWNS = {
    "Gauteng": ["Sunninghill", "Midrand", "Johannesburg", "Joburg", "Germiston", "Pretoria", "Tshwane",
                "Centurion", "Sandton", "Rosebank", "Randburg", "Roodepoort", "Soweto", "Benoni", "Boksburg",
                "Brakpan", "Springs", "Kempton Park", "Alberton", "Vereeniging", "Vanderbijlpark",
                "Krugersdorp", "Randfontein", "Bedfordview", "Edenvale", "Ekurhuleni", "Heidelberg",
                "Megawatt Park", "Rosherville", "Meyerton", "Nigel", "Braamfontein", "Carletonville",
                "Zonderwater", "Cullinan"],
    "Mpumalanga": ["Witbank", "eMalahleni", "Emalahleni", "Standerton", "Balfour", "Middelburg", "Secunda",
                   "Ermelo", "Mbombela", "Nelspruit", "Kriel", "Kendal", "Hendrina", "Arnot", "Duvha", "Matla",
                   "Tutuka", "Majuba", "Volksrust", "Komati", "Camden", "Grootvlei", "Kusile", "Ogies",
                   "Bethal", "Piet Retief", "Mkhondo", "Lydenburg", "Barberton", "Delmas", "Hazyview",
                   "Sabie", "Mashishing", "KwaMhlanga", "Kwa- Mhlanga", "Kwa-Mhlanga"],
    "Limpopo": ["Lephalale", "Ellisras", "Polokwane", "Matimba", "Medupi", "Tzaneen", "Thohoyandou",
                "Mokopane", "Musina", "Phalaborwa", "Bela-Bela", "Modimolle", "Giyani", "Louis Trichardt"],
    "Free State": ["Deneysville", "Dealesville", "Bloemfontein", "Welkom", "Kroonstad", "Bethlehem",
                   "Sasolburg", "Parys", "Harrismith", "Phuthaditjhaba", "Virginia"],
    "Northern Cape": ["De Aar", "Springbok", "Kimberley", "Upington", "Kuruman", "Kathu", "Postmasburg",
                      "Prieska", "Calvinia"],
    "Western Cape": ["Cape Town", "Bellville", "Koeberg", "Stellenbosch", "Paarl", "George", "Worcester",
                     "Mossel Bay", "Knysna", "Atlantis", "Brackenfell", "Durbanville", "Somerset West",
                     "Oudtshoorn", "Beaufort West", "Vredenburg", "Saldanha"],
    "Eastern Cape": ["Gqeberha", "Port Elizabeth", "East London", "Mthatha", "Umtata", "Makhanda",
                     "Grahamstown", "Komani", "Queenstown", "Uitenhage", "Kariega", "Bhisho", "Bisho",
                     "King William", "Qonce", "Butterworth", "Graaff-Reinet", "Port Alfred", "Jeffreys Bay",
                     "Cradock", "Nxuba", "Zwelitsha"],
    "KwaZulu-Natal": ["Durban", "eThekwini", "Pietermaritzburg", "Msunduzi", "Newcastle", "Richards Bay",
                      "Empangeni", "Ladysmith", "Ulundi", "Vryheid", "Pinetown", "Umhlanga", "Port Shepstone",
                      "Estcourt", "Dundee", "Kokstad", "Stanger", "KwaDukuza", "Ingagane", "Drakensberg",
                      "Midmar"],
    "North West": ["Klerksdorp", "Rustenburg", "Mahikeng", "Mafikeng", "Potchefstroom", "Brits",
                   "Lichtenburg", "Vryburg", "Zeerust", "Orkney", "Hartbeespoort", "Mmabatho", "Boskop"],
}

_RULES = [(re.compile(r"\b" + re.escape(t) + r"\b", re.I), prov) for prov, ts in TOWNS.items() for t in ts]


def province_of(location):
    """Return the province for a location like 'Sunninghill' or 'Lephalale / Ellisras', or '' if unknown."""
    loc = (location or "").strip()
    if not loc:
        return ""
    for p in PROVINCES:
        if re.search(r"\b" + re.escape(p) + r"\b", loc, re.I):
            return p
    if re.search(r"\bKZN\b|KwaZulu", loc, re.I):
        return "KwaZulu-Natal"
    for rx, prov in _RULES:
        if rx.search(loc):
            return prov
    return ""
