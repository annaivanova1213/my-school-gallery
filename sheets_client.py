# -*- coding: utf-8 -*-
"""Google Sheets + Google Drive (OAuth для личного Gmail) + HTML-галерея."""
import os
import re
import pickle
import gspread
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import (OAUTH_CREDS_FILE, OAUTH_TOKEN_FILE,
                    SHEET_ID, LIST_STUDENTS, LIST_ACHIEVEMENTS,
                    LIST_TEACHERS, DRIVE_FOLDER_ID)

import html as _html
from datetime import datetime as _dt

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _normalize_word(w: str) -> str:
    if not w:
        return ""
    w = w.strip().lower().replace("ё", "е")
    suffixes = (
        "ого", "его", "ому", "ему", "ыми", "ими",
        "ой", "ый", "ий", "ая", "яя", "ое", "ее",
        "ую", "юю", "ых", "их", "ым", "им",
        "ов", "ев", "ин", "ын",
        "а", "я", "у", "ю", "е", "о", "ы", "и", "й", "ь",
    )
    for suf in suffixes:
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _cyrillize(s: str) -> str:
    lat_map = {
        'a': 'а', 'e': 'е', 'o': 'о', 'p': 'р', 'c': 'с', 'x': 'х',
        'y': 'у', 't': 'т', 'u': 'и', 'w': 'ш', 'k': 'к', 'h': 'н',
        'b': 'в', 'm': 'т', 'n': 'п', 'r': 'г', 'q': 'я',
        'g': 'г', 'd': 'д', 'f': 'ф', 'l': 'л', 'i': 'и', 'j': 'й',
        's': 'с', 'v': 'в', 'z': 'з',
        'A': 'А', 'E': 'Е', 'O': 'О', 'P': 'Р', 'C': 'С', 'X': 'Х',
        'Y': 'У', 'T': 'Т', 'U': 'И', 'W': 'Ш', 'K': 'К', 'H': 'Н',
        'B': 'В', 'M': 'Т', 'N': 'П', 'R': 'Г', 'G': 'Г', 'D': 'Д',
        'F': 'Ф', 'L': 'Л', 'I': 'И', 'J': 'Й', 'S': 'С', 'V': 'В',
        'Z': 'З',
        '3': 'з', '0': 'о', '1': 'л', '4': 'ч',
    }
    return "".join(lat_map.get(ch, ch) for ch in s)


def get_credentials():
    creds = None
    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              OAUTH_TOKEN_FILE)
    if os.path.exists(token_path):
        try:
            with open(token_path, "rb") as f:
                creds = pickle.load(f)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                OAUTH_CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
        with open(token_path, "wb") as f:
            pickle.dump(creds, f)
    return creds


