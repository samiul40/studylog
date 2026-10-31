"""Where users are, worked out from the timezone on their profile.

Every IANA zone except generic ones like UTC belongs to a country, and tzdata's
zone.tab says which.
"""

from collections import Counter
from importlib.resources import files

from allauth.account.models import EmailAddress
from django.db.models import Count, Exists, OuterRef

from accounts.models import UserProfile
from learning.services.types import CountryRow


def _read_tab(name):
    text = files("tzdata").joinpath("zoneinfo", name).read_text(encoding="utf-8")
    return [line.split("\t") for line in text.splitlines() if not line.startswith("#")]


# zone.tab columns: country code, coordinates, zone, comment.
ZONE_COUNTRY = {cols[2]: cols[0] for cols in _read_tab("zone.tab")}
COUNTRY_NAME = {cols[0]: cols[1] for cols in _read_tab("iso3166.tab")}

# Browsers still report some zones by names tzdata has since retired, and
# zone.tab only lists the current ones.
ZONE_COUNTRY.update(
    {
        "America/Buenos_Aires": "AR",
        "America/Catamarca": "AR",
        "America/Cordoba": "AR",
        "America/Jujuy": "AR",
        "America/Mendoza": "AR",
        "America/Indianapolis": "US",
        "America/Louisville": "US",
        "Asia/Calcutta": "IN",
        "Asia/Katmandu": "NP",
        "Asia/Rangoon": "MM",
        "Asia/Saigon": "VN",
        "Atlantic/Faeroe": "FO",
        "Europe/Kiev": "UA",
        "Pacific/Ponape": "FM",
        "Pacific/Truk": "FM",
    }
)


def get_user_countries():
    """Active users per country, most first, plus how many couldn't be placed.

    Active means a verified email and no pending deletion. The verified check
    is an Exists rather than a join so two verified addresses count once.
    """
    verified = EmailAddress.objects.filter(user=OuterRef("user"), verified=True)
    profiles = UserProfile.objects.filter(
        Exists(verified), deletion_requested_at__isnull=True
    )

    counts = Counter()
    unknown = 0
    for row in profiles.values("timezone").annotate(users=Count("pk")):
        code = ZONE_COUNTRY.get(row["timezone"])
        if code:
            counts[code] += row["users"]
        else:
            unknown += row["users"]

    rows = [
        CountryRow(code=code, name=COUNTRY_NAME.get(code, code), users=users)
        for code, users in counts.most_common()
    ]
    return rows, unknown
