#!/usr/bin/env python3
"""
CoinMarketCap Daily Diamonds Auto-Claimer
Skrypt automatycznie odbiera codzienne diamenty z platformy CoinMarketCap.
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
from src.claimer import CMCClaimer
from src.notifier import Notifier
from src.scheduler import wait_for_execution_window


def main():
    print("=" * 60)
    print("💎 CoinMarketCap Daily Diamonds Auto-Claimer uruchomiony")
    print("=" * 60)

    if not Config.validate():
        error_msg = (
            "BŁĄD: Zmienna środowiskowa CMC_AUTH_TOKEN nie jest ustawiona lub jest pusta!\n"
            "W GitHub Actions: Przejdź do Settings -> Secrets and variables -> Actions i dodaj sekret CMC_AUTH_TOKEN.\n"
            "Lokalnie: Skopiuj .env.example do .env i uzupełnij token."
        )
        print(error_msg, file=sys.stderr)
        Notifier.notify_all(
            status="Brak konfiguracji",
            message=error_msg,
            success=False,
        )
        sys.exit(1)

    # Sprawdź okno czasowe (05:25 - 06:45 czasu polskiego) i ewentualnie odczekaj
    wait_for_execution_window(start_hour=5, start_minute=25, end_hour=6, end_minute=45)

    # Sprawdź ważność sesji
    expiry_info = Config.get_expiry_info()
    if expiry_info.get("has_expiry"):
        print(f"[*] Ważność sesji CoinMarketCap: {expiry_info['display']}")
        if expiry_info.get("warning_level") in ("warning", "critical", "expired"):
            print(f"[!] OSTRZEŻENIE SESJI: {expiry_info['warning_message']}")

    try:
        claimer = CMCClaimer()
        result = claimer.claim()
    except Exception as e:
        print(f"[!] Nieoczekiwany wyjątek: {e}", file=sys.stderr)
        Notifier.notify_all(
            status="Błąd krytyczny",
            message=f"Wystąpił nieoczekiwany wyjątek: {e}",
            success=False,
        )
        sys.exit(1)

    # Wyślij powiadomienia (GitHub Step Summary, opcjonalnie Discord, Telegram)
    Notifier.notify_all(
        status=result.status,
        message=result.message,
        balance_before=result.balance_before,
        balance_after=result.balance_after,
        streak=result.streak,
        success=result.success,
    )

    print("-" * 60)
    print(f"Podsumowanie: {result.status}")
    print(f"Komunikat: {result.message}")
    print(f"Bilans diamentów: {result.balance_after} | Dni z rzędu: {result.streak}")
    print("=" * 60)

    # Jeśli błąd wynikał z wygasłej sesji lub błędu połączenia, zwróć kod błędu 1
    if not result.success:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
