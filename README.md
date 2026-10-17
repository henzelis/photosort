# PhotoSort 📷

Кросплатформова програма для сортування фотографій: **Mac · Windows · Linux**.

Читає EXIF (дата зйомки) і геотеги (GPS), визначає назву місця через OpenStreetMap
і раскладає фото по папках. Підтримка JPEG, HEIC/HEIF (iPhone), PNG, TIFF, WebP.

## Встановлення одним рядком

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/henzelis/photosort/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
powershell -c "irm https://raw.githubusercontent.com/henzelis/photosort/main/install.ps1 | iex"
```

Потрібен Python 3.9+ (на Windows — з python.org, з галочкою «Add to PATH»).

## Запуск

```bash
photosort
```
— відкривається **преміум веб-інтерфейс** (локальний сервер + браузер), де можна:
1. обрати вхідну папку (сканується **разом із вкладеними папками**);
2. обрати папку, куди складати відсортовані фото;
3. обрати режим сортування;
4. побачити мапу локацій, хронологію і дерево папок перед запуском;
5. увімкнути переміщення замість копіювання (типово — безпечне копіювання).

Інтерфейс працює однаково на Windows, macOS і Linux — все ставиться автоматично при встановленні.
Сервер слухає лише `127.0.0.1`, фотографії нікуди не надсилаються (тільки назви місць
через Nominatim). `photosort --no-browser` — не відкривати браузер; `--port N` — фіксований порт.

## Режими сортування

| Режим | Структура папок |
|---|---|
| **За датою та місцем** (типово) | `2024/07/Київ/` |
| Тільки за датою | `2024/07/` |
| Тільки за місцем | `Київ/2024/` |

Фото без EXIF-дати потрапляють у `Без дати`, фото без GPS — у `Невідоме місце`.

## Командний рядок

```bash
photosort ~/Pictures ~/Pictures/sorted                    # типовий режим
photosort ~/Pictures ~/Pictures/sorted --mode date        # рік/місяць
photosort ~/Pictures ~/Pictures/sorted --mode location    # місце/рік
photosort ~/Pictures ~/Pictures/sorted --move             # переміщувати, не копіювати
photosort ~/Pictures ~/Pictures/sorted --dry-run          # лише показати план
photosort --help
```

## Як працює геокодинг

Координати перетворюються на назви місць через безкоштовний
[Nominatim (OpenStreetMap)](https://nominatim.openstreetmap.org).
Результати кешуються (`~/.config/photosort/geo_cache.json`), тому повторні запуски
працюють швидко і без мережі. Обмеження Nominatim — 1 запит/секунду,
тож перший розбір великої бібліотеки фото потребує трохи часу.
Режим без мережі: `--no-network` або галочка в GUI.

## Конфлікти імен

Файли з однаковими іменами в різних вхідних папках не перезаписуються —
другий отримує суфікс ` (1)`, ` (2)` і т.д. Назви папок очищуються від
заборонених символів (у тому числі для Windows).

## Розробка

```bash
git clone https://github.com/henzelis/photosort
cd photosort
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
photosort --help
```

## Ліцензія

MIT
