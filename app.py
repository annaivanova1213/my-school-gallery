# -*- coding: utf-8 -*-
"""Streamlit: визуальная галерея грамот (онлайн, автообновление)."""
import re
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from config import CREDS_FILE, SHEET_ID, LIST_ACHIEVEMENTS, LIST_TEACHERS

st.set_page_config(page_title="Галерея грамот", page_icon="🎓", layout="wide")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]


# ─── Подключение: Secrets (облако) или файл (локально) ───
@st.cache_resource(show_spinner=False)
def get_spreadsheet():
    creds = None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except (KeyError, FileNotFoundError):
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)

    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def get_file_id(url: str) -> str:
    m = re.search(r'/(?:file/d/|d/|id=)([a-zA-Z0-9_-]+)', url)
    return m.group(1) if m else ""


def thumb_url(file_id: str, size: int = 600) -> str:
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{size}"


def extract_drive_url(cell_value) -> str:
    if not cell_value:
        return ""
    s = str(cell_value).strip()
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


def normalize_klass(raw: str) -> str:
    if not raw:
        return "Без класса"
    s = str(raw).strip().upper().replace("Ё", "Е")
    m_num = re.search(r'(\d{1,2})', s)
    if not m_num:
        return "Без класса"
    num = m_num.group(1)
    m_let = re.search(r'[А-ЯA-Z]', s)
    return f"{num}-{m_let.group(0)}" if m_let else num


def klass_sort_key(klass: str):
    m = re.match(r"^(\d{1,2})(?:-([А-ЯA-Z]))?$", klass)
    if m:
        return (0, int(m.group(1)), m.group(2) or "")
    return (1, 999, klass)


# ─── Загрузка данных ───
st.markdown("<h1 style='margin-bottom:0'>🎓 Галерея грамот</h1>", unsafe_allow_html=True)
st.caption("Онлайн-галерея достижений учащихся. Обновляется автоматически из Google Sheets.")

try:
    sh = get_spreadsheet()
    ws_ach = sh.worksheet(LIST_ACHIEVEMENTS)
    rows = ws_ach.get_all_records()

    # Загружаем справочник учителей для фото
    try:
        ws_teachers = sh.worksheet(LIST_TEACHERS)
        teacher_rows = ws_teachers.get_all_values()
        teacher_photos = {}
        for r in teacher_rows[1:]:
            if len(r) >= 3 and r[0].strip():
                fio = r[0].strip()
                url = r[2].strip()  # Столбец C (индекс 2)
                if url:
                    teacher_photos[fio] = url
    except Exception as e:
        teacher_photos = {}
        st.warning(f"Не удалось загрузить фото учителей: {e}")

except Exception as e:
    st.error(f"Не удалось подключиться к Google Sheets: {e}")
    st.stop()

# ─── Собираем карточки только с фото ───
items = []
for r in rows:
    r = {k.strip() if isinstance(k, str) else k: v for k, v in r.items()}
    fio = (r.get("ФИО учащегося") or r.get("ФИО учащся") or r.get("fio") or "").strip()
    if not fio or fio in ("Не распознан", "Не указан"):
        continue

    url = ""
    for key in ("Diploma URL", "diploma_url", "Ссылка", "URL"):
        v = r.get(key)
        if v:
            url = str(v).strip()
            break
    if not url:
        url = extract_drive_url(r.get("Диплом") or r.get("diploma") or "")
    if not url:
        continue

    fid = get_file_id(url)
    if not fid:
        continue

    klass = normalize_klass(r.get("Номинация") or r.get("Класс") or r.get("klass"))
    contest = (r.get("Название деятельности") or r.get("Название") or r.get("Деятельность") or "Конкурс").strip()
    level = (r.get("Уровень") or "—").strip()
    teacher = (r.get("ФИО учителя") or r.get("Учитель") or "").strip()

    items.append({
        "fio": fio, "klass": klass, "contest": contest,
        "level": level, "teacher": teacher,
        "file_id": fid, "url": url,
    })

