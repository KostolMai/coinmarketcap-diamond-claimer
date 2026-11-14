# 💎 CoinMarketCap Daily Diamonds Auto-Claimer

[![CoinMarketCap Daily Diamonds Auto-Claimer](https://github.com/KostolMai/coinmarketcap-diamond-claimer/actions/workflows/daily-diamonds.yml/badge.svg)](https://github.com/KostolMai/coinmarketcap-diamond-claimer/actions/workflows/daily-diamonds.yml)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

W pełni automatyczny bot do codziennego odbierania diamentów na platformie [CoinMarketCap](https://coinmarketcap.com/account/my-diamonds/) działający w chmurze za pośrednictwem darmowego **GitHub Actions**.

---

## 🌟 Główne funkcje

- 🤖 **100% Automatyzacji**: Działa codziennie bez konieczności trzymania włączonego komputera.
- 🕒 **Polskie okno czasowe (05:25 – 06:45)**: Uruchamia się każdego ranka z losowym, ludzkim opóźnieniem (jitterem), automatycznie radząc sobie ze zmianą czasu letniego (**CEST**) i zimowego (**CET**).
- 🌐 **Ochrona Cloudflare WARP**: Zapewnia czysty, wiarygodny adres IP przy każdym uruchomieniu w GitHub Actions, eliminując blokady datacenter.
- 🎭 **TLS & Browser Impersonation**: Wykorzystuje `curl_cffi` do wiernego odtwarzania sygnatury TLS przeglądarki Chrome 124.
- ⏳ **Wczesne ostrzeganie o wygaśnięciu sesji**: Skrypt automatycznie dekoduje datę ważności tokenu JWT (`exp`) i ostrzega o wygasaniu sesji z wyprzedzeniem 7 oraz 3 dni!
- 📊 **Szczegółowe raporty**:
  - **GitHub Step Summary**: Estetyczna tabela Markdown z przyrostem diamentów, sumą, streakiem i statusem.
  - **Discord**: Bogaty embed z awatarem, kolorystyką statusu i powiadomieniami.
  - **Telegram**: Sformatowane wiadomości HTML na Twój prywatny czat lub grupę.
- 🔒 **Maksymalne bezpieczeństwo**: Twoje dane autoryzacyjne przechowywane są wyłącznie w zaszyfrowanych GitHub Secrets i nigdy nie trafiają do kodu źródłowego.

---

## 📋 Wymagania

Do działania potrzebujesz jedynie:
1. Konta na platformie [CoinMarketCap](https://coinmarketcap.com/).
2. Konta na GitHubie (na którym znajduje się to repozytorium).
3. Opcjonalnie: Webhooka Discord lub Bota Telegram do powiadomień na telefon.

---

## 📝 Jak uruchomić bota (Krok po kroku)

### 🔑 Krok 1: Jak pobrać token autoryzacyjny (`CMC_AUTH_TOKEN`)

CoinMarketCap zabezpiecza swoje API za pomocą tokenu sesyjnego (JWT), przekazywanego w nagłówku `Authorization: Bearer <token>`.

### Instrukcja pobrania w 2 minuty:

1. Otwórz przeglądarkę (np. Chrome, Brave, Edge, Firefox).
2. Wejdź na stronę **[CoinMarketCap My Diamonds](https://coinmarketcap.com/account/my-diamonds/)** i upewnij się, że jesteś zalogowany.
3. Otwórz Narzędzia dla programistów: naciśnij klawisz `F12` (lub prawy przycisk myszy w dowolnym miejscu strony -> **Zbadaj** / **Inspect**).
4. Przejdź do zakładki **Sieć** (**Network**).
5. W polu filtra (Filter / URL filter) wpisz: `check-in` lub `loyalty`.
6. Odśwież stronę (`F5` lub `Ctrl+R`) albo kliknij przycisk odbioru diamentów.
7. Na liście zapytań kliknij jedno z zapytań (np. `check-in`, `user-point-summary` lub `latest-check-in-logs`).
8. W panelu bocznym przejdź do sekcji **Nagłówki** (**Headers**) i zjedź do sekcji **Nagłówki żądania** (**Request Headers**).
9. Znajdź nagłówek **`Authorization`**:
   ```http
   Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOi...
   ```
10. Skopiuj całą wartość (możesz skopiować zarówno sam ciąg zaczynający się od `eyJ...`, jak i z przedrostkiem `Bearer ` — bot automatycznie go rozpozna i oczyści).

> [!TIP]
> **Metoda alternatywna**: W Narzędziach deweloperskich (`F12`) wejdź w zakładkę **Aplikacja** (**Application**) -> po lewej stronie rozwiń **Local Storage** -> kliknij `https://coinmarketcap.com` -> znajdź klucz `u`. W jego zawartości znajduje się pole `"token": "..."`. Skopiuj wartość tego pola.

---

### ⚙️ Krok 2: Konfiguracja GitHub Secrets

Aby bot mógł bezpiecznie pobierać diamenty na Twoim koncie w chmurze GitHub Actions:

1. W swoim repozytorium na GitHubie kliknij zakładkę **Settings** (Ustawienia).
2. W menu po lewej stronie wybierz **Secrets and variables** -> **Actions**.
3. Kliknij zielony przycisk **New repository secret**.
4. Wprowadź sekret autoryzacyjny:
   - **Name**: `CMC_AUTH_TOKEN`
   - **Secret**: Wklej skopiowany w Kroku 1 token (np. `eyJhbGciOi...`).
   - Kliknij **Add secret**.

### Opcjonalne powiadomienia (zalecane):

| Nazwa Sekretu | Opis | Wymagany? |
| :--- | :--- | :--- |
| `CMC_AUTH_TOKEN` | Twój token autoryzacyjny CoinMarketCap | **Tak** |
| `DISCORD_WEBHOOK_URL` | URL webhooka Discord do odbierania powiadomień | Nie |
| `TELEGRAM_BOT_TOKEN` | Token bota Telegram (z @BotFather) | Nie |
| `TELEGRAM_CHAT_ID` | Twój identyfikator czatu Telegram (np. z @userinfobot) | Nie |
| `PROXY_URL` | Własny serwer proxy (np. `http://user:pass@ip:port`) | Nie |

---

### 🚀 Krok 3: Ręczne przetestowanie bota

Nie musisz czekać do rana, aby sprawdzić czy wszystko działa poprawnie!

1. W swoim repozytorium na GitHubie przejdź do zakładki **Actions**.
2. W kolumnie po lewej stronie kliknij **CoinMarketCap Daily Diamonds Auto-Claimer**.
3. Po prawej stronie kliknij przycisk **Run workflow**.
4. Zostaw gałąź `main` i kliknij zielony przycisk **Run workflow**.
5. Po odświeżeniu strony pojawi się uruchomiony proces (żółte kółko -> zielony ptaszek).
6. Kliknij w niego, aby zobaczyć szczegóły wykonania oraz estetyczny raport w sekcji **Summary**!

---

## ⏰ Harmonogram działania

GitHub Actions uruchamia workflow codziennie o:
- **03:25 UTC** w okresie czasu letniego (kwiecień – październik) = **05:25 czasu polskiego (CEST)**.
- **04:25 UTC** w okresie czasu zimowego (listopad – marzec) = **05:25 czasu polskiego (CET)**.

Skrypt wbudowany `src/scheduler.py` weryfikuje bieżącą strefę czasową Polski (`Europe/Warsaw`) i losuje minutę odbioru między **05:25 a 06:45**, imitując naturalne zachowanie człowieka.

*(W przypadku ręcznego uruchomienia przez `workflow_dispatch` oczekiwanie jest automatycznie pomijane).*

---

## 💻 Uruchomienie lokalne (dla programistów)

Jeśli chcesz uruchomić bota lokalnie na swoim komputerze:

1. Sklonuj repozytorium:
   ```bash
   git clone https://github.com/KostolMai/coinmarketcap-diamond-claimer.git
   cd coinmarketcap-diamond-claimer
   ```

2. Utwórz wirtualne środowisko i zainstaluj zależności:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Na Linux/macOS
   # lub: .venv\Scripts\activate na Windows

   pip install -r requirements.txt
   ```

3. Skonfiguruj plik `.env`:
   ```bash
   cp .env.example .env
   # Wpisz swój CMC_AUTH_TOKEN w pliku .env
   ```

4. Uruchom skrypt:
   ```bash
   # Uruchomienie z natychmiastowym odbiorem (bez czekania na okno poranne):
   python main.py --now
   ```

---

## ❓ Często zadawane pytania (FAQ)

### Jak długo ważny jest token `CMC_AUTH_TOKEN`?
Tokeny sesyjne CoinMarketCap zazwyczaj są ważne przez kilkadziesiąt dni. Bot automatycznie odczytuje znacznik `exp` z Twojego tokenu i w każdym powiadomieniu (GitHub, Discord, Telegram) informuje, do kiedy sesja jest aktywna. Gdy pozostanie 7 lub 3 dni, otrzymasz wyraźne ostrzeżenie o konieczności odświeżenia tokenu.

### Co zrobić, gdy sesja wygaśnie?
Wystarczy ponownie wejść na [CoinMarketCap](https://coinmarketcap.com/account/my-diamonds/), pobrać nowy nagłówek `Authorization` zgodnie z instrukcją z Kroku 1 i zaktualizować sekret `CMC_AUTH_TOKEN` w zakładce **Settings -> Secrets and variables -> Actions**.

### Czy moje konto może zostać zablokowane?
Bot stosuje zaawansowaną impersonację protokołu TLS przeglądarki Chrome (`curl_cffi`), działa przez Cloudflare WARP i korzysta z oficjalnego endpointu lojalnościowego CoinMarketCap z losowym czasem żądania. Jest bezpieczny i zachowuje się jak zwykła przeglądarka internetowa.

---

## 📄 Licencja

Projekt udostępniany na licencji [MIT](LICENSE).
