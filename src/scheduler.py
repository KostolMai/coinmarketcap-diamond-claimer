"""
Moduł obsługujący harmonogram i losowe opóźnienie w polskim oknie czasowym (Europe/Warsaw).
Dba o to, aby odbiór diamentów CoinMarketCap następował między 05:25 a 06:45 czasu polskiego,
automatycznie uwzględniając czas letni (CEST) i zimowy (CET).
"""

import os
import sys
import time
import random
import zoneinfo
from datetime import datetime, timedelta


def wait_for_execution_window(
    start_hour: int = 5,
    start_minute: int = 25,
    end_hour: int = 6,
    end_minute: int = 45,
) -> None:
    """
    Sprawdza strefę czasową Polski (Europe/Warsaw) i jeśli skrypt został
    uruchomiony automatycznie przez zaplanowany cron, losuje porę odbioru
    diamentów w zadanym oknie (05:25 - 06:45) i odczekuje do wylosowanej minuty.
    """
    # 1. Ręczne uruchomienie z panelu GitHub Actions (workflow_dispatch) lub flaga pominięcia
    if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
        print("[*] Wykryto ręczne uruchomienie (workflow_dispatch) - natychmiastowe wykonanie bez czekania.")
        return

    if os.getenv("SKIP_DELAY", "").lower() in ("true", "1", "yes"):
        print("[*] Flaga SKIP_DELAY aktywna - natychmiastowe wykonanie bez czekania.")
        return

    if "--now" in sys.argv:
        print("[*] Flaga --now podana - natychmiastowe wykonanie bez czekania.")
        return

    # 2. Pobierz aktualny czas w Polsce (automatycznie uwzględnia CET/CEST)
    try:
        tz = zoneinfo.ZoneInfo("Europe/Warsaw")
        now_pl = datetime.now(tz)
    except Exception as e:
        print(f"[!] Ostrzeżenie: Nie udało się określić strefy Europe/Warsaw ({e}). Kontynuacja bez opóźnienia.")
        return

    tz_label = now_pl.strftime("%Z (UTC%z)")
    print(f"[*] Aktualny czas w Polsce: {now_pl.strftime('%Y-%m-%d %H:%M:%S')} {tz_label}")

    start_window = now_pl.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end_window = now_pl.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)

    # 3. Jeśli uruchomiono przed początkiem okna
    if now_pl < start_window:
        total_window_span = int((end_window - start_window).total_seconds()) - 300
        random_offset = random.randint(0, max(0, total_window_span))
        target_time = start_window + timedelta(seconds=random_offset)
        wait_seconds = (target_time - now_pl).total_seconds()

        mins = int(wait_seconds // 60)
        secs = int(wait_seconds % 60)
        print(
            f"[*] Przed rozpoczęciem okna. Wylosowano godzinę odbioru: {target_time.strftime('%H:%M:%S')} czasu polskiego "
            f"(oczekiwanie: {mins} min {secs} s)..."
        )
        time.sleep(wait_seconds)
        return

    # 4. Jeśli uruchomiono wewnątrz okna
    if start_window <= now_pl < end_window:
        remaining_seconds = int((end_window - now_pl).total_seconds()) - 180  # margines 3 min przed końcem okna
        if remaining_seconds > 60:
            delay = random.randint(30, min(remaining_seconds, 3600))
            target_time = now_pl + timedelta(seconds=delay)
            mins = int(delay // 60)
            secs = int(delay % 60)
            print(
                f"[*] Wewnątrz okna {start_hour:02d}:{start_minute:02d} - {end_hour:02d}:{end_minute:02d}. "
                f"Wylosowano godzinę odbioru: {target_time.strftime('%H:%M:%S')} czasu polskiego "
                f"(opóźnienie: {mins} min {secs} s)..."
            )
            time.sleep(delay)
        else:
            print("[*] Końcówka okna czasowego - natychmiastowe wykonanie.")
        return

    # 5. Jeśli uruchomiono poza oknem porannym (np. test w ciągu dnia)
    print(
        f"[*] Skrypt uruchomiony poza oknem porannym ({now_pl.strftime('%H:%M:%S')} poza "
        f"{start_hour:02d}:{start_minute:02d}-{end_hour:02d}:{end_minute:02d}). Wykonanie natychmiastowe."
    )
