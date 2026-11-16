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
    def _parse_balance(val: str) -> Optional[int]:
        if not val or str(val).strip() in ("Brak danych", "None", ""):
            return None
        m = re.search(r"\d+", str(val).replace(",", "").replace(" ", ""))
        return int(m.group()) if m else None

    @staticmethod
    def _extract_account_data(res, unit: str, default_name: str, expiry_info: dict) -> dict:
        lbl = getattr(res, "account_label", "")
        if lbl == "Konto 1":
            name = "CoinGecko #1"
            full_name = "CoinGecko (Konto 1)"
        elif lbl == "Konto 2":
            name = "CoinGecko #2"
            full_name = "CoinGecko (Konto 2)"
        elif lbl:
            name = f"CoinGecko ({lbl})"
            full_name = f"CoinGecko ({lbl})"
        else:
            name = default_name
            full_name = default_name

        icon = "🍬" if unit == "🍬" else "💎"

        b_before = Notifier._parse_balance(res.balance_before)
        b_after = Notifier._parse_balance(res.balance_after)
        status_raw = str(res.status or "").strip()
        status_lower = status_raw.lower()

        if b_before is not None and b_after is not None:
            diff = b_after - b_before
        elif res.success and ("odebrano" in status_lower or "sukces" in status_lower):
            diff = 10
        else:
            diff = 0

        if not res.success:
            status_short = "Błąd"
            status_full = f"❌ Błąd ({status_raw})" if status_raw else "❌ Błąd"
        elif "już" in status_lower:
            status_short = "Już odebrano"
            status_full = "ℹ️ Już odebrano dzisiaj"
        elif res.success and ("odebrano" in status_lower or "sukces" in status_lower or diff > 0):
            status_short = "Odebrano"
            status_full = "✅ Sukces (Odebrano)"
        else:
            status_short = status_raw[:12] if status_raw else "Nieznany"
            status_full = f"✅ {status_raw}" if status_raw else "Nieznany"

        gain_short = f"+{diff}" if diff > 0 else "0"
        gain_full = f"+{diff} {unit}" if diff > 0 else f"0 {unit}"

        tot = b_after if b_after is not None else b_before
        total_short = f"{tot} {unit}" if tot is not None else f"? {unit}"
        total_full = f"{tot} {unit}" if tot is not None else "Brak danych"

        warning = None
        if expiry_info.get("warning_level") in ("warning", "critical", "expired"):
            warning = expiry_info.get("warning_message")

        return {
            "name": name,
            "full_name": full_name,
            "icon": icon,
            "unit": unit,
            "status_short": status_short,
            "status_full": status_full,
            "gain_short": gain_short,
            "gain_full": gain_full,
            "total_short": total_short,
            "total_full": total_full,
            "diff": diff,
            "streak": str(res.streak or "1"),
            "expiry_display": expiry_info.get("display", "Brak danych"),
            "warning": warning,
            "error": res.message if not res.success else None,
            "message": res.message,
            "success": res.success,
        }

    @staticmethod
    def _build_unified_table(accounts_data: list[dict]) -> str:
        """
        Buduje czytelną tabelkę w bloku monospace dopasowaną do Discorda i Telegrama.
        Szerokość wiersza to dokładnie 44 znaki (mieści się idealnie bez zawijania na telefonach).
        """
        col1, col2, col3, col4 = "Usługa", "Status", "Zysk", "Suma"
        header = f"{col1:<15}{col2:<13}{col3:>6}{col4:>10}"
        sep = "─" * len(header)
        lines = [header, sep]
        for acc in accounts_data:
            lines.append(f"{acc['name']:<15}{acc['status_short']:<13}{acc['gain_short']:>6}{acc['total_short']:>10}")
        return "\n".join(lines)

    @staticmethod
    def _build_unified_embed(accounts_data: list[dict]) -> dict:
        """
        Buduje JEDNO powiadomienie Embed dla Discorda zawierające tabelkę i podsumowanie.
        """
        table_str = Notifier._build_unified_table(accounts_data)

        desc_lines = [
            f"```text\n{table_str}\n```",
            "**Szczegóły kont:**",
        ]
        for acc in accounts_data:
            desc_lines.append(
                f"• {acc['icon']} **{acc['name']}**: Streak: **{acc['streak']}** 🔥 • Ważność sesji: `{acc['expiry_display']}`"
            )

        warnings = [f"• ⚠️ **{acc['name']}**: {acc['warning']}" for acc in accounts_data if acc.get("warning")]
        if warnings:
            desc_lines.append("\n**⚠️ Ostrzeżenia dotyczące sesji:**")
            desc_lines.extend(warnings)

        errors = [f"• ❌ **{acc['name']}**: {acc['error']}" for acc in accounts_data if acc.get("error")]
        if errors:
            desc_lines.append("\n**❌ Błędy:**")
            desc_lines.extend(errors)

        any_fail = any(not acc["success"] for acc in accounts_data)
        any_warn = any(bool(acc.get("warning")) for acc in accounts_data)
        any_claimed = any(acc["diff"] > 0 for acc in accounts_data)

        if any_fail:
            title = "❌ Codzienny Raport: Błąd odbioru nagród"
            color = 0xE74C3C  # Czerwony
        elif any_warn:
            title = "⚠️ Codzienny Raport: Sesja wkrótce wygasa!"
            color = 0xE67E22  # Pomarańczowy
        elif any_claimed:
            title = "🎁 Codzienny Raport: Odebrano codzienne nagrody!"
            color = 0x2ECC71  # Zielony
        else:
            title = "ℹ️ Codzienny Raport: Nagrody już odebrane dzisiaj"
            color = 0x3498DB  # Niebieski

        return {
            "title": title,
            "description": "\n".join(desc_lines),
            "color": color,
            "footer": {
                "text": "Crypto Daily Rewards Auto-Claimer • CoinGecko & CoinMarketCap",
                "icon_url": "https://s2.coinmarketcap.com/static/cloud/img/coinmarketcap_logo_mobile.png",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def notify_combined(cg_result=None, cmc_result=None, cg_results=None) -> None:
        """
        Wysyła JEDNO połączone powiadomienie (zawierające czytelną tabelkę dla wszystkich kont).
        """
        if cg_results is None:
            cg_results = [cg_result] if cg_result else []

        accounts_data = []
        for cg_res in cg_results:
            lbl = getattr(cg_res, "account_label", "") or "Konto 1"
            exp = Config.get_coingecko_expiry_2() if lbl == "Konto 2" else Config.get_coingecko_expiry()
            accounts_data.append(Notifier._extract_account_data(cg_res, unit="🍬", default_name="CoinGecko", expiry_info=exp))

        if cmc_result:
            cmc_exp = Config.get_expiry_info()
            accounts_data.append(Notifier._extract_account_data(cmc_result, unit="💎", default_name="CoinMarketCap", expiry_info=cmc_exp))

        if not accounts_data:
            return

        # 1. Zapisz do GitHub Actions Step Summary (czytelna tabela Markdown)
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if summary_path:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            md_lines = [
                f"## 🎁 Codzienny Raport Nagród Krypto — {now_str}\n",
                "| Usługa | Status | Zysk | Saldo | Seria (Streak) | Ważność sesji |",
                "| :--- | :--- | :---: | :---: | :---: | :--- |",
            ]
            for acc in accounts_data:
                md_lines.append(
                    f"| {acc['icon']} **{acc['full_name']}** | {acc['status_full']} | `{acc['gain_full']}` | **{acc['total_full']}** | `{acc['streak']}` 🔥 | {acc['expiry_display']} |"
                )

            md_lines.append("\n> *Automatyczne zbieranie nagród przez GitHub Actions.*")

            warnings = [f"- ⚠️ **{acc['full_name']}**: {acc['warning']}" for acc in accounts_data if acc.get("warning")]
            errors = [f"- ❌ **{acc['full_name']}**: {acc['error']}" for acc in accounts_data if acc.get("error")]

            if warnings or errors:
                md_lines.append("\n### ⚠️ Uwagi i błędy")
                md_lines.extend(warnings)
                md_lines.extend(errors)

            try:
                with open(summary_path, "a", encoding="utf-8") as f:
                    f.write("\n".join(md_lines) + "\n\n")
            except Exception as e:
                print(f"[!] Błąd zapisu GITHUB_STEP_SUMMARY: {e}")

        # 2. Wyślij JEDNĄ wiadomość na Discord (dokładnie jeden embed z czytelną tabelką)
        if Config.DISCORD_WEBHOOK_URL:
            embed = Notifier._build_unified_embed(accounts_data)
            payload = {
                "username": "Crypto Daily Rewards",
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
                    print("[+] Jedno wspólne powiadomienie z tabelką wysłane na Discord.")
                else:
                    print(f"[!] Błąd wysyłania na Discord (kod {res.status_code}): {res.text}")
            except Exception as e:
                print(f"[!] Nie udało się wysłać powiadomienia Discord: {e}")

        # 3. Wyślij JEDNĄ wiadomość na Telegram (z tabelką w bloku <pre>)
        if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_CHAT_ID:
            table_str = Notifier._build_unified_table(accounts_data)
            tg_lines = [
                "<b>🎁 Codzienny Raport Nagród Krypto</b>\n",
                f"<pre>{table_str}</pre>\n",
                "<b>Szczegóły kont:</b>",
            ]
            for acc in accounts_data:
                tg_lines.append(
                    f"• {acc['icon']} <b>{acc['name']}</b>: Streak: {acc['streak']} 🔥 • Sesja: {acc['expiry_display']}"
                )

            warnings = [f"• ⚠️ <b>{acc['name']}</b>: {acc['warning']}" for acc in accounts_data if acc.get("warning")]
            if warnings:
                tg_lines.append("\n<b>⚠️ Ostrzeżenia:</b>")
                tg_lines.extend(warnings)

            errors = [f"• ❌ <b>{acc['name']}</b>: {acc['error']}" for acc in accounts_data if acc.get("error")]
            if errors:
                tg_lines.append("\n<b>❌ Błędy:</b>")
                tg_lines.extend(errors)

            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": Config.TELEGRAM_CHAT_ID,
                "text": "\n".join(tg_lines),
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
