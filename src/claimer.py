import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests as cffi_requests
    HAS_CURL_CFFI = False

from src.config import Config


@dataclass
class ClaimResult:
    success: bool
    status: str
    message: str
    balance_before: str = "Brak danych"
    balance_after: str = "Brak danych"
    streak: str = "Brak danych"
    account_label: str = ""


class CMCClaimer:
    """
    Klient do automatycznego odbioru codziennych diamentów z platformy CoinMarketCap.
    """
    def __init__(self):
        self.token = Config.get_token()
        if not self.token:
            raise ValueError(
                "Brak tokenu CoinMarketCap! Ustaw zmienną środowiskową CMC_AUTH_TOKEN w GitHub Secrets lub .env."
            )

        if HAS_CURL_CFFI:
            self.session = cffi_requests.Session(impersonate="chrome124")
        else:
            self.session = cffi_requests.Session()

        if Config.PROXY_URL:
            print("[*] Korzystanie z skonfigurowanego serwera proxy.")
            self.session.proxies = {
                "http": Config.PROXY_URL,
                "https": Config.PROXY_URL,
            }

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
            "Content-Type": "application/json",
            "platform": "desktop",
            "Origin": Config.BASE_URL,
            "Referer": Config.MY_DIAMONDS_URL,
            "Authorization": Config.get_auth_header(),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

    def _post(self, url: str, data: dict) -> cffi_requests.Response:
        """Wysyła żądanie POST z obsługą TLS impersonacji Chrome."""
        kwargs = {
            "headers": self.headers,
            "json": data,
            "timeout": 30,
        }
        if HAS_CURL_CFFI:
            kwargs["impersonate"] = "chrome124"
        return self.session.post(url, **kwargs)

    def get_user_point_summary(self) -> Tuple[Optional[dict], Optional[str]]:
        """
        Pobiera stan punktów i diamentów użytkownika z endpointu loyalty/user-point-summary.
        Zwraca (dane, błąd).
        """
        try:
            res = self._post(Config.USER_POINT_SUMMARY_URL, {})
            if res.status_code != 200:
                if res.status_code in (401, 403):
                    return None, "Sesja wygasła (błąd autoryzacji HTTP 401/403)"
                return None, f"HTTP {res.status_code}"

            body = res.json()
            status = body.get("status", {})
            err_code = str(status.get("error_code", ""))
            if err_code in ("100002", "401"):
                return None, "Sesja wygasła (błąd autoryzacji tokenu)"
            if err_code != "0":
                return None, status.get("error_message", f"Błąd API {err_code}")

            return body.get("data", {}), None
        except Exception as e:
            return None, str(e)

    def get_latest_check_in_logs(self) -> Tuple[Optional[list], Optional[str]]:
        """
        Pobiera historię ostatnich dni odbioru z loyalty/latest-check-in-logs.
        Zwraca (lista_dni, błąd).
        """
        try:
            res = self._post(Config.LATEST_LOGS_URL, {})
            if res.status_code != 200:
                if res.status_code in (401, 403):
                    return None, "Sesja wygasła (błąd autoryzacji HTTP 401/403)"
                return None, f"HTTP {res.status_code}"

            body = res.json()
            status = body.get("status", {})
            err_code = str(status.get("error_code", ""))
            if err_code in ("100002", "401"):
                return None, "Sesja wygasła"
            if err_code != "0":
                return None, status.get("error_message", f"Błąd API {err_code}")

            return body.get("data", []), None
        except Exception as e:
            return None, str(e)

    def _calculate_streak(self, logs: list) -> str:
        """
        Oblicza liczbę dni z rzędu (streak) na podstawie logów odbioru.
        """
        if not logs:
            return "Brak danych"

        # Policz aktywne dni
        checked_count = sum(1 for item in logs if item.get("state") in (True, 1))
        if checked_count > 0:
            return f"Dzień {checked_count}"
        return "1"

    def claim(self) -> ClaimResult:
        """
        Główna metoda wykonująca proces weryfikacji i odbioru diamentów.
        """
        print(f"[*] Łączenie z API CoinMarketCap Loyalty ({Config.CHECK_IN_URL})...")

        # 1. Pobierz stan punktów przed odebraniem
        summary, err = self.get_user_point_summary()
        if err:
            if "Sesja wygasła" in err:
                return ClaimResult(
                    success=False,
                    status="Sesja wygasła",
                    message=(
                        "Token autoryzacyjny CoinMarketCap wygasł lub jest nieprawidłowy. "
                        "Zaloguj się na coinmarketcap.com i zaktualizuj sekret CMC_AUTH_TOKEN w GitHub Secrets!"
                    ),
                )
            return ClaimResult(
                success=False,
                status="Błąd połączenia",
                message=f"Nie udało się pobrać salda diamentów: {err}",
            )

        balance_before = str(summary.get("point", "Nieznany"))
        print(f"[*] Bieżący stan diamentów: {balance_before}")

        # 2. Sprawdź czy diamenty zostały już dzisiaj odebrane
        logs, logs_err = self.get_latest_check_in_logs()
        streak = self._calculate_streak(logs) if logs else "Brak danych"

        if logs and isinstance(logs, list) and len(logs) > 0:
            # Ostatni element w tablicy reprezentuje dzisiejszy dzień
            today_log = logs[-1]
            if today_log.get("state") in (True, 1):
                print("[+] Diamenty zostały już dzisiaj odebrane!")
                return ClaimResult(
                    success=True,
                    status="Już odebrano",
                    message="Diamenty z dnia dzisiejszego zostały już wcześniej odebrane. Do zobaczenia jutro!",
                    balance_before=balance_before,
                    balance_after=balance_before,
                    streak=streak,
                )

        print(f"[*] Dni z rzędu (streak): {streak}")
        print("[*] Wysyłanie żądania odbioru diamentów...")

        # 3. Wyślij żądanie check-in
        try:
            claim_res = self._post(Config.CHECK_IN_URL, {"platform": "web"})
        except Exception as e:
            return ClaimResult(
                success=False,
                status="Błąd żądania POST",
                message=f"Błąd podczas wysyłania żądania odbioru diamentów: {e}",
                balance_before=balance_before,
                balance_after=balance_before,
                streak=streak,
            )

        print(f"[*] Otrzymano odpowiedź HTTP: {claim_res.status_code}")

        try:
            body = claim_res.json()
        except Exception:
            return ClaimResult(
                success=False,
                status="Błąd parsowania",
                message=f"Odpowiedź serwera nie jest poprawnym formatem JSON: {claim_res.text[:200]}",
                balance_before=balance_before,
                balance_after=balance_before,
                streak=streak,
            )

        status_info = body.get("status", {})
        error_code = str(status_info.get("error_code", ""))
        error_message = status_info.get("error_message", "")

        # Sprawdzenie błędu wygasłego tokenu
        if error_code in ("100002", "401"):
            return ClaimResult(
                success=False,
                status="Sesja wygasła",
                message="Token CMC wygasł. Zaktualizuj CMC_AUTH_TOKEN w GitHub Secrets!",
                balance_before=balance_before,
                balance_after=balance_before,
                streak=streak,
            )

        # Sprawdzenie czy już odebrano
        if error_code == "10007" or "already" in error_message.lower() or "twice a day" in error_message.lower():
            print("[+] API zgłasza: Diamenty zostały już dzisiaj odebrane.")
            return ClaimResult(
                success=True,
                status="Już odebrano",
                message="Diamenty zostały już dzisiaj odebrane.",
                balance_before=balance_before,
                balance_after=balance_before,
                streak=streak,
            )

        # Sukces (kod "0")
        if error_code == "0":
            # Odczekaj chwilę, aby baza zaktualizowała saldo
            time.sleep(2)
            summary_after, _ = self.get_user_point_summary()
            balance_after = str(summary_after.get("point", balance_before)) if summary_after else balance_before

            logs_after, _ = self.get_latest_check_in_logs()
            streak_after = self._calculate_streak(logs_after) if logs_after else streak

            print(f"[+] Sukces! Diamenty odebrane! Nowe saldo: {balance_after} | Streak: {streak_after}")

            return ClaimResult(
                success=True,
                status="Odebrano diamenty",
                message=f"Pomyślnie odebrano codzienne diamenty CoinMarketCap! Twój nowy bilans to {balance_after}.",
                balance_before=balance_before,
                balance_after=balance_after,
                streak=streak_after,
            )

        # Inny błąd
        return ClaimResult(
            success=False,
            status=f"Błąd API ({error_code})",
            message=f"CoinMarketCap zwrócił błąd: {error_message or 'Nieznany błąd'}",
            balance_before=balance_before,
            balance_after=balance_before,
            streak=streak,
        )
