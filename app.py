# -*- coding: utf-8 -*-
"""Streamlit: таблица достижений + превью грамот."""
import re
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from config import CREDS_FILE, SHEET_ID, LIST_ACHIEVEMENTS

# ▼▼▼ ИЗМЕНЕНО: Название вкладки браузера ▼▼▼
st.set_page_config(page_title="MeritHub",
                   page_icon="🎓", layout="wide")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]


@st.cache_resource(show_spinner=False)
def get_sheet():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID).worksheet(LIST_ACHIEVEMENTS)


def extract_drive_url(cell_value) -> str:
    """Достаёт URL из ячейки: HYPERLINK, чистая ссылка или ID."""
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


# ▼▼▼ ИЗМЕНЕНО: Главный заголовок на странице ▼▼▼
st.markdown("<h1 style='margin-bottom:0'>🎓 MeritHub</h1>",
            unsafe_allow_html=True)
st.markdown("### 📋 Сводная таблица достижений")

try:
    ws = get_sheet()
    rows = ws.get_all_records()
except Exception as e:
    st.error(f"Не удалось подключиться к Google Sheets: {e}")
    st.stop()

df = pd.DataFrame(rows)
if df.empty:
    st.warning("Пока нет записей.")
    st.stop()

# Чистим имена колонок от лишних пробелов
df.columns = [c.strip() for c in df.columns]

# ─── Диагностика ───
with st.expander("🔧 Диагностика данных", expanded=False):
    st.write("**Колонки:**", list(df.columns))
    if "Диплом" in df.columns:
        st.write("**Пример «Диплом»:**", repr(df["Диплом"].iloc[0]))
    if "Diploma URL" in df.columns:
        st.write("**Пример «Diploma URL»:**", repr(df["Diploma URL"].iloc[0]))

# ─── Фильтры ───
col1, col2, col3 = st.columns(3)
with col1:
    klass_col = "Номинация" if "Номинация" in df.columns else df.columns[0]
    classes = ["Все"] + sorted({str(v) for v in df[klass_col] if v})
    klass_filter = st.selectbox("Класс / Номинация", classes)
with col2:
    lvl_col = "Уровень" if "Уровень" in df.columns else df.columns[0]
    levels = ["Все"] + sorted({str(v) for v in df[lvl_col] if v})
    level_filter = st.selectbox("Уровень", levels)
with col3:
    search = st.text_input("🔍 Поиск по ФИО", "")

view = df.copy()
if klass_filter != "Все":
    view = view[view[klass_col].astype(str) == klass_filter]
if level_filter != "Все":
    view = view[view[lvl_col].astype(str) == level_filter]
if search and "ФИО учащся" in view.columns:
    view = view[view["ФИО учащся"].astype(str)
                .str.contains(search, case=False, na=False)]

st.success(f"Данные загружены из облака. Записей: {len(view)} (из {len(df)})")

# ─── Таблица + превью ───
left, right = st.columns([3, 1])

view = view.reset_index(drop=True)
view.index = view.index + 1

# Ищем URL: сначала «Diploma URL», потом «Диплом»
url_col = None
if "Diploma URL" in view.columns:
    url_col = "Diploma URL"
elif "Диплом" in view.columns:
    view["_url"] = view["Диплом"].apply(extract_drive_url)
    url_col = "_url"

with left:
    display_view = view.drop(columns=[url_col], errors="ignore") if url_col else view
    event = st.dataframe(
        display_view,
        use_container_width=True,
        hide_index=False,
        on_select="rerun",
        selection_mode="single-row",
    )

with right:
    st.markdown("#### 📂 Просмотр грамоты")
    has_selection = (
        isinstance(event, dict)
        and "selection" in event
        and event["selection"].get("rows")
    )
    if has_selection:
        sel_row = event["selection"]["rows"][0] + 1
        url = view.loc[sel_row, url_col] if url_col in view.columns else ""
        if url:
            embed_url = url.replace("/view", "/preview") \
                           .replace("?usp=sharing", "") \
                           .replace("?usp=drivesdk", "")
            try:
                st.image(embed_url, use_container_width=True)
            except Exception:
                st.warning("Не удалось отобразить превью.")
            st.markdown(f"[📂 Открыть в Drive]({url})")
            fio = view.loc[sel_row].get("ФИО учащся", "")
            contest = view.loc[sel_row].get("Название деятельности", "")
            if fio:
                st.caption(f"**{fio}**")
            if contest:
                st.caption(contest)
        else:
            st.info("У выбранной записи нет ссылки на грамоту.")
    else:
        st.info("👈 Выберите строку в таблице, чтобы увидеть грамоту.")

st.download_button("📥 Скачать CSV",
                   data=view.drop(columns=["_url"], errors="ignore")
                           .to_csv(index=False).encode("utf-8-sig"),
                   file_name="svodnaya_tablica.csv",
                   mime="text/csv")