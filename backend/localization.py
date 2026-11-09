import pycountry

# In-memory caches to speed up repeated lookups
_LANGUAGE_CACHE = {}

# Custom overrides for TMDb non-standard / legacy codes
_LANGUAGE_OVERRIDES = {
    "cn": "Cantonese",
    "xx": "No Language",
    "mo": "Moldavian",
    "sh": "Serbo-Croatian",
}


def get_language_name(code: str) -> str:
    """Convert an ISO language code to its full name using pycountry.
    Falls back to raw code if lookup fails.
    """
    if not code:
        return ""

    raw_code = str(code).strip()
    lower_code = raw_code.lower()

    if lower_code in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[lower_code]

    if lower_code in _LANGUAGE_OVERRIDES:
        name = _LANGUAGE_OVERRIDES[lower_code]
        _LANGUAGE_CACHE[lower_code] = name
        return name

    try:
        # 1. Try alpha_2 (e.g. 'en', 'fr')
        lang = pycountry.languages.get(alpha_2=lower_code)
        if lang and hasattr(lang, "name"):
            _LANGUAGE_CACHE[lower_code] = lang.name
            return lang.name

        # 2. Try alpha_3 (e.g. 'eng', 'fra')
        lang3 = pycountry.languages.get(alpha_3=lower_code)
        if lang3 and hasattr(lang3, "name"):
            _LANGUAGE_CACHE[lower_code] = lang3.name
            return lang3.name
    except Exception:
        pass

    # Fallback to raw code
    _LANGUAGE_CACHE[lower_code] = raw_code
    return raw_code
