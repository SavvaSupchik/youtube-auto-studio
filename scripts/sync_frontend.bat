@echo off
REM Автоматическое одностороннее зеркалирование исходников frontend:
REM   локальная рабочая копия (с node_modules)  -->  бэкап на Google Диске (без node_modules)
REM
REM Зачем: рабочая копия frontend живёт ЛОКАЛЬНО (вне Google Drive File Stream),
REM потому что npm install через виртуальный диск Drive ненадёжен и медленный.
REM Но чтобы код был виден с других компьютеров под этим же Google-аккаунтом,
REM нужна свежая копия исходников на Диске. Этот скрипт следит за изменениями
REM в локальной папке и сам копирует их на Диск (без node_modules/dist/.vite).
REM
REM Работает в режиме монитора (/MON:1) - копирует сразу при появлении
REM изменений и продолжает следить дальше. Останови окно (Ctrl+C), когда
REM закончил работу с фронтендом.

setlocal
set "LOCAL_SRC=%USERPROFILE%\Projects\YouTube Auto Studio-frontend"
set "DRIVE_DST=%~dp0..\frontend"

echo === Зеркалирование frontend: локальная копия -^> Google Диск ===
echo Источник:  %LOCAL_SRC%
echo Назначение: %DRIVE_DST%
echo (node_modules, dist, .vite исключены из копирования)
echo.

robocopy "%LOCAL_SRC%" "%DRIVE_DST%" /MIR /XD node_modules dist .vite .git /XF package-lock.json /MON:1 /MOT:1 /R:3 /W:2 /NFL /NDL /NJH

endlocal
