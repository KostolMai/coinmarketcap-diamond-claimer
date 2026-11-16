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
            print(f"[*] Ważność sesji CoinGecko (Konto 1): {cg_expiry['display']}")
            if cg_expiry.get("warning_level") in ("warning", "critical", "expired"):
                print(f"[!] OSTRZEŻENIE SESJI CoinGecko (Konto 1): {cg_expiry['warning_message']}")

    if Config.has_coingecko_2():
        cg2_expiry = Config.get_coingecko_expiry_2()
        if cg2_expiry.get("has_expiry"):
            print(f"[*] Ważność sesji CoinGecko (Konto 2): {cg2_expiry['display']}")
            if cg2_expiry.get("warning_level") in ("warning", "critical", "expired"):
                print(f"[!] OSTRZEŻENIE SESJI CoinGecko (Konto 2): {cg2_expiry['warning_message']}")

    cg_results = []
    cmc_result = None
    failures = 0

    # 1. Odbiór CoinGecko Candy — Konto 1
    if Config.has_coingecko():
        print("\n" + "-" * 50)
        print("🍬 [1/3] Rozpoczynanie odbioru CoinGecko Candy (Konto 1)...")
        print("-" * 50)
        try:
            from src.claimer_coingecko import CoinGeckoClaimer
            cg_claimer = CoinGeckoClaimer(
                cookies=Config.get_coingecko_cookies(),
                account_label="Konto 1",
                impersonate_profile="chrome124",
            )
            res1 = cg_claimer.claim()
            cg_results.append(res1)
            if not res1.success:
                failures += 1
        except Exception as e:
            print(f"[!] Błąd krytyczny podczas odbioru CoinGecko (Konto 1): {e}", file=sys.stderr)
            cg_results.append(ClaimResult(
                success=False,
                status="Błąd krytyczny",
                message=f"Wystąpił nieoczekiwany wyjątek CoinGecko (Konto 1): {e}",
                account_label="Konto 1",
            ))
            failures += 1
    else:
        print("\n[*] COINGECKO_COOKIE nie jest skonfigurowane — pomijanie Konta 1 CoinGecko.")

    # 2. Odbiór CoinGecko Candy — Konto 2 (zabezpieczenia Anti-Ban)
    if Config.has_coingecko_2():
        import time
        import random
        import subprocess

        # Losowy odstęp (jitter) 75 - 130 sekund, aby zapytania nie leciały jednocześnie
        delay = random.randint(75, 130)
        print("\n" + "-" * 50)
        print(f"⏳ [Anti-Ban] Odczekiwanie {delay} sekund przed obsługą Konta 2 (symulacja człowieka)...")
        print("-" * 50)
        time.sleep(delay)

        # Odświeżenie połączenia Cloudflare WARP, aby przydzielić inny adres IP
        try:
            subprocess.run(["warp-cli", "disconnect"], capture_output=True, timeout=5)
            time.sleep(2)
            subprocess.run(["warp-cli", "connect"], capture_output=True, timeout=5)
            time.sleep(2)
            print("[*] [Anti-Ban] Zresetowano połączenie Cloudflare WARP (nowa tożsamość sieciowa).")
        except Exception:
            pass

        print("\n" + "-" * 50)
        print("🍬 [2/3] Rozpoczynanie odbioru CoinGecko Candy (Konto 2)...")
        print("-" * 50)
        try:
            from src.claimer_coingecko import CoinGeckoClaimer
            # Użyj innego fingerprintu TLS/przeglądarki dla drugiego konta
            cg2_claimer = CoinGeckoClaimer(
                cookies=Config.get_coingecko_cookies_2(),
                account_label="Konto 2",
                impersonate_profile="edge101",
            )
            res2 = cg2_claimer.claim()
            cg_results.append(res2)
            if not res2.success:
                failures += 1
        except Exception as e:
            print(f"[!] Błąd krytyczny podczas odbioru CoinGecko (Konto 2): {e}", file=sys.stderr)
            cg_results.append(ClaimResult(
                success=False,
                status="Błąd krytyczny",
                message=f"Wystąpił nieoczekiwany wyjątek CoinGecko (Konto 2): {e}",
                account_label="Konto 2",
            ))
            failures += 1
    else:
        print("\n[*] COINGECKO_COOKIE_2 nie jest skonfigurowane — pomijanie Konta 2 CoinGecko.")

    # 3. Odbiór CoinMarketCap Diamonds
    if Config.has_cmc():
        print("\n" + "-" * 50)
        print("💎 [3/3] Rozpoczynanie odbioru CoinMarketCap Diamonds...")
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

    # 4. Wyślij JEDNO wspólne powiadomienie (na Discord ze wszystkimi embedami w jednej wiadomości)
    Notifier.notify_combined(cg_results=cg_results, cmc_result=cmc_result)

    # 5. Podsumowanie w konsoli
    print("\n" + "=" * 65)
    print("📊 PODSUMOWANIE DZISIEJSZEGO ODBIORU:")
    for cg_res in cg_results:
        lbl = getattr(cg_res, "account_label", "") or "Konto 1"
        print(f"🍬 CoinGecko ({lbl}): {cg_res.status} | Bilans: {cg_res.balance_after} | Streak: {cg_res.streak}")
    if cmc_result:
        print(f"💎 CoinMarketCap:           {cmc_result.status} | Bilans: {cmc_result.balance_after} | Streak: {cmc_result.streak}")
    print("=" * 65)

    if failures > 0:
        print(f"[!] Zakończono z błędami ({failures} niepowodzenie/a).")
        sys.exit(1)

    print("[+] Wszystkie nagrody odebrane pomyślnie!")
    sys.exit(0)


if __name__ == "__main__":
    main()
