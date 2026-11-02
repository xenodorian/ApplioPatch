@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Applio vocal restoration patch - uninstall
cd /d "%~dp0"

set "APPLIO=D:\Applio-3.6.4"
if not "%~1"=="" set "APPLIO=%~1"

echo ============================================
echo  Applio vocal restoration patch - UNINSTALL
echo ============================================
echo.

rem ---- Step 2: find the Applio folder ----
:check_target
call :is_valid_target
if "!VALID!"=="1" goto target_ok
echo.
echo The Applio folder was not found or is not valid:
echo   !APPLIO!
echo A valid Applio folder contains core.py and rvc\infer\pipeline.py.
echo Type the Applio folder path, or Q to quit.
set "APPLIO="
set /p "APPLIO=Applio folder: "
set "APPLIO=!APPLIO:"=!"
if /i "!APPLIO!"=="Q" goto cancelled
goto check_target

:target_ok
set "BK=!APPLIO!\_vocal_patch_backup"
echo Target: !APPLIO!
echo.
if not exist "!BK!\" goto nothing_to_restore
if not exist "!BK!\NEW_FILES.txt" goto no_marker

echo IMPORTANT: close Applio completely before continuing.
echo.
pause

rem ---- Restore originals, then remove new files, then the backup folder ----
set "RS_ERR="
set "RS_WARN="
call :restore_one core.py
call :restore_one rvc\infer\infer.py
call :restore_one rvc\infer\pipeline.py
call :restore_one rvc\lib\utils.py
call :restore_one tabs\inference\inference.py
if defined RS_ERR goto fail_restore

set "DEL_ERR="
call :delete_new rvc\lib\tools\audio_restore.py
call :delete_new rvc\lib\tools\audio_restore_worker.py
if defined DEL_ERR goto fail_restore

rmdir /s /q "!BK!"
if exist "!BK!\" goto fail_restore
echo.
echo Backup folder removed.
goto done_info

rem ---- Messages and exits ----
:done_info
echo.
if defined RS_WARN echo Uninstall finished, but some files had no backup and were not restored.
if not defined RS_WARN echo Uninstall complete. The original files are restored.
echo.
echo The sidecar environments were NOT removed. They are large, about 6 GB
echo for each restorer. To free disk space, delete the folder named
echo assets\audio-restore inside the Applio folder. It can be deleted by
echo hand at any time.
echo.
pause
exit /b 0

:nothing_to_restore
echo No vocal patch backup was found in this Applio folder.
echo Nothing to restore.
pause
exit /b 0

:no_marker
echo ERROR: the backup folder has no NEW_FILES.txt, so the new files
echo cannot be identified safely. Nothing was changed.
goto fail_pause

:fail_restore
echo.
echo ERROR: restore did not finish. The backup folder was kept.
echo Check the messages above, close Applio, and run this again.
goto fail_pause

:cancelled
echo Cancelled. Nothing was changed.
goto fail_pause

:fail_pause
pause
exit /b 1

rem ---- Subroutines ----

:is_valid_target
set "VALID=0"
if "!APPLIO!"=="" goto :eof
if not exist "!APPLIO!\core.py" goto :eof
if not exist "!APPLIO!\rvc\infer\pipeline.py" goto :eof
set "VALID=1"
goto :eof

:restore_one
rem %1 = relative path
if defined RS_ERR goto :eof
if not exist "!BK!\%~1" goto rs_nobackup
copy /y "!BK!\%~1" "!APPLIO!\%~1" >nul
if errorlevel 1 goto rs_fail
echo   restored %~1
goto :eof

:rs_nobackup
echo WARNING: no backup for %~1, left as is
set "RS_WARN=1"
goto :eof

:rs_fail
echo ERROR: could not restore %~1
set "RS_ERR=1"
goto :eof

:delete_new
rem %1 = relative path of a new file listed in NEW_FILES.txt
if defined DEL_ERR goto :eof
findstr /i /l /c:"%~1" "!BK!\NEW_FILES.txt" >nul 2>nul
if errorlevel 1 goto :eof
if not exist "!APPLIO!\%~1" goto :eof
del /q "!APPLIO!\%~1"
if exist "!APPLIO!\%~1" goto dn_fail
echo   deleted %~1
goto :eof

:dn_fail
echo ERROR: could not delete %~1
set "DEL_ERR=1"
goto :eof
