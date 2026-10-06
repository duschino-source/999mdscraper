# Scraper pentru 999.md

**Limbi:** [English](README.md) · Română · [Русский](README.ru.md)

Un scraper asincron bazat pe Playwright pentru anunțurile de pe 999.md. Salvează anunțurile și istoricul prețurilor în SQLite și exportă rezultatele fiecărei rulări în CSV sau JSON.

## Cerințe

- Python 3.10 sau o versiune mai nouă
- Chromium, instalat o singură dată prin Playwright

## Instalare

Din directorul repository-ului, creați și activați un mediu virtual:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
```

Pentru API-ul HTTP opțional, instalați și dependențele acestuia:

```powershell
python -m pip install -e ".[api]"
```

Pentru instrumentele de testare și împachetare, instalați `python -m pip install -e ".[api,dev]"`.

## Rularea din linia de comandă

```powershell
.\.venv\Scripts\999scraper.exe --url "https://999.md/ro/list/computers-and-office-equipment/video" --output listings.csv
```

Scraper-ul parcurge paginile categoriei, până la 999 de pagini în mod implicit, și se oprește după două pagini consecutive fără anunțuri. Istoricul anunțurilor este salvat în `scraper.db`, iar anunțurile găsite în toate paginile parcurse sunt exportate în `listings.csv`. Folosiți `--output listings.json` pentru formatul JSON, `--pages N` pentru a stabili o limită diferită de pagini, `--db PATH` pentru a schimba baza de date și `--help` pentru lista tuturor opțiunilor. Concurența implicită este de 3 pagini.

Dacă activați mediul virtual cu `.\.venv\Scripts\Activate.ps1`, puteți rula comanda `999scraper` fără calea explicită.

Puteți rula scraper-ul și din directorul sursă, fără instalarea comenzii:

```powershell
python -m scraper999.cli --pages 2 --output listings.csv
```

## Pregătirea unui model local pentru anunțuri

Primul profil este pentru **smartphone-uri** și compară prețul, performanța chipsetului și spațiul de stocare. Modificați smartphone-criteria.json înainte de a înregistra alegeri. Ponderile exprimă importanța fiecărui criteriu; limitele opționale permit stabilirea unui preț maxim sau a spațiului minim.

După colectarea anunțurilor, comparați două anunțuri salvate și înregistrați-l pe cel preferat:

    999scraper-preference record --chosen "https://999.md/ro/12345678" --rejected "https://999.md/ro/87654321" --reason "Chipset mai rapid pentru o diferență mică de preț"

Exportați comparațiile în formatul DPO JSONL:

    999scraper-preference export --output preferences.jsonl

Exportul folosește datele anunțurilor din baza scraper-ului și include profilul criteriilor. Aceasta este etapa de colectare a datelor, nu un model deja antrenat. GTX 1080 Ti are 11 GB VRAM și poate fi un punct de pornire pentru fine-tuning eficient al unui model compact.

Pentru fine-tuning-ul modelului Qwen 0.6B, folosiți Linux sau WSL cu NVIDIA CUDA disponibil. Instalați o versiune PyTorch compatibilă cu CUDA pentru sistemul dvs., apoi instalați dependențele și porniți antrenarea:

    python -m pip install -e ".[training]"
    python scripts/train_ranker.py --data preferences.jsonl

Adapterul LoRA va fi salvat în models/999-ranker. Scriptul nu descarcă și nu antrenează modelul până când nu îl porniți.

După antrenare, ordonați un export JSON folosind același profil:

    python scripts/rank_listings.py --input listings.json --criteria smartphone-criteria.json --adapter models/999-ranker --output ranked-listings.json

Clasificarea compară anunțurile în perechi, deci o categorie mare poate necesita timp.

## Rularea API-ului

```powershell
python -m uvicorn scraper999.api:app --host 127.0.0.1 --port 8000
```

Deschideți `http://127.0.0.1:8000/docs` pentru documentația interactivă. `POST /api/scrape` primește adresa unei categorii 999.md, numărul de pagini și gradul de concurență. Implicit, baza de date este salvată în `data/scraper.db`; setați `SCRAPER_DATA_DIR` înainte de pornire pentru a alege alt director. `GET /api/price-history?url=https://999.md/ro/12345678` returnează modificările de preț înregistrate pentru un anunț. API-ul este destinat utilizării locale; păstrați-l pe localhost dacă nu adăugați autentificare și măsuri de protecție pentru deployment.

## Note

- Instalarea browserului este un pas explicit. Pornirea scraper-ului nu descarcă browserul și nu folosește API-uri private din Playwright.
- Adresele sunt acceptate doar de la `999.md` și `www.999.md`.
- Baza SQLite păstrează datele primei și ultimei apariții și marchează dacă prețul unui anunț a scăzut.
- Istoricul de preț salvează fiecare modificare observată. La actualizarea unei baze de date existente, ultimul preț cunoscut devine primul punct din istoric.
- Paginile sunt verificate în ordine. Scraper-ul tolerează o pagină goală izolată și se oprește după două pagini consecutive fără anunțuri.
- API-ul nu acceptă o cale către baza de date în cereri, astfel încât apelantul nu poate alege arbitrar fișierul în care se scrie.
- Structura paginilor și protecția anti-bot de pe 999.md se pot schimba; selectorii pot necesita actualizări.