class SheetsClient:
    def __init__(self):
        self.creds = get_credentials()
        self.gc = gspread.authorize(self.creds)
        self.sh = self.gc.open_by_key(SHEET_ID)
        self.ws_students = self.sh.worksheet(LIST_STUDENTS)
        self.ws_ach = self.sh.worksheet(LIST_ACHIEVEMENTS)

        self._students_cache = None
        self._teachers_cache = None
        self._drive_service = None
        self._drive_url_cache = {}
        self._drive_files_loaded = False

    # ─────── Google Drive ───────
    def _drive(self):
        if self._drive_service is None:
            self._drive_service = build("drive", "v3", credentials=self.creds)
        return self._drive_service

    def _load_drive_files(self):
        if self._drive_files_loaded:
            return
        if not DRIVE_FOLDER_ID:
            self._drive_files_loaded = True
            return
        try:
            service = self._drive()
            results = service.files().list(
                q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
                fields="files(id, name, webViewLink)",
                pageSize=1000,
            ).execute()
            for f in results.get("files", []):
                self._drive_url_cache[f["name"]] = f["webViewLink"]
        except Exception as e:
            print(f"Не удалось загрузить список файлов Drive: {e}")
        self._drive_files_loaded = True

    def upload_to_drive(self, local_path: str) -> str:
        if not DRIVE_FOLDER_ID:
            print("DRIVE_FOLDER_ID пустой — загрузка невозможна.")
            return ""
        fname = os.path.basename(local_path)
        self._load_drive_files()
        if fname in self._drive_url_cache:
            return self._drive_url_cache[fname]
        try:
            service = self._drive()
            metadata = {"name": fname, "parents": [DRIVE_FOLDER_ID]}
            media = MediaFileUpload(local_path, resumable=False)
            created = service.files().create(
                body=metadata, media_body=media,
                fields="id, webViewLink",
            ).execute()
            file_id = created.get("id")
            url = created.get("webViewLink", "")

            try:
                service.permissions().create(
                    fileId=file_id,
                    body={"role": "reader", "type": "anyone"},
                ).execute()
            except Exception as e:
                print(f"Не удалось открыть доступ к {fname}: {e}")

            self._drive_url_cache[fname] = url
            return url
        except Exception as e:
            print(f"Ошибка загрузки в Drive ({fname}): {e}")
            return ""

    # ─────── Ученики ───────
    def _load_students(self):
        if self._students_cache is None:
            rows = self.ws_students.get_all_values()
            self._students_cache = []
            for i, row in enumerate(rows[1:], start=2):
                if len(row) < 4 or not row[0].strip():
                    continue
                self._students_cache.append({
                    "row": i,
                    "surname": row[0].strip(),
                    "name": row[1].strip(),
                    "patronym": row[2].strip() if len(row) > 2 else "",
                    "klass": row[3],
                    "surname_norm": _normalize_word(row[0]),
                    "name_low": row[1].strip().lower(),
                })
        return self._students_cache

    def find_student(self, fio: str):
        if not fio:
            return None

        parts = [p for p in re.split(r"[\s,.\-]+", fio.strip()) if p]
        if not parts:
            return None

        surname_ocr = parts[0]
        name_ocr = parts[1] if len(parts) > 1 else ""

        surname_stem = _normalize_word(surname_ocr)
        name_low = name_ocr.lower()

        students = self._load_students()
        candidates = [s for s in students if s["surname_norm"] == surname_stem]

        if not candidates:
            best, best_dist = None, 999
            for s in students:
                d = _levenshtein(s["surname_norm"], surname_stem)
                if d <= 2 and d < best_dist:
                    best_dist, best = d, s
            if best:
                return self._res_student(best, f"нечёткая фамилия (dist={best_dist})")
            return None

        def is_name_soft_match(name_table, name_ocr_val):
            if not name_ocr_val:
                return True
            n1 = name_table.lower()
            n2 = name_ocr_val.lower()
            if n1 == n2:
                return True
            if n1[:2] == n2[:2]:
                return True
            if _levenshtein(n1[:3], n2[:3]) <= 1:
                return True
            return False

        if len(candidates) == 1:
            return self._res_student(candidates[0], "единственный с такой фамилией")

        if name_low:
            for s in candidates:
                if is_name_soft_match(s["name_low"], name_low):
                    return self._res_student(s, "мягкое совпадение имени")
            return self._res_student(candidates[0], "совпала фамилия (имя не совпало)")

        return self._res_student(candidates[0], "только фамилия")

    @staticmethod
    def _res_student(s, source):
        return {
            "row": s["row"],
            "fio": f"{s['surname']} {s['name']} {s['patronym']}".strip(),
            "klass": s["klass"],
            "source": source,
        }

    def all_students(self):
        return [
            {"fio": f"{s['surname']} {s['name']} {s['patronym']}".strip(),
             "klass": s["klass"]}
            for s in self._load_students()
        ]

    # ─────── Учителя ───────
    def all_teachers(self, use_cache: bool = True):
        if use_cache and self._teachers_cache is not None:
            return self._teachers_cache
        try:
            ws = self.sh.worksheet(LIST_TEACHERS)
        except Exception as e:
            print(f"Лист «{LIST_TEACHERS}» не найден: {e}")
            self._teachers_cache = []
            return []
        rows = ws.get_all_values()
        result = []
        for r in rows[1:]:
            if r and r[0].strip():
                result.append(r[0].strip())
        self._teachers_cache = result
        return result

    def find_teacher(self, ocr_teacher: str, teachers_list=None) -> str:
        if not ocr_teacher:
            return ""
        if teachers_list is None:
            teachers_list = self.all_teachers()
        if not teachers_list:
            return ocr_teacher

        norm = self._normalize_teacher_string(ocr_teacher)
        if not norm:
            return ocr_teacher
        surname_ocr, initials_ocr = norm
        if not surname_ocr:
            return ocr_teacher

        for t in teachers_list:
            s, i = self._normalize_teacher_string(t)
            if s == surname_ocr and i == initials_ocr:
                return t

        for t in teachers_list:
            s, i = self._normalize_teacher_string(t)
            if s == surname_ocr:
                return t

        best, best_d = None, 999
        for t in teachers_list:
            s, i = self._normalize_teacher_string(t)
            if not s:
                continue
            if s[0] != surname_ocr[0]:
                continue
            d = _levenshtein(s, surname_ocr)
            if initials_ocr and i and initials_ocr == i:
                d -= 1
            if d < best_d:
                best_d = d
                best = t
        if best and best_d <= 4:
            return best

        return ocr_teacher

    @staticmethod
    def _normalize_teacher_string(s: str):
        if not s:
            return "", ""
        s = _cyrillize(s.strip())

        parts = [p for p in re.split(r"\s+", s) if p]
        if not parts:
            return "", ""

        surname = None
        initials = []

        for p in parts:
            p_clean = p.strip(".,;:")
            if re.fullmatch(r"[А-ЯЁ]\.?", p_clean) or \
                    re.fullmatch(r"[А-ЯЁ]\.[А-ЯЁ]\.?", p_clean) or \
                    re.fullmatch(r"[А-ЯЁ]{2}", p_clean):
                initials.extend(re.findall(r"[А-ЯЁ]", p_clean.upper()))
            elif re.fullmatch(r"[А-ЯЁ][а-яё\-]+", p_clean) and surname is None:
                surname = p_clean

        if surname is None and parts:
            surname = parts[0].strip(".,;:")

        surname_norm = _normalize_word(surname) if surname else ""

        ini_str = ""
        if initials:
            ini_str = ".".join(initials[:2]) + "."

        return surname_norm, ini_str

    # ─────── Запись достижений ───────
    def append_achievement(self, data: dict):
        diploma_value = data.get("diploma", "")
        url = data.get("diploma_url", "")
        if url:
            diploma_cell = f'=HYPERLINK("{url}"; "📂 Открыть грамоту")'
        else:
            diploma_cell = diploma_value

        self.ws_ach.append_row([
            data.get("activity", "Конкурс"),
            data.get("contest", "Не указан"),
            data.get("nomination", ""),
            data.get("level", "Районный"),
            diploma_cell,
            data.get("fio", "Не распознан"),
            data.get("teacher", ""),
            data.get("uploaded_by", ""),
            url,
            data.get("publication_where", ""),
            data.get("publication_output", ""),
        ], value_input_option="USER_ENTERED")

    def all_achievements(self):
        return self.ws_ach.get_all_records()

    # ─────── Обновление существующей записи ───────
    def update_achievement_by_filename(self, filename: str, updates: dict) -> bool:
        if not filename:
            return False

        try:
            headers = self.ws_ach.row_values(1)
        except Exception as e:
            print(f"Не удалось прочитать заголовки: {e}")
            return False

        col_map = {}
        for idx, h in enumerate(headers, start=1):
            h_norm = str(h).strip()
            if h_norm in ("Диплом", "diploma", "filename"):
                col_map.setdefault("diploma", idx)
            elif h_norm in ("ФИО учащегося", "ФИО учащся", "fio", "Ученик"):
                col_map.setdefault("fio", idx)
            elif h_norm in ("ФИО учителя", "Учитель", "teacher"):
                col_map.setdefault("teacher", idx)
            elif h_norm in ("Номинация", "Класс", "klass"):
                col_map.setdefault("klass", idx)

        if "diploma" not in col_map:
            print("Колонка «Диплом» не найдена в листе")
            return False

        try:
            diploma_col = self.ws_ach.col_values(col_map["diploma"])
        except Exception as e:
            print(f"Не удалось прочитать колонку «Диплом»: {e}")
            return False

        base_name = os.path.basename(filename).strip().lower()
        target_row = None
        for idx, cell in enumerate(diploma_col):
            if idx == 0:
                continue
            cell_str = str(cell).strip().lower()
            if base_name and base_name in cell_str:
                target_row = idx + 1
                break
            if cell_str == base_name:
                target_row = idx + 1
                break

        if target_row is None:
            print(f"Строка с файлом {filename!r} не найдена в Google Sheets")
            return False

        try:
            if "fio" in col_map and "fio" in updates:
                self.ws_ach.update_cell(target_row, col_map["fio"], updates["fio"])
            if "teacher" in col_map and "teacher" in updates:
                self.ws_ach.update_cell(target_row, col_map["teacher"], updates["teacher"])
            if "klass" in col_map and "klass" in updates:
                self.ws_ach.update_cell(target_row, col_map["klass"], updates["klass"])
        except Exception as e:
            print(f"Ошибка обновления ячеек: {e}")
            return False

        return True

    def update_achievement_by_fio_and_contest(self, fio: str, contest: str, klass: str, updates: dict) -> bool:
        if not fio or fio in ("Не распознан", "—"):
            return False

        try:
            headers = self.ws_ach.row_values(1)
            col_map = {}
            for idx, h in enumerate(headers, start=1):
                h_norm = str(h).strip().lower()
                if h_norm in ("фио учащегося", "фио учащся", "fio", "ученик", "учащийся"):
                    col_map["fio"] = idx
                elif h_norm in ("фамилия",):
                    col_map["surname"] = idx
                elif h_norm in ("имя",):
                    col_map["name"] = idx
                elif h_norm in ("отчество",):
                    col_map["patronym"] = idx
                elif h_norm in ("фио учителя", "учитель", "teacher", "педагог"):
                    col_map["teacher"] = idx
                elif h_norm in ("номинация", "класс", "klass"):
                    col_map["klass"] = idx
                elif h_norm in ("название деятельности", "название", "деятельность", "contest", "конкурс"):
                    col_map["contest"] = idx

            all_data = self.ws_ach.get_all_values()
            target_row = None

            # Если ФИО было не распознано, ищем любую строку с "Не распознан" или пустую
            if not fio or fio in ("Не распознан", "—", ""):
                for idx in range(len(all_data) - 1, 0, -1):
                    row = all_data[idx]
                    r_fio = row[col_map.get("fio", 1) - 1].strip() if "fio" in col_map and len(row) >= col_map[
                        "fio"] else ""
                    if r_fio in ("Не распознан", "—", ""):
                        target_row = idx + 1
                        break
            else:
                parts = fio.split()
                for idx in range(len(all_data) - 1, 0, -1):
                    row = all_data[idx]
                    r_fio = row[col_map.get("fio", 1) - 1].strip() if "fio" in col_map and len(row) >= col_map[
                        "fio"] else ""
                    if parts and parts[0].lower() in r_fio.lower():
                        target_row = idx + 1
                        break

            # Запасной вариант: если точная строка не нашлась, берем последнюю строку с "Не распознан"
            if target_row is None:
                for idx in range(len(all_data) - 1, 0, -1):
                    row = all_data[idx]
                    r_fio = row[col_map.get("fio", 1) - 1].strip() if "fio" in col_map and len(row) >= col_map[
                        "fio"] else ""
                    if r_fio in ("Не распознан", "—", ""):
                        target_row = idx + 1
                        break

            if target_row is None:
                print(f"Строка для обновления не найдена в Google Sheets.")
                return False

            new_fio = updates.get("fio", "")
            new_teacher = updates.get("teacher", "")
            new_contest = updates.get("contest", "")

            # Разбиваем новое ФИО
            new_parts = new_fio.split()
            n_surname = new_parts[0] if len(new_parts) > 0 else ""
            n_name = new_parts[1] if len(new_parts) > 1 else ""
            n_patronym = new_parts[2] if len(new_parts) > 2 else ""

            # Обновляем те колонки, которые есть в таблице
            if "fio" in col_map and new_fio:
                self.ws_ach.update_cell(target_row, col_map["fio"], new_fio)
            if "surname" in col_map and n_surname:
                self.ws_ach.update_cell(target_row, col_map["surname"], n_surname)
            if "name" in col_map and n_name:
                self.ws_ach.update_cell(target_row, col_map["name"], n_name)
            if "patronym" in col_map and n_patronym:
                self.ws_ach.update_cell(target_row, col_map["patronym"], n_patronym)

            # Обновляем учителя, класс и конкурс
            if "teacher" in col_map and new_teacher:
                self.ws_ach.update_cell(target_row, col_map["teacher"], new_teacher)
            if "klass" in col_map and klass:
                self.ws_ach.update_cell(target_row, col_map["klass"], klass)
            if "contest" in col_map and new_contest and new_contest not in ("Не указан", "—", ""):
                self.ws_ach.update_cell(target_row, col_map["contest"], new_contest)

            return True
        except Exception as e:
            print(f"Ошибка при обновлении: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    #                    HTML-ГАЛЕРЕЯ
    # ═══════════════════════════════════════════════════════════
    @staticmethod
    def _normalize_klass(raw: str) -> str:
        if not raw:
            return "Без класса"
        s = str(raw).strip().upper().replace("Ё", "Е")
        m = re.match(r"^(\d{1,2})\s*[-–—]?\s*([А-ЯA-Z])$", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        return "Без класса"

    @staticmethod
    def _klass_sort_key(klass: str):
        m = re.match(r"^(\d{1,2})-([А-ЯA-Z])$", klass)
        if m:
            return (0, int(m.group(1)), m.group(2))
        return (1, 999, klass)

    @staticmethod
    def _extract_drive_url_static(cell) -> str:
        if not cell:
            return ""
        s = str(cell).strip()
        m = re.search(r'HYPERLINK\(\s*"([^"]+)"', s, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r'https?://\S+', s)
        if m:
            return m.group(0).rstrip('");, ')
        m = re.search(r'\b([A-Za-z0-9_\-]{25,})\b', s)
        if m:
            return f"https://drive.google.com/file/d/{m.group(1)}/view"
        return ""

    def _collect_gallery_items(self, rows=None):
        if rows is None:
            try:
                rows = self.all_achievements()
            except Exception as e:
                print(f"Галерея: не удалось прочитать Достижения: {e}")
                rows = []

        items = []
        for r in rows:
            fio = (r.get("ФИО учащегося") or r.get("ФИО учащся")
                   or r.get("fio") or "").strip()
            if not fio or fio in ("Не распознан", "Не указан"):
                continue

            klass_raw = (r.get("Номинация") or r.get("Класс")
                         or r.get("klass") or "")
            klass = self._normalize_klass(klass_raw)

            contest = (r.get("Название деятельности") or r.get("Название")
                       or r.get("Деятельность") or r.get("contest") or "").strip()
            level = (r.get("Уровень") or r.get("level") or "").strip()
            teacher = (r.get("ФИО учителя") or r.get("Учитель")
                       or r.get("teacher") or "").strip()
            nomination = (r.get("Номинация") or r.get("nomination") or "").strip()
            author = (r.get("Загрузил") or r.get("author") or "").strip()

            url = ""
            for key in ("Diploma URL", "diploma_url", "Ссылка", "URL"):
                v = r.get(key)
                if v:
                    url = str(v).strip()
                    break
            if not url:
                raw = r.get("Диплом") or r.get("diploma") or ""
                url = self._extract_drive_url_static(raw)
            if not url:
                continue

            items.append({
                "fio": fio,
                "klass": klass,
                "contest": contest or "Конкурс",
                "level": level or "—",
                "teacher": teacher,
                "nomination": nomination,
                "author": author,
                "url": url,
            })
        return items

    def build_html_gallery(self, out_path=None, rows=None) -> str:
        items = self._collect_gallery_items(rows=rows)
        if not items:
            print("Галерея: нет записей с грамотами — файл не создан.")
            return ""

        by_klass = {}
        for it in items:
            by_klass.setdefault(it["klass"], []).append(it)

        for k in by_klass:
            by_klass[k].sort(key=lambda x: (x["fio"].lower(), x["contest"].lower()))

        sorted_klasses = sorted(by_klass.keys(), key=self._klass_sort_key)
        all_levels = sorted({it["level"] for it in items
                             if it["level"] and it["level"] != "—"})

        if out_path is None:
            try:
                from config import GALLERY_DIR, GALLERY_FILE
            except Exception:
                GALLERY_DIR, GALLERY_FILE = "Archive", "gallery.html"
            os.makedirs(GALLERY_DIR, exist_ok=True)
            out_path = os.path.join(GALLERY_DIR, GALLERY_FILE)

        e = _html.escape
        now = _dt.now().strftime("%d.%m.%Y %H:%M")

        parts = []
        parts.append(f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🎓 {getattr(config, 'GALLERY_TITLE', 'Галерея грамот')}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: 'Segoe UI', Arial, sans-serif;
         background:#F4F6FB; color:#0F172A; }}
  header {{ background:#1F4E78; color:#fff; padding:22px 28px; }}
  header h1 {{ margin:0; font-size:24px; }}
  header .meta {{ opacity:.85; font-size:12px; margin-top:4px; }}
  .toolbar {{ position:sticky; top:0; z-index:5; background:#fff;
             border-bottom:1px solid #E2E8F0; padding:12px 28px;
             display:flex; gap:14px; flex-wrap:wrap; align-items:center; }}
  .toolbar input, .toolbar select {{
      padding:8px 12px; border:1px solid #E2E8F0; border-radius:8px;
      font-size:14px; outline:none; background:#F8FAFC; }}
  .toolbar input:focus, .toolbar select:focus {{ border-color:#2563EB; }}
  .toolbar .counter {{ margin-left:auto; font-size:12px; color:#64748B; }}
  main {{ max-width:1400px; margin:0 auto; padding:24px 28px 60px; }}
  .klass-block {{ margin-bottom:34px; }}
  .klass-title {{ display:flex; align-items:center; gap:12px; margin:0 0 14px; }}
  .klass-title h2 {{ margin:0; font-size:20px; color:#1F4E78; }}
  .klass-title .badge {{ background:#DBEAFE; color:#1D4ED8; font-size:12px;
                        font-weight:700; padding:3px 10px; border-radius:20px; }}
  .grid {{ display:grid; gap:14px;
          grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }}
  .card {{ background:#fff; border:1px solid #E2E8F0; border-radius:12px;
          overflow:hidden; display:flex; flex-direction:column;
          transition: box-shadow .15s, transform .15s; cursor:pointer; }}
  .card:hover {{ box-shadow:0 6px 22px rgba(15,23,42,.10); transform:translateY(-2px); }}

  .img-container {{
    width: 100%; aspect-ratio: 4/3; background: #F1F5F9;
    display: flex; align-items: center; justify-content: center; overflow: hidden;
    position: relative;
  }}
  .img-container img {{
    width: 100%; height: 100%; object-fit: cover;
  }}
  .no-img {{
    font-size: 40px; color: #94A3B8;
  }}

  .card-body {{ padding:10px 12px 12px; display:flex; flex-direction:column;
               gap:4px; flex:1; }}
  .fio {{ font-weight:700; font-size:13px; }}
  .contest {{ font-size:11.5px; color:#334155; line-height:1.35; }}
  .lvl {{ align-self:flex-start; font-size:10.5px; font-weight:700;
         padding:2px 8px; border-radius:20px; margin-top:auto; }}
  .lvl-Районный         {{ background:#F5EFC9; color:#8A6D00; }}
  .lvl-Областной        {{ background:#DBEAFE; color:#1D4ED8; }}
  .lvl-Республиканский  {{ background:#D1FAE5; color:#047857; }}
  .lvl-Международный    {{ background:#FCE7F3; color:#BE185D; }}
  .lvl-—                {{ background:#E5E7EB; color:#374151; }}
  .teacher {{ font-size:10.5px; color:#64748B; }}
  .empty {{ text-align:center; color:#64748B; padding:60px 20px; }}

  #lightbox {{
    display: none; position: fixed; z-index: 9999; top:0; left:0; width:100%; height:100%;
    background: rgba(15, 23, 42, 0.9); justify-content: center; align-items: center;
  }}
  #lightbox img {{
    max-width: 90%; max-height: 90%; box-shadow: 0 0 20px rgba(0,0,0,0.5);
    border-radius: 8px; transform: scale(0.95); transition: transform 0.2s;
  }}
  #lightbox.active {{ display: flex; }}
  #lightbox.active img {{ transform: scale(1); }}
  .close-btn {{
    position: absolute; top: 20px; right: 30px; color: white;
    font-size: 40px; font-weight: bold; cursor: pointer;
  }}
</style>
</head>
<body>
<header>
  <h1>🎓 {getattr(config, 'GALLERY_TITLE', 'Галерея грамот')}</h1>
  <div class="meta">Обновлено: {e(now)} &nbsp;·&nbsp; классов: {len(sorted_klasses)}
       &nbsp;·&nbsp; грамот: {len(items)}</div>
</header>
<div class="toolbar">
  <input id="q" type="search" placeholder="🔍 Поиск по ФИО, конкурсу, учителю...">
  <select id="lvl">
    <option value="">Все уровни</option>
""")
        for lv in all_levels:
            parts.append(f'    <option value="{e(lv)}">{e(lv)}</option>\n')
        parts.append("""  </select>
  <select id="kls">
    <option value="">Все классы</option>
""")
        for k in sorted_klasses:
            parts.append(f'    <option value="{e(k)}">{e(k)}</option>\n')
        parts.append(f"""  </select>
  <span class="counter" id="counter">Показано: {len(items)}</span>
</div>
<main id="main">
""")

        for k in sorted_klasses:
            group = by_klass[k]
            parts.append(f'<section class="klass-block" data-klass="{e(k)}">\n')
            parts.append(
                f'  <div class="klass-title"><h2>{e(k)}</h2>'
                f'<span class="badge">{len(group)}</span></div>\n'
            )
            parts.append('  <div class="grid">\n')
            for it in group:
                file_id = ""
                m = re.search(r'/(?:file/d/|d/|id=)([a-zA-Z0-9_-]+)', it["url"])
                if m: file_id = m.group(1)

                if file_id:
                    img_url = f"https://wsrv.nl/?url=drive.google.com/thumbnail?id={file_id}&sz=w800"
                    direct_link = f"https://drive.google.com/file/d/{file_id}/view"
                else:
                    img_url = ""
                    direct_link = it["url"]

                parts.append(
                    f'    <div class="card" onclick="openLightbox(\'{e(img_url)}\')"\n'
                    f'       data-fio="{e(it["fio"].lower())}"\n'
                    f'       data-contest="{e(it["contest"].lower())}"\n'
                    f'       data-teacher="{e(it["teacher"].lower())}"\n'
                    f'       data-level="{e(it["level"])}"\n'
                    f'       data-klass="{e(it["klass"])}">\n'
                    f'      <div class="img-container">\n'
                )

                if img_url:
                    parts.append(
                        f'        <img loading="lazy" src="{e(img_url)}" alt="{e(it["fio"])}" '
                        f'onerror="this.style.display=\'none\'; this.nextElementSibling.style.display=\'block\';">\n'
                        f'        <div class="no-img" style="display:none;">📄</div>\n'
                    )
                else:
                    parts.append(f'        <div class="no-img">📄</div>\n')

                parts.append(
                    f'      </div>\n'
                    f'      <div class="card-body">\n'
                    f'        <div class="fio">{e(it["fio"])}</div>\n'
                    f'        <div class="contest">{e(it["contest"])}</div>\n'
                )
                if it["teacher"]:
                    parts.append(
                        f'        <div class="teacher">👩‍🏫 {e(it["teacher"])}</div>\n'
                    )
                parts.append(
                    f'        <span class="lvl lvl-{e(it["level"])}">{e(it["level"])}</span>\n'
                    f'      </div>\n'
                    f'    </div>\n'
                )
            parts.append('  </div>\n</section>\n')

        parts.append("""</main>
<div id="lightbox" onclick="closeLightbox(event)">
  <span class="close-btn" onclick="closeLightbox(event)">&times;</span>
  <img id="lightbox-img" src="" alt="Грамота">
</div>
<script>
function openLightbox(imgSrc) {
  if (!imgSrc) return;
  const lb = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  img.src = imgSrc;
  lb.classList.add('active');
}
function closeLightbox(e) {
  if (e.target.id === 'lightbox' || e.target.classList.contains('close-btn')) {
    document.getElementById('lightbox').classList.remove('active');
    document.getElementById('lightbox-img').src = '';
  }
}

(function () {
  const q     = document.getElementById('q');
  const lvl   = document.getElementById('lvl');
  const kls   = document.getElementById('kls');
  const cnt   = document.getElementById('counter');
  const cards = Array.from(document.querySelectorAll('.card'));
  const blocks= Array.from(document.querySelectorAll('section.klass-block'));

  function apply() {
    const needle = q.value.trim().toLowerCase();
    const lv = lvl.value, kl = kls.value;
    let shown = 0;

    cards.forEach(c => {
      const okText = !needle ||
        c.dataset.fio.includes(needle) ||
        c.dataset.contest.includes(needle) ||
        c.dataset.teacher.includes(needle);
      const okLvl = !lv || c.dataset.level === lv;
      const okKl  = !kl || c.dataset.klass === kl;
      const ok = okText && okLvl && okKl;
      c.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });

    blocks.forEach(b => {
      const vis = b.querySelectorAll('.card:not([style*="display: none"])').length;
      b.style.display = vis ? '' : 'none';
      const badge = b.querySelector('.badge');
      if (badge) badge.textContent = vis;
    });

    cnt.textContent = 'Показано: ' + shown;
  }

  [q, lvl, kls].forEach(el => el.addEventListener('input', apply));
})();
</script>
</body>
</html>
""")

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("".join(parts))
        except Exception as e:
            print(f"Галерея: ошибка записи {out_path}: {e}")
            return ""

        print(f"Галерея: сохранено {len(items)} записей → {out_path}")
        return out_path
