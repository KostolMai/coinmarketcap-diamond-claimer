#!/usr/bin/env python3
"""
Crypto Daily Rewards Auto-Claimer (CoinGecko Candy & CoinMarketCap Diamonds)
Skrypt automatycznie odbiera codzienne nagrody (cukierki i diamenty)
oraz wysyła jedno połączone podsumowanie na Discord, Telegram i GitHub Step Summary.
"""

import sys

# Zapewnij kodowanie UTF-8 dla konsoli (np. na Windows z kodowaniem cp1250)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.config import Config
from src.claimer import CMCClaimer, ClaimResult
from src.notifier import Notifier
from src.scheduler import wait_for_execution_window


def main():
    print("=" * 65)
    print("🎁 Crypto Daily Rewards Auto-Claimer (CoinGecko & CoinMarketCap)")
    print("=" * 65)

    if not Config.validate():
        error_msg = (
            "BŁĄD: Żaden token ani ciasteczko nie zostały skonfigurowane!\n"
            "Wymagany jest co najmniej jeden z sekretów:\n"
            "  - CMC_AUTH_TOKEN (dla CoinMarketCap Diamonds)\n"
            "  - COINGECKO_COOKIE (dla CoinGecko Candies)\n\n"
            "W GitHub Actions: Przejdź do Settings -> Secrets and variables -> Actions i dodaj sekrety.\n"
            "Lokalnie: Skopiuj .env.example do .env i uzupełnij zmienne."
        )
        print(error_msg, file=sys.stderr)
        Notifier.notify_all(
            status="Brak konfiguracji",
            message=error_msg,
            success=False,
        )
        sys.exit(1)

    # Sprawdź okno czasowe (05:25 - 06:45 czasu polskiego) i ewentualnie odczekaj
    # W przypadku wywołania przez cron-job.org (workflow_dispatch) funkcja przechodzi natychmiast
    wait_for_execution_window(start_hour=5, start_minute=25, end_hour=6, end_minute=45)

    # Informacje o ważności sesji
    if Config.has_cmc():
        cmc_expiry = Config.get_expiry_info()
        if cmc_expiry.get("has_expiry"):
            print(f"[*] Ważność sesji CoinMarketCap: {cmc_expiry['display']}")
            if cmc_expiry.get("warning_level") in ("warning", "critical", "expired"):
                print(f"[!] OSTRZEŻENIE SESJI CMC: {cmc_expiry['warning_message']}")

    if Config.has_coingecko():
        cg_expiry = Config.get_coingecko_expiry()
        if cg_expiry.get("has_expiry"):
            print(f"[*] Ważność sesji CoinGecko: {cg_expiry['display']}")
            if cg_expiry.get("warning_level") in ("warning", "critical", "expired"):
                print(f"[!] OSTRZEŻENIE SESJI CoinGecko: {cg_expiry['warning_message']}")

    cg_result = None
    cmc_result = None
    failures = 0

    # 1. Odbiór CoinGecko Candy
    if Config.has_coingecko():
        print("\n" + "-" * 50)
        print("🍬 [1/2] Rozpoczynanie odbioru CoinGecko Candy...")
        print("-" * 50)
        try:
            from src.claimer_coingecko import CoinGeckoClaimer
            cg_claimer = CoinGeckoClaimer()
            cg_result = cg_claimer.claim()
            if not cg_result.success:
                failures += 1
        except Exception as e:
            print(f"[!] Błąd krytyczny podczas odbioru CoinGecko: {e}", file=sys.stderr)
            cg_result = ClaimResult(
                success=False,
                status="Błąd krytyczny",
                message=f"Wystąpił nieoczekiwany wyjątek CoinGecko: {e}",
            )
            failures += 1
    else:
        print("\n[*] COINGECKO_COOKIE nie jest skonfigurowane — pomijanie CoinGecko.")

    # 2. Odbiór CoinMarketCap Diamonds
    if Config.has_cmc():
        print("\n" + "-" * 50)
        print("💎 [2/2] Rozpoczynanie odbioru CoinMarketCap Diamonds...")
        print("-" * 50)
        try:
            cmc_claimer = CMCClaimer()
            cmc_result = cmc_claimer.claim()
            if not cmc_result.success:
                failures += 1
        except Exception as e:
            print(f"[!] Błąd krytyczny podczas odbioru CoinMarketCap: {e}", file=sys.stderr)
            cmc_result = ClaimResult(
                success=False,
                status="Błąd krytyczny",
                message=f"Wystąpił nieoczekiwany wyjątek CoinMarketCap: {e}",
            )
            failures += 1
    else:
        print("\n[*] CMC_AUTH_TOKEN nie jest skonfigurowane — pomijanie CoinMarketCap.")

    # 3. Wyślij JEDNO wspólne powiadomienie (na Discord z obydwoma embedami w jednej wiadomości)
    Notifier.notify_combined(cg_result=cg_result, cmc_result=cmc_result)

    # 4. Podsumowanie w konsoli
    print("\n" + "=" * 65)
    print("📊 PODSUMOWANIE DZISIEJSZEGO ODBIORU:")
    if cg_result:
        print(f"🍬 CoinGecko:      {cg_result.status} | Bilans: {cg_result.balance_after} | Streak: {cg_result.streak}")
    if cmc_result:
        print(f"💎 CoinMarketCap:  {cmc_result.status} | Bilans: {cmc_result.balance_after} | Streak: {cmc_result.streak}")
    print("=" * 65)

    if failures > 0:
        print(f"[!] Zakończono z błędami ({failures} niepowodzenie/a).")
        sys.exit(1)

    print("[+] Wszystkie nagrody odebrane pomyślnie!")
    sys.exit(0)


if __name__ == "__main__":
    main()
