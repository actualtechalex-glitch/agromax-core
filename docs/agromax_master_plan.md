# Project Master-Plan: AGROMAX v35.0 «Infinity»
**Версия:** 35.0-HKU-FINAL
**Стек:** LightRAG (HKU) + PostgreSQL 16 + Playwright + Google Drive API v3

## 1. Архитектурное ядро (Core)
Система переведена на двухслойный граф знаний LightRAG (Hong Kong University). Хранение на Google Drive.

## 2. Модуль Spider-Scout (Автономный сбор)
*   **Автономная авторизация** через storage_state.json.
*   **Пагинация** через URL (?page=N).
*   **Переименование** кириллицей по заголовку ссылки.

## 3. Модуль Slicer-Archive
*   **Рекурсивная распаковка** матрешек (ZIP/RAR) в SSD-буфере.
*   **Слайсинг A4** в памяти (BytesIO).
*   **Детекция A1-A3** (MediaBox > 1000 pts) - без нарезки.

## 4. Semantic Worker (Worker 1)
*   **Header-Scout**: анализ 1-й страницы для извлечения реального заголовка документа в БД.
