import json
import os
import re
from datetime import datetime, timezone
from typing import Optional
import requests
from src.config import Config


class Notifier:
    @staticmethod
    def _compute_metrics(
        balance_before: str,
        balance_after: str,
        status: str,
        success: bool,
        unit: str = "💎",
    ) -> tuple[str, str, str]:
        """
        Oblicza:
        1. Ile przybyło (np. '+10 💎', '0 💎 (już odebrane dzisiaj)', '0 💎 (błąd)')
        2. Ogólną sumę (np. '150 💎')
        3. Etykietę statusu (np. '✅ Sukces', '❌ Błąd')
        """
        balance_before = str(balance_before or "Brak danych")
        balance_after = str(balance_after or "Brak danych")
        status = str(status or "")
        total = balance_after if balance_after != "Brak danych" else balance_before

        try:
            b_before = int(re.sub(r"[^\d]", "", balance_before)) if re.search(r"\d", balance_before) else None
            b_after = int(re.sub(r"[^\d]", "", balance_after)) if re.search(r"\d", balance_after) else None
        except Exception:
            b_before, b_after = None, None

        if b_before is not None and b_after is not None:
            diff = b_after - b_before
            if diff > 0:
                gained = f"+{diff} {unit}"
            elif "już" in status.lower():
                gained = f"0 {unit} (już odebrane dzisiaj)"
            elif not success:
                gained = f"0 {unit} (błąd)"
            else:
                gained = f"{diff} {unit}"
        else:
            if not success:
                gained = f"0 {unit} (błąd)"
            elif "już" in status.lower():
                gained = f"0 {unit} (już odebrane dzisiaj)"
            elif success and "odebrano" in status.lower():
                gained = f"+10 {unit} (odebrano)"
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

        total_str = f"{total} {unit}" if total != "Brak danych" and unit not in total else total
        return gained, total_str, status_label

    @staticmethod
    def _build_cmc_embed(result) -> dict:
        """Buduje kartę embed dla CoinMarketCap Diamonds."""
        gained, total, status_label = Notifier._compute_metrics(
            result.balance_before, result.balance_after, result.status, result.success, unit="💎"
        )
        expiry_info = Config.get_expiry_info()

        description = result.message
        if expiry_info.get("warning_level") in ("warning", "critical", "expired"):
            description = f"{expiry_info['warning_message']}\n\n{result.message}"

        if not result.success:
            title = "❌ CoinMarketCap: Niepowodzenie odbioru diamentów"
            color = 0xE74C3C  # Czerwony
        elif expiry_info.get("warning_level") == "critical":
            title = "⚠️ CoinMarketCap: Sesja wkrótce wygasa!"
            color = 0xE67E22  # Pomarańczowy
        elif "już" in result.status.lower():
            title = "ℹ️ CoinMarketCap: Diamenty zostały już dzisiaj odebrane"
            color = 0x3498DB  # Niebieski
        else:
            title = "💎 CoinMarketCap: Pomyślnie odebrano codzienne diamenty!"
            color = 0x2ECC71  # Zielony

        return {
            "title": title,
            "description": description,
            "color": color,
            "fields": [
                {"name": "📊 Status", "value": status_label, "inline": False},
                {"name": "➕ Przybyło", "value": f"**{gained}**", "inline": True},
                {"name": "💎 Ogólna suma", "value": f"**{total}**", "inline": True},
                {"name": "🔥 Dni z rzędu (Streak)", "value": f"{result.streak}", "inline": True},
                {"name": "⏳ Ważność sesji", "value": expiry_info["display"], "inline": True},
            ],
            "footer": {
                "text": "CoinMarketCap Diamond Auto-Claimer",
                "icon_url": "https://s2.coinmarketcap.com/static/cloud/img/coinmarketcap_logo_mobile.png",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _build_cg_embed(result) -> dict:
        """Buduje kartę embed dla CoinGecko Candies."""
        account_label = getattr(result, "account_label", "") or "Konto 1"
        gained, total, status_label = Notifier._compute_metrics(
            result.balance_before, result.balance_after, result.status, result.success, unit="🍬"
        )
        if account_label == "Konto 2":
            expiry_info = Config.get_coingecko_expiry_2()
        else:
            expiry_info = Config.get_coingecko_expiry()

        description = result.message
        if expiry_info.get("warning_level") in ("warning", "critical", "expired"):
            description = f"{expiry_info['warning_message']}\n\n{result.message}"

        if not result.success:
            title = f"❌ CoinGecko ({account_label}): Niepowodzenie odbioru cukierków"
            color = 0xE74C3C
        elif expiry_info.get("warning_level") == "critical":
            title = f"⚠️ CoinGecko ({account_label}): Sesja wkrótce wygasa!"
            color = 0xE67E22
        elif "już" in result.status.lower():
            title = f"ℹ️ CoinGecko ({account_label}): Cukierki zostały już dzisiaj odebrane"
            color = 0x3498DB
        else:
            title = f"🍬 CoinGecko ({account_label}): Pomyślnie odebrano codzienne cukierki!"
            color = 0x2ECC71

        return {
            "title": title,
            "description": description,
            "color": color,
            "fields": [
                {"name": "📊 Status", "value": status_label, "inline": False},
                {"name": "➕ Przybyło", "value": f"**{gained}**", "inline": True},
                {"name": "🍬 Ogólna suma", "value": f"**{total}**", "inline": True},
                {"name": "🔥 Dni z rzędu (Streak)", "value": f"{result.streak}", "inline": True},
                {"name": "⏳ Ważność sesji", "value": expiry_info["display"], "inline": True},
            ],
            "footer": {
                "text": f"CoinGecko Candy Auto-Claimer • {account_label}",
                "icon_url": "https://static.coingecko.com/s/thumbnail-00f7877a3903b9ae80112f47f8237b63d1496336a670300b00401322f50f1469.png",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def notify_combined(cg_result=None, cmc_result=None, cg_results=None) -> None:
        """
        Wysyła JEDNO połączone powiadomienie (zawierające CoinGecko dla jednego lub wielu kont i/lub CoinMarketCap).
        """
        if cg_results is None:
            cg_results = [cg_result] if cg_result else []

        # 1. Zapisz do GitHub Actions Step Summary
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if summary_path:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            md_parts = [f"## 🎁 Codzienny Raport Nagród Krypto — {now_str}\n"]

            for cg_res in cg_results:
                lbl = getattr(cg_res, "account_label", "") or "Konto 1"
                cg_gained, cg_total, cg_status = Notifier._compute_metrics(
                    cg_res.balance_before, cg_res.balance_after, cg_res.status, cg_res.success, unit="🍬"
                )
                cg_exp = Config.get_coingecko_expiry_2() if lbl == "Konto 2" else Config.get_coingecko_expiry()
                md_parts.append(f"""
### 🍬 CoinGecko Candy — {lbl} ({cg_status})

| Parametr | Wartość |
| :--- | :--- |
| **Status operacji** | {cg_status} |
| **➕ Przybyło cukierków** | **`{cg_gained}`** |
| **💰 Ogólna suma cukierków** | **`{cg_total}`** |
| **⏳ Ważność sesji** | {cg_exp['display']} |
| **Streak (dni z rzędu)** | `{cg_res.streak}` 🔥 |
| **Szczegóły** | {cg_res.message} |
""")

            if cmc_result:
                cmc_gained, cmc_total, cmc_status = Notifier._compute_metrics(
                    cmc_result.balance_before, cmc_result.balance_after, cmc_result.status, cmc_result.success, unit="💎"
                )
                cmc_exp = Config.get_expiry_info()
                md_parts.append(f"""
### 💎 CoinMarketCap Diamonds ({cmc_status})

| Parametr | Wartość |
| :--- | :--- |
| **Status operacji** | {cmc_status} |
| **➕ Przybyło diamentów** | **`{cmc_gained}`** |
| **💎 Ogólna suma diamentów** | **`{cmc_total}`** |
| **⏳ Ważność sesji** | {cmc_exp['display']} |
| **Streak (dni z rzędu)** | `{cmc_result.streak}` 🔥 |
| **Szczegóły** | {cmc_result.message} |
""")

            md_parts.append("\n---\n*Automatyczne zbieranie nagród przez GitHub Actions.*")
            try:
                with open(summary_path, "a", encoding="utf-8") as f:
                    f.write("\n".join(md_parts))
            except Exception as e:
                print(f"[!] Błąd zapisu GITHUB_STEP_SUMMARY: {e}")

        # 2. Wyślij JEDNĄ wiadomość na Discord (z kartami embed dla każdego konta)
        if Config.DISCORD_WEBHOOK_URL:
            embeds = []
            for cg_res in cg_results:
                embeds.append(Notifier._build_cg_embed(cg_res))
            if cmc_result:
                embeds.append(Notifier._build_cmc_embed(cmc_result))

            if embeds:
                payload = {
                    "username": "Crypto Daily Rewards",
                    "avatar_url": "https://s2.coinmarketcap.com/static/cloud/img/coinmarketcap_logo_mobile.png",
                    "embeds": embeds,
                }
                try:
                    res = requests.post(
                        Config.DISCORD_WEBHOOK_URL,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                    )
                    if res.status_code in (200, 204):
                        print("[+] Wspólne powiadomienie Discord wysłane pomyślnie.")
                    else:
                        print(f"[!] Błąd wysyłania na Discord (kod {res.status_code}): {res.text}")
                except Exception as e:
                    print(f"[!] Nie udało się wysłać powiadomienia Discord: {e}")

        # 3. Wyślij JEDNĄ wiadomość na Telegram
        if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_CHAT_ID:
            sections = ["<b>🎁 Codzienny Raport Nagród Krypto</b>\n"]
            for cg_res in cg_results:
                lbl = getattr(cg_res, "account_label", "") or "Konto 1"
                cg_gained, cg_total, cg_status = Notifier._compute_metrics(
                    cg_res.balance_before, cg_res.balance_after, cg_res.status, cg_res.success, unit="🍬"
                )
                cg_exp = Config.get_coingecko_expiry_2() if lbl == "Konto 2" else Config.get_coingecko_expiry()
                sections.append(
                    f"<b>🍬 CoinGecko ({lbl}):</b>\n"
                    f"• Status: {cg_status}\n"
                    f"• Przybyło: <b>{cg_gained}</b>\n"
                    f"• Suma: <b>{cg_total}</b>\n"
                    f"• Streak: {cg_res.streak}\n"
                    f"• Ważność sesji: {cg_exp['display']}\n"
                )
            if cmc_result:
                cmc_gained, cmc_total, cmc_status = Notifier._compute_metrics(
                    cmc_result.balance_before, cmc_result.balance_after, cmc_result.status, cmc_result.success, unit="💎"
                )
                cmc_exp = Config.get_expiry_info()
                sections.append(
                    f"<b>💎 CoinMarketCap:</b>\n"
                    f"• Status: {cmc_status}\n"
                    f"• Przybyło: <b>{cmc_gained}</b>\n"
                    f"• Suma: <b>{cmc_total}</b>\n"
                    f"• Streak: {cmc_result.streak}\n"
                    f"• Ważność sesji: {cmc_exp['display']}\n"
                )

            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": Config.TELEGRAM_CHAT_ID,
                "text": "\n".join(sections),
                "parse_mode": "HTML",
            }
            try:
                res = requests.post(url, json=payload, timeout=10)
                if res.status_code == 200:
                    print("[+] Powiadomienie Telegram wysłane pomyślnie.")
                else:
                    print(f"[!] Błąd wysyłania na Telegram: {res.text}")
            except Exception as e:
                print(f"[!] Nie udało się wysłać powiadomienia Telegram: {e}")

    @staticmethod
    def notify_all(
        status: str,
        message: str,
        balance_before: str = "Brak danych",
        balance_after: str = "Brak danych",
        streak: str = "Brak danych",
        success: bool = True,
    ) -> None:
        """Fallback do pojedynczych powiadomień lub błędów konfiguracyjnych."""
        from src.claimer import ClaimResult
        dummy = ClaimResult(
            success=success,
            status=status,
            message=message,
            balance_before=balance_before,
            balance_after=balance_after,
            streak=streak,
        )
        Notifier.notify_combined(cmc_result=dummy)
