import os
import re
import json
import base64
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def extract_bearer_token(raw_input: str) -> str:
    """
    Wyodrębnia właściwy token Bearer ze zmiennej środowiskowej.
    Obsługuje:
    - Czysty token JWT ('eyJhbGciOi...')
    - Nagłówek Authorization ('Bearer eyJhbGciOi...')
    - Ciasteczka CoinMarketCap (zawierające np. u-prod=...)
    - Obiekt JSON z LocalStorage ('{"token": "..."}')
    - Ścieżkę do pliku z tokenem/ciasteczkami
    """
    if not raw_input or not raw_input.strip():
        return ""

    cleaned = raw_input.strip().strip("'\"")

    # Sprawdzenie czy podano ścieżkę do pliku
    if len(cleaned) < 255:
        try:
            if Path(cleaned).is_file():
                with open(cleaned, "r", encoding="utf-8") as f:
                    cleaned = f.read().strip()
        except Exception:
            pass

    # 1. Format: 'Bearer <token>' lub 'BearereyJ...'
    if cleaned.lower().startswith("bearer "):
        return cleaned[7:].strip()
    if cleaned.lower().startswith("bearereyj"):
        return "eyJ" + cleaned[9:].strip()

    # 2. Format: JSON (np. skopiowane z localStorage 'u' lub odpowiedzi API)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            data = json.loads(cleaned)
            if "token" in data and isinstance(data["token"], str):
                t = data["token"].strip()
                if t.lower().startswith("bearer "):
                    return t[7:].strip()
                if t.lower().startswith("bearereyj"):
                    return "eyJ" + t[9:].strip()
                return t
        except Exception:
            pass

    # 3. Format: Ciąg ciasteczek (zawiera u-prod= lub u=)
    if "u-prod=" in cleaned or "u=" in cleaned:
        for part in cleaned.split(";"):
            part = part.strip()
            if part.startswith("u-prod=") or part.startswith("u="):
                val = part.split("=", 1)[1].strip()
                try:
                    unquoted = urllib.parse.unquote(val)
                    decoded_bytes = base64.b64decode(unquoted)
                    json_str = decoded_bytes.decode("utf-8")
                    data = json.loads(json_str)
                    if "token" in data:
                        return data["token"].replace("Bearer ", "").replace("BearereyJ", "eyJ").strip()
                except Exception:
                    pass

    # 4. Sprawdzenie czy w ciągu jest 'Authorization=Bearer...' lub 'Authorization=BearereyJ...'
    auth_match = re.search(r"Authorization=(?:Bearer\s*|BearereyJ)?([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", cleaned, re.IGNORECASE)
    if auth_match:
        cand = auth_match.group(1).strip()
        if not cand.startswith("eyJ") and "bearereyj" in auth_match.group(0).lower():
            cand = "eyJ" + cand
        return cand

    # 5. Sprawdzenie czy to poprawny token JWT zaczynający się od standardowego prefiksu 'eyJ'
    jwt_eyj_match = re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", cleaned)
    if jwt_eyj_match:
        return jwt_eyj_match.group(0).strip()

    # 6. Ogólne dopasowanie ciągu JWT (trzy części oddzielone kropkami)
    jwt_match = re.search(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", cleaned)
    if jwt_match:
        return jwt_match.group(0).strip()

    # Fallback: zwróć oczyszczony ciąg
    return cleaned


def get_token_expiry_info(token: str) -> dict:
    """
    Parsuje token JWT CoinMarketCap i wyciąga dokładną datę wygaśnięcia sesji (pole 'exp').
    """
    if not token:
        return {
            "has_expiry": False,
            "expiry_date": "Nieznana",
            "days_left": None,
            "warning_level": "unknown",
            "warning_message": "Brak tokenu autoryzacyjnego",
            "display": "Brak danych o ważności",
        }

    try:
        parts = token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            # Uzupełnij dopełnienie base64 (=)
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
            data = json.loads(payload_json)

            exp = data.get("exp")
            if exp:
                exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
                now = datetime.now(timezone.utc)
                days_left = (exp_dt - now).days
                date_fmt = exp_dt.strftime("%Y-%m-%d")

                if days_left <= 0:
                    warning_level = "expired"
                    warning_message = "🚨 Sesja CoinMarketCap wygasła! Zaktualizuj token w GitHub Secrets."
                    display = f"🚨 Wygasła ({date_fmt})"
                elif days_left <= 3:
                    warning_level = "critical"
                    warning_message = (
                        f"⚠️ PILNE: Twój token CMC wygasa za {days_left} dni ({date_fmt})! "
                        "Zaktualizuj CMC_AUTH_TOKEN w GitHub Secrets!"
                    )
                    display = f"🚨 Za {days_left} dni ({date_fmt})"
                elif days_left <= 7:
                    warning_level = "warning"
                    warning_message = (
                        f"⚠️ Uwaga: Twój token CMC wygasa za {days_left} dni ({date_fmt}). "
                        "Zaktualizuj wkrótce token w GitHub Secrets."
                    )
                    display = f"⚠️ Za {days_left} dni ({date_fmt})"
                else:
                    warning_level = "normal"
                    warning_message = f"Sesja ważna do {date_fmt} (pozostało {days_left} dni)"
                    display = f"{date_fmt} (za {days_left} dni) ✅"

                return {
                    "has_expiry": True,
                    "expiry_date": date_fmt,
                    "days_left": days_left,
                    "warning_level": warning_level,
                    "warning_message": warning_message,
                    "display": display,
                }
    except Exception:
        pass

    return {
        "has_expiry": False,
        "expiry_date": "Nieznana",
        "days_left": None,
        "warning_level": "unknown",
        "warning_message": "Nie udało się sparsować daty ważności tokenu",
        "display": "Nieznana",
    }


def parse_coingecko_cookies(cookie_raw: str) -> dict:
    """
    Parsuje ciąg ciasteczek CoinGecko.
    """
    if not cookie_raw or not cookie_raw.strip():
        return {}

    cleaned = cookie_raw.strip().strip("'\"")
    if len(cleaned) < 255:
        try:
            if Path(cleaned).is_file():
                with open(cleaned, "r", encoding="utf-8") as f:
                    cleaned = f.read().strip()
        except Exception:
            pass

    cookies = {}
    parts = cleaned.split(";")
    for part in parts:
        if "=" in part:
            name, val = part.split("=", 1)
            name = name.strip()
            val = val.strip()
            if name:
                cookies[name] = val

    if not cookies and len(cleaned) > 20:
        cookies["_coingecko_session"] = cleaned

    return cookies


def get_coingecko_expiry_info(cookies: dict) -> dict:
    """
    Sprawdza ciasteczko remember_user_token CoinGecko i wyciąga datę ważności sesji.
    W przypadku logowania przez Google/OAuth rozpoznaje aktywną sesję _session_id.
    """
    token = cookies.get("remember_user_token")
    if token:
        try:
            part = token.split("--")[0]
            unquoted = urllib.parse.unquote(part)
            data = json.loads(base64.b64decode(unquoted).decode("utf-8"))
            exp_str = data.get("_rails", {}).get("exp")
            if exp_str:
                exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_left = (exp_dt - now).days
                date_fmt = exp_dt.strftime("%Y-%m-%d")

                if days_left <= 0:
                    warning_level = "expired"
                    warning_message = "🚨 Sesja CoinGecko wygasła! Zaktualizuj ciasteczko w GitHub Secrets."
                    display = f"🚨 Wygasła ({date_fmt})"
                elif days_left <= 3:
                    warning_level = "critical"
                    warning_message = f"⚠️ PILNE: Twoja sesja CoinGecko wygasa za {days_left} dni ({date_fmt})!"
                    display = f"🚨 Za {days_left} dni ({date_fmt})"
                elif days_left <= 7:
                    warning_level = "warning"
                    warning_message = f"⚠️ Uwaga: Twoja sesja CoinGecko wygasa za {days_left} dni ({date_fmt})."
                    display = f"⚠️ Za {days_left} dni ({date_fmt})"
                else:
                    warning_level = "normal"
                    warning_message = f"Sesja CoinGecko ważna do {date_fmt} (pozostało {days_left} dni)"
                    display = f"{date_fmt} (za {days_left} dni) ✅"

                return {
                    "has_expiry": True,
                    "expiry_date": date_fmt,
                    "days_left": days_left,
                    "warning_level": warning_level,
                    "warning_message": warning_message,
                    "display": display,
                }
        except Exception:
            pass

    if cookies.get("_session_id") or cookies.get("_coingecko_session") or len(cookies) > 0:
        return {
            "has_expiry": True,
            "expiry_date": "Aktywna sesja",
            "days_left": None,
            "warning_level": "normal",
            "warning_message": "Sesja ciasteczek CoinGecko jest aktywna.",
            "display": "Sesja aktywna (_session_id) ✅",
        }

    return {
        "has_expiry": False,
        "expiry_date": "Nieznana",
        "days_left": None,
        "warning_level": "unknown",
        "warning_message": "Brak ciasteczek sesyjnych CoinGecko",
        "display": "Brak ciasteczek",
    }


class Config:
    # CoinMarketCap
    RAW_TOKEN: str = (
        os.getenv("CMC_AUTH_TOKEN")
        or os.getenv("CMC_COOKIE")
        or os.getenv("COINMARKETCAP_TOKEN")
        or ""
    ).strip()

    # CoinGecko
    RAW_COINGECKO_COOKIE: str = os.getenv("COINGECKO_COOKIE", "").strip()

    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    PROXY_URL: str = os.getenv("PROXY_URL", "").strip()

    # URL-e API CoinMarketCap
    BASE_URL: str = "https://coinmarketcap.com"
    MY_DIAMONDS_URL: str = "https://coinmarketcap.com/account/my-diamonds/"
    API_BASE_URL: str = "https://api.coinmarketcap.com"
    CHECK_IN_URL: str = "https://api.coinmarketcap.com/asset/v3/loyalty/check-in/"
    USER_POINT_SUMMARY_URL: str = "https://api.coinmarketcap.com/asset/v3/loyalty/user-point-summary"
    LATEST_LOGS_URL: str = "https://api.coinmarketcap.com/asset/v3/loyalty/latest-check-in-logs"

    # URL-e CoinGecko
    COINGECKO_BASE_URL: str = "https://www.coingecko.com"
    COINGECKO_CANDY_URL: str = "https://www.coingecko.com/account/candy?locale=en"
    COINGECKO_CHECK_IN_URL: str = "https://www.coingecko.com/account/candy/daily_check_in"

    @classmethod
    def get_token(cls) -> str:
        return extract_bearer_token(cls.RAW_TOKEN)

    @classmethod
    def get_auth_header(cls) -> str:
        token = cls.get_token()
        if not token:
            return ""
        return f"Bearer {token}"

    @classmethod
    def get_coingecko_cookies(cls) -> dict:
        return parse_coingecko_cookies(cls.RAW_COINGECKO_COOKIE)

    @classmethod
    def has_cmc(cls) -> bool:
        return bool(cls.get_token())

    @classmethod
    def has_coingecko(cls) -> bool:
        cookies = cls.get_coingecko_cookies()
        return bool(cookies.get("_coingecko_session") or len(cookies) > 0)

    @classmethod
    def validate(cls) -> bool:
        return cls.has_cmc() or cls.has_coingecko()

    @classmethod
    def get_expiry_info(cls) -> dict:
        return get_token_expiry_info(cls.get_token())

    @classmethod
    def get_coingecko_expiry(cls) -> dict:
        return get_coingecko_expiry_info(cls.get_coingecko_cookies())

