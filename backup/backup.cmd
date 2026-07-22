@echo off
chcp 65001 > nul

:: ==========================================
:: НАСТРОЙКИ (ИЗМЕНИТЕ ПОД СЕБЯ)
:: ==========================================
set "DB_NAME=my_database"
set "DB_USER=postgres"
set "PG_PASSWORD=your_secure_password"
set "PG_BIN_PATH=C:\Program Files\PostgreSQL\16\bin"

set "SERVER_SOURCE_DIR=C:\ServerData"
set "BACKUP_DEST_DIR=E:\Backups"
set "LOG_DIR=E:\Backups\Logs"
:: ==========================================

:: Создаем папки для бэкапов и логов
if not exist "%BACKUP_DEST_DIR%" mkdir "%BACKUP_DEST_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: Генерируем уникальный штамп времени для имени папки и лога
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "dt=%%I"
set "TIMESTAMP=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%_%dt:~8,2%-%dt:~10,2%-%dt:~12,2%"
set "CURRENT_BACKUP_DIR=%BACKUP_DEST_DIR%\Backup_%TIMESTAMP%"
set "LOG_FILE=%LOG_DIR%\backup_%TIMESTAMP%.log"

:: Функция записи в лог и на экран
echo === ЗАПУСК РЕЗЕРВНОГО КОПИРОВАНИЯ ===
echo [%DATE% %TIME%] === НАЧАЛО РАБОТЫ СКРИПТА === > "%LOG_FILE%"

echo Создание директории бэкапа: %CURRENT_BACKUP_DIR%
echo [%DATE% %TIME%] Создание директории: %CURRENT_BACKUP_DIR% >> "%LOG_FILE%"
mkdir "%CURRENT_BACKUP_DIR%" 2>nul

echo.
echo [1/2] Бэкап базы данных %DB_NAME%...
echo [%DATE% %TIME%] [1/2] Старт бэкапа БД %DB_NAME% >> "%LOG_FILE%"
set "DB_BACKUP_FILE=%CURRENT_BACKUP_DIR%\%DB_NAME%.backup"

:: Запуск pg_dump с перенаправлением вывода ошибок в лог-файл
"%PG_BIN_PATH%\pg_dump.exe" -U %DB_USER% -F c -b -v -f "%DB_BACKUP_FILE%" %DB_NAME% >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Не удалось создать бэкап базы данных! См. лог.
    echo [%DATE% %TIME%] [КРИТИЧЕСКАЯ ОШИБКА] Ошибка при дампе БД! Код возврата: %ERRORLEVEL% >> "%LOG_FILE%"
    pause
    exit /b %ERRORLEVEL%
) else (
    echo [%DATE% %TIME%] Бэкап БД успешно завершен. >> "%LOG_FILE%"
)

echo.
echo [2/2] Бэкап файлов сервера...
echo [%DATE% %TIME%] [2/2] Старт копирования файлов сервера >> "%LOG_FILE%"

:: Запуск robocopy с записью его собственного отчета в конец нашего лога
:: Параметры /NP и /NDL убирают лишний спам (прогресс в % и имена папок), оставляя только важные ошибки и итоговую таблицу
robocopy "%SERVER_SOURCE_DIR%" "%CURRENT_BACKUP_DIR%\ServerFiles" /E /Z /R:3 /W:5 /LOG+:"%LOG_FILE%" /V /NP /NDL

:: Robocopy возвращает коды от 0 до 7 при успешном копировании. Все что выше 7 - ошибка.
if %ERRORLEVEL% GEQ 8 (
    echo [ВНИМАНИЕ/ОШИБКА] При копировании файлов возникли проблемы! Проверьте лог-файл.
    echo [%DATE% %TIME%] [ОШИБКА] Robocopy завершился с кодом %ERRORLEVEL% >> "%LOG_FILE%"
) else (
    echo [%DATE% %TIME%] Копирование файлов успешно завершено. >> "%LOG_FILE%"
)

echo.
echo === БЭКАП ЗАВЕРШЕН ===
echo [%DATE% %TIME%] === КОНЕЦ РАБОТЫ СКРИПТА === >> "%LOG_FILE%"
echo Отчет сохранен в: %LOG_FILE%
pause
