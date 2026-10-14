import re
import unicodedata


def normalize_person(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def normalize_team(value: str) -> str:
    value = " ".join(unicodedata.normalize("NFKC", value).split())
    compact = value.replace(" ", "")
    aliases = {f"{prefix}{number}班": f"{chinese}班" for number, chinese in (("1", "一"), ("2", "二"), ("3", "三")) for prefix in ("", "第")}
    return aliases.get(compact, value)
