import json
import re
import sys
from typing import Optional, Tuple
from bs4 import BeautifulSoup

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
from src.claimer import ClaimResult


class CoinGeckoClaimer:
    """
    Klient do automatycznego odbioru codziennych cukierków z platformy CoinGecko.
    """
    def __init__(self):
        self.cookies = Config.get_coingecko_cookies()
        if not self.cookies:
            raise ValueError(
                "Brak ciasteczek CoinGecko! Ustaw zmienną środowiskową COINGECKO_COOKIE w GitHub Secrets lub .env."
            )

        if HAS_CURL_CFFI:
            self.session = cffi_requests.Session(impersonate="chrome124")
        else:
            self.session = cffi_requests.Session()

        if Config.PROXY_URL:
            print("[*] CoinGecko: Korzystanie ze skonfigurowanego serwera proxy.")
            self.session.proxies = {
                "http": Config.PROXY_URL,
                "https": Config.PROXY_URL,
            }

        # Załaduj ciasteczka do sesji
        for name, value in self.cookies.items():
            self.session.cookies.set(name, value, domain="coingecko.com")
            self.session.cookies.set(name, value, domain="www.coingecko.com")

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
            "Referer": "https://www.coingecko.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        if Config.RAW_COINGECKO_COOKIE:
            self.headers["Cookie"] = Config.RAW_COINGECKO_COOKIE

    def _fetch_page(self, url: str):
        """Pobiera stronę z obsługą impersonacji i nagłówków."""
        if HAS_CURL_CFFI:
            return self.session.get(url, headers=self.headers, timeout=30, impersonate="chrome124")
        return self.session.get(url, headers=self.headers, timeout=30)

    def _extract_balance(self, soup: BeautifulSoup) -> str:
        """Wyciąga aktualną liczbę cukierków ze strony."""
        balance_elem = soup.find(attrs={"data-candy-target": "balance"})
        if balance_elem and balance_elem.text.strip():
            return balance_elem.text.strip()

        balance_elem = soup.find(attrs={"data-target": "points.balance"})
        if not balance_elem:
            balance_elem = soup.find(attrs={"data-target": "candy.balance"})
        if not balance_elem:
            balance_elem = soup.select_one('[data-target*="balance"]')

        if balance_elem and balance_elem.text.strip():
            return balance_elem.text.strip()

        label = soup.find(string=lambda t: t and "Candy Balance" in t)
        if label and label.parent and label.parent.parent:
            text = label.parent.parent.get_text()
            match = re.search(r"(\d+)", text)
            if match:
                return match.group(1)

        return "Nieznany"

    def _extract_streak(self, soup: BeautifulSoup) -> str:
        """Wyciąga liczbę dni z rzędu (streak)."""
        streak_elem = soup.find(attrs={"data-target": "points.streak"}) or soup.find(
            attrs={"data-target": "candy.streak"}
        )
        if streak_elem and streak_elem.text.strip():
            return streak_elem.text.strip()

        active_day = soup.find(attrs={"data-candy-target": "todayBox"}) or soup.find(
            class_=re.compile(r"tw-border-primary")
        )
        if active_day:
            day_text = active_day.get_text(separator=" ").strip()
            match = re.search(r"(?:Day\s*|Dzień\s*)(\d+)", day_text, re.IGNORECASE)
            if match:
                return f"Dzień {match.group(1)}"

        match = re.search(r"(\d+)\s*(?:day streak|dni z rzędu|Day Streak)", soup.get_text(), re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return "Brak danych"

    def _fetch_csrf_token(self) -> Optional[str]:
        """Pobiera świeży token CSRF z wewnętrznego endpointu API CoinGecko."""
        try:
            res = self.session.get(
                "https://www.coingecko.com/accounts/csrf_meta.json",
                headers=self.headers,
                timeout=15,
                impersonate="chrome124" if HAS_CURL_CFFI else None,
            )
            if res.status_code == 200:
                data = res.json()
                return data.get("token")
        except Exception as e:
            print(f"[!] CoinGecko: Błąd pobierania csrf_meta.json: {e}")
        return None

    def _is_already_collected(self, soup: BeautifulSoup) -> bool:
        """Sprawdza, czy cukierki zostały już dzisiaj odebrane."""
        btn = soup.find("button", id="collectButton")
        if btn:
            if btn.has_attr("disabled") or btn.get("disabled") is not None:
                return True
            return False

        text = soup.get_text().lower()
        if "next candy in" in text or "kolejny cukierek za" in text or "come back tomorrow" in text:
            return True

        return False

    def claim(self) -> ClaimResult:
        """Główna metoda wykonująca proces zbierania cukierków."""
        print(f"[*] Łączenie z CoinGecko ({Config.COINGECKO_CANDY_URL})...")

        try:
            res = self._fetch_page(Config.COINGECKO_CANDY_URL)
        except Exception as e:
            return ClaimResult(
                success=False,
                status="Błąd połączenia",
                message=f"Nie udało się połączyć ze stroną CoinGecko: {e}",
            )

        print(f"[*] CoinGecko odpowiedź HTTP: {res.status_code}")

        # Sprawdzenie blokady Cloudflare
        if res.status_code in (403, 503) and ("cloudflare" in res.text.lower() or "challenge" in res.text.lower()):
            return ClaimResult(
                success=False,
                status="Blokada Cloudflare",
                message="Cloudflare zablokował żądanie IP centrum danych. Wymagany czysty tunel lub proxy.",
            )

        # Sprawdzenie przekierowania do logowania (wygasła sesja)
        if "/users/sign_in" in str(res.url) or "Sign In to CoinGecko" in res.text:
            return ClaimResult(
                success=False,
                status="Sesja wygasła",
                message=(
                    "Ciasteczka CoinGecko straciły ważność. Zaloguj się ponownie na coingecko.com "
                    "i zaktualizuj sekret COINGECKO_COOKIE w GitHub Secrets!"
                ),
            )

        soup = BeautifulSoup(res.text, "html.parser")
        balance_before = self._extract_balance(soup)
        streak = self._extract_streak(soup)

        print(f"[*] CoinGecko bieżący stan: {balance_before} cukierków | Streak: {streak}")

        if self._is_already_collected(soup):
            print("[+] Cukierki CoinGecko zostały już dzisiaj odebrane!")
            return ClaimResult(
                success=True,
                status="Już odebrano",
                message="Cukierki z dnia dzisiejszego zostały już wcześniej odebrane. Do zobaczenia jutro!",
                balance_before=balance_before,
                balance_after=balance_before,
                streak=streak,
            )

        print("[*] Cukierki są gotowe do odebrania! Pobieranie tokenu CSRF...")
        csrf_token = self._fetch_csrf_token()
        if not csrf_token:
            meta_tag = soup.find("meta", {"name": "csrf-token"})
            if meta_tag and meta_tag.get("content"):
                csrf_token = meta_tag["content"]

        if not csrf_token:
            return ClaimResult(
                success=False,
                status="Błąd CSRF",
                message="Nie udało się pobrać tokenu autoryzacji CSRF z CoinGecko.",
                balance_before=balance_before,
                balance_after=balance_before,
                streak=streak,
            )

        check_in_url = "https://www.coingecko.com/en/candy/daily_check_in"
        print(f"[*] Wysyłanie żądania odbioru do: {check_in_url}...")

        claim_headers = {
            "Origin": Config.COINGECKO_BASE_URL,
            "Referer": Config.COINGECKO_CANDY_URL,
            "X-CSRF-Token": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
        }

        try:
            claim_res = self.session.post(
                check_in_url,
                headers={**self.headers, **claim_headers},
                timeout=30,
                impersonate="chrome124" if HAS_CURL_CFFI else None,
            )
        except Exception as e:
            return ClaimResult(
                success=False,
                status="Błąd żądania POST",
                message=f"Błąd podczas wysyłania żądania odbioru cukierków: {e}",
                balance_before=balance_before,
                balance_after=balance_before,
                streak=streak,
            )

        print(f"[*] Odpowiedź odbioru cukierków HTTP: {claim_res.status_code}")

        new_balance = balance_before
        new_streak = streak
        try:
            after_page = self._fetch_page(Config.COINGECKO_CANDY_URL)
            if after_page.status_code == 200:
                after_soup = BeautifulSoup(after_page.text, "html.parser")
                new_balance = self._extract_balance(after_soup)
                new_streak = self._extract_streak(after_soup)
        except Exception:
            pass

        if claim_res.status_code in (200, 204, 302):
            print(f"[+] Sukces! Cukierki odebrane! Nowy bilans: {new_balance}")
            return ClaimResult(
                success=True,
                status="Odebrano cukierki",
                message=f"Pomyślnie odebrano codzienne cukierki CoinGecko! Twój nowy bilans to {new_balance}.",
                balance_before=balance_before,
                balance_after=new_balance,
                streak=new_streak,
            )
        else:
            return ClaimResult(
                success=False,
                status=f"Błąd serwera ({claim_res.status_code})",
                message=f"Serwer CoinGecko zwrócił kod {claim_res.status_code}: {claim_res.text[:200]}",
                balance_before=balance_before,
                balance_after=new_balance,
                streak=new_streak,
            )