if not items:
    st.warning("Пока нет записей с грамотами.")
    st.stop()

st.success(f"Всего грамот: {len(items)}")

# ─── Фильтры ───
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    search = st.text_input("🔍 Поиск по ФИО, конкурсу, учителю", "")
with c2:
    all_levels = ["Все"] + sorted({it["level"] for it in items if it["level"] and it["level"] != "—"})
    lvl_filter = st.selectbox("Уровень", all_levels)
with c3:
    all_klasses = ["Все"] + sorted({it["klass"] for it in items}, key=klass_sort_key)
    kls_filter = st.selectbox("Класс", all_klasses)

filtered = items
if search:
    q = search.lower()
    filtered = [it for it in filtered if
                q in it["fio"].lower() or q in it["contest"].lower() or q in it["teacher"].lower()]
if lvl_filter != "Все":
    filtered = [it for it in filtered if it["level"] == lvl_filter]
if kls_filter != "Все":
    filtered = [it for it in filtered if it["klass"] == kls_filter]

st.caption(f"Показано: {len(filtered)} из {len(items)}")

if not filtered:
    st.info("По вашему запросу ничего не найдено.")
    st.stop()

# ─── Группировка по классам ───
by_klass = {}
for it in filtered:
    by_klass.setdefault(it["klass"], []).append(it)

LEVEL_COLORS = {
    "Районный": "#8A6D00",
    "Областной": "#1D4ED8",
    "Республиканский": "#047857",
    "Международный": "#BE185D",
}

# ─── Рендер сетки карточек ───
for klass in sorted(by_klass.keys(), key=klass_sort_key):
    group = sorted(by_klass[klass], key=lambda x: (x["fio"].lower(), x["contest"].lower()))
    st.markdown(
        f"<h2 style='color:#1F4E78;margin:24px 0 12px;'>"
        f"{klass} <span style='background:#DBEAFE;color:#1D4ED8;"
        f"font-size:14px;padding:3px 10px;border-radius:20px;'>"
        f"{len(group)}</span></h2>",
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    for i, it in enumerate(group):
        with cols[i % 4]:
            # Фото диплома
            st.image(thumb_url(it["file_id"]), width=300)

            # ФИО ученика
            st.markdown(
                f"<div style='font-weight:700;font-size:14px;margin-top:-8px;'>{it['fio']}</div>",
                unsafe_allow_html=True,
            )

            # Название конкурса
            st.caption(it["contest"])

            # Учитель с аватаркой
            if it["teacher"]:
                t_url = teacher_photos.get(it["teacher"])
                if t_url:
                    t_fid = get_file_id(t_url)
                    if t_fid:
                        t_avatar = thumb_url(t_fid, size=40)  # Маленький размер для аватарки
                        # Вставляем круглое фото (object-fit: cover) и текст рядом
                        html_teacher = f"""
                        <div style='display:flex; align-items:center; margin-top:4px;'>
                            <img src='{t_avatar}' style='width:20px; height:20px; border-radius:50%; object-fit:cover; margin-right:6px;'>
                            <span style='font-size:12px; color:#64748B;'>{it['teacher']}</span>
                        </div>
                        """
                        st.markdown(html_teacher, unsafe_allow_html=True)
                    else:
                        st.caption(f"👩‍🏫 {it['teacher']}")
                else:
                    st.caption(f"👩‍🏫 {it['teacher']}")

            # Уровень (бейдж)
            color = LEVEL_COLORS.get(it["level"], "#374151")
            st.markdown(
                f"<span style='background:{color}22;color:{color};"
                f"font-size:11px;font-weight:700;padding:2px 8px;"
                f"border-radius:20px;'>{it['level']}</span>",
                unsafe_allow_html=True,
            )
            st.markdown("---")
