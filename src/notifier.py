import json
import os
import re
from datetime import datetime, timezone
import requests
from src.config import Config


class Notifier:
    @staticmethod
    def notify_all(
        status: str,
        message: str,
        balance_before: str = "Brak danych",
        balance_after: str = "Brak danych",
        streak: str = "Brak danych",
        success: bool = True,
    ) -> None:
        """Wysyła powiadomienia do wszystkich skonfigurowanych kanałów."""
        Notifier.write_github_step_summary(
            status=status,
            message=message,
            balance_before=balance_before,
            balance_after=balance_after,
            streak=streak,
            success=success,
        )

        if Config.DISCORD_WEBHOOK_URL:
            Notifier.send_discord_notification(
                status=status,
                message=message,
                balance_before=balance_before,
                balance_after=balance_after,
                streak=streak,
                success=success,
            )

        if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_CHAT_ID:
            Notifier.send_telegram_notification(
                status=status,
                message=message,
                balance_before=balance_before,
                balance_after=balance_after,
                streak=streak,
                success=success,
            )

    @staticmethod
    def _compute_metrics(
        balance_before: str,
        balance_after: str,
        status: str,
        success: bool,
    ) -> tuple[str, str, str]:
        """
        Oblicza:
        1. Ile diamentów przybyło (np. '+10 💎', '0 💎 (już odebrane dzisiaj)', '0 💎 (błąd)')
        2. Ogólną sumę diamentów (np. '150 💎')
        3. Etykietę statusu (np. '✅ Sukces', '❌ Błąd')
        """
        total = balance_after if balance_after != "Brak danych" else balance_before

        try:
            b_before = int(re.sub(r"[^\d]", "", balance_before)) if re.search(r"\d", balance_before) else None
            b_after = int(re.sub(r"[^\d]", "", balance_after)) if re.search(r"\d", balance_after) else None
        except Exception:
            b_before, b_after = None, None

        if b_before is not None and b_after is not None:
            diff = b_after - b_before
            if diff > 0:
                gained = f"+{diff} 💎"
            elif "już" in status.lower():
                gained = "0 💎 (już odebrane dzisiaj)"
            elif not success:
                gained = "0 💎 (błąd)"
            else:
                gained = f"{diff} 💎"
        else:
            if not success:
                gained = "0 💎 (błąd)"
            elif "już" in status.lower():
                gained = "0 💎 (już odebrane dzisiaj)"
            elif success and "odebrano" in status.lower():
                gained = "+10-50 💎 (odebrano)"
            else:
                gained = "Brak danych"

        if "już" in status.lower():
            status_label = "ℹ️ Już odebrano dzisiaj"
        elif success and ("odebrano" in status.lower() or "sukces" in status.lower()):
            status_label = "✅ Sukces (Odebrano)"
        elif success:
            status_label = f"✅ {status}"
        else:
            status_label = f"❌ Niepowodzenie ({status})"

        total_str = f"{total} 💎" if total != "Brak danych" and "💎" not in total else total
        return gained, total_str, status_label

    @staticmethod
    def write_github_step_summary(
        status: str,
        message: str,
        balance_before: str,
        balance_after: str,
        streak: str,
        success: bool,
    ) -> None:
        """Zapisuje podsumowanie do GitHub Actions Step Summary."""
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if not summary_path:
            return

        gained, total, status_label = Notifier._compute_metrics(
            balance_before, balance_after, status, success
        )
        expiry_info = Config.get_expiry_info()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        markdown = f"""
### {status_label} — CoinMarketCap Diamonds Raport

| Parametr | Wartość |
| :--- | :--- |
| **Status operacji** | {status_label} |
| **➕ Przybyło diamentów** | **`{gained}`** |
| **💎 Ogólna suma diamentów** | **`{total}`** |
| **⏳ Ważność sesji** | {expiry_info['display']} |
| **Poprzedni stan konta** | `{balance_before}` 💎 |
| **Streak (dni z rzędu)** | `{streak}` 🔥 |
| **Szczegóły** | {message} |
| **Data wykonania** | {now_str} |

---
*Automatyczne zbieranie diamentów CoinMarketCap przez GitHub Actions.*
"""
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(markdown)
        except Exception as e:
            print(f"[!] Błąd zapisu GITHUB_STEP_SUMMARY: {e}")

    @staticmethod
    def send_discord_notification(
        status: str,
        message: str,
        balance_before: str,
        balance_after: str,
        streak: str,
        success: bool,
    ) -> None:
        """Wysyła szczegółowy i estetyczny raport embed na Discord."""
        gained, total, status_label = Notifier._compute_metrics(
            balance_before, balance_after, status, success
        )
        expiry_info = Config.get_expiry_info()

        # Dodaj widoczne ostrzeżenie w opisie, jeśli sesja zbliża się do końca (<= 7 dni)
        description = message
        if expiry_info.get("warning_level") in ("warning", "critical", "expired"):
            description = f"{expiry_info['warning_message']}\n\n{message}"

        if not success:
            title = "❌ CoinMarketCap: Niepowodzenie odbioru diamentów"
            color = 0xE74C3C  # Czerwony
        elif expiry_info.get("warning_level") == "critical":
            title = "⚠️ CoinMarketCap: Sesja wkrótce wygasa!"
            color = 0xE67E22  # Pomarańczowy
        elif "już" in status.lower():
            title = "ℹ️ CoinMarketCap: Diamenty zostały już dzisiaj odebrane"
            color = 0x3498DB  # Niebieski
        else:
            title = "💎 CoinMarketCap: Pomyślnie odebrano codzienne diamenty!"
            color = 0x2ECC71  # Zielony

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": [
                {"name": "📊 Status", "value": status_label, "inline": False},
                {"name": "➕ Przybyło", "value": f"**{gained}**", "inline": True},
                {"name": "💎 Ogólna suma", "value": f"**{total}**", "inline": True},
                {"name": "🔥 Dni z rzędu (Streak)", "value": f"{streak}", "inline": True},
                {"name": "⏳ Ważność sesji", "value": expiry_info["display"], "inline": True},
            ],
            "footer": {
                "text": "CoinMarketCap Diamond Auto-Claimer • GitHub Actions",
                "icon_url": "https://s2.coinmarketcap.com/static/cloud/img/coinmarketcap_logo_mobile.png",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        payload = {
            "username": "CoinMarketCap Diamond Bot",
            "avatar_url": "https://s2.coinmarketcap.com/static/cloud/img/coinmarketcap_logo_mobile.png",
            "embeds": [embed],
        }

        try:
            res = requests.post(
                Config.DISCORD_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if res.status_code in (200, 204):
                print("[+] Powiadomienie Discord wysłane pomyślnie.")
            else:
                print(f"[!] Błąd wysyłania na Discord (kod {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[!] Nie udało się wysłać powiadomienia Discord: {e}")

    @staticmethod
    def send_telegram_notification(
        status: str,
        message: str,
        balance_before: str,
        balance_after: str,
        streak: str,
        success: bool,
    ) -> None:
        """Wysyła wiadomość na Telegram."""
        gained, total, status_label = Notifier._compute_metrics(
            balance_before, balance_after, status, success
        )
        expiry_info = Config.get_expiry_info()

        warning_line = ""
        if expiry_info.get("warning_level") in ("warning", "critical", "expired"):
            warning_line = f"\n<b>Ostrzeżenie:</b> {expiry_info['warning_message']}\n"

        text = (
            f"<b>💎 CoinMarketCap Diamond Raport</b>\n\n"
            f"<b>Status:</b> {status_label}\n"
            f"<b>➕ Przybyło:</b> <b>{gained}</b>\n"
            f"<b>💎 Ogólna suma:</b> <b>{total}</b>\n"
            f"<b>🔥 Dni z rzędu:</b> {streak}\n"
            f"<b>⏳ Ważność sesji:</b> {expiry_info['display']}\n"
            f"{warning_line}"
            f"<b>📝 Komunikat:</b> {message}\n"
        )

        url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": Config.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                print("[+] Powiadomienie Telegram wysłane pomyślnie.")
            else:
                print(f"[!] Błąd wysyłania na Telegram (kod {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[!] Nie udało się wysłać powiadomienia Telegram: {e}")
