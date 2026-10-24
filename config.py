# -*- coding: utf-8 -*-
"""Конфигурация проекта SchoolAchievement-Parser Pro."""

# ============ GOOGLE API ============
CREDS_FILE = "creds.json"
OAUTH_CREDS_FILE = "oauth_creds.json"
OAUTH_TOKEN_FILE = "oauth_token.json"

# ID Google-таблицы
SHEET_ID = "1ZqFSAPir6X477RA3xC3QgyAHH1WDj59OgDmwunX3E5g"

# Названия листов
LIST_STUDENTS     = "Справочник учеников"
LIST_ACHIEVEMENTS = "Достижения"
LIST_TEACHERS     = "Справочник учителей"

# ID папки Google Drive
DRIVE_FOLDER_ID = "11DH6gM0wrsAiA66-8pUpXPuvpteUz5RG"

# ============ ЛОКАЛЬНЫЙ АРХИВ ============
LOCAL_ARCHIVE = "Archive"
DIPLOMA_SUBFOLDER = "Грамоты учащихся"

# ============ HTML-ГАЛЕРЕЯ ============  # ← ДОБАВЛЕНО
GALLERY_DIR   = "Archive"
GALLERY_FILE  = "gallery.html"
GALLERY_TITLE = "Галерея грамот"


# ============ УЧЕБНЫЕ ГОДЫ ============
SCHOOL_YEARS = [
    "2026/2027",
    "2027/2028",
    "2028/2029",
    "2029/2030",
]
DEFAULT_YEAR = "2026/2027"


# ============ УРОВНИ НАГРАД ============
LEVEL_RAYON         = "Районный"
LEVEL_OBLAST        = "Областной"
LEVEL_REPUBLIC      = "Республиканский"
LEVEL_INTERNATIONAL = "Международный"

LEVELS = [
    LEVEL_RAYON,
    LEVEL_OBLAST,
    LEVEL_REPUBLIC,
    LEVEL_INTERNATIONAL,
]


# ============ ПРОЧЕЕ ============
DEBUG_FILE = "ocr_debug.txt"
DB_NAME = "school_master_portfolio.db"