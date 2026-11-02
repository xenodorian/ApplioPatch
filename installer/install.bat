@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Applio vocal restoration patch - install
cd /d "%~dp0"
echo "%~dp0"| findstr /c:"!" >nul
if not errorlevel 1 goto err_bang
setlocal EnableDelayedExpansion
echo "%~dp0"| findstr /i /c:".zip" >nul
if not errorlevel 1 goto err_zip

set "PAYLOAD=%~dp0payload"
set "STOCKFILE=%~dp0stock_hashes.txt"

echo ==========================================
echo  Applio vocal restoration patch - INSTALL
echo ==========================================
echo.

rem ---- Step 3: package must be complete ----
if not exist "%PAYLOAD%\" goto err_nopayload
if not exist "%STOCKFILE%" goto err_nostock

set "MISSING="
for %%F in (core.py rvc\infer\infer.py rvc\infer\pipeline.py rvc\lib\utils.py tabs\inference\inference.py rvc\lib\tools\audio_restore.py rvc\lib\tools\audio_restore_worker.py) do if not exist "%PAYLOAD%\%%F" set "MISSING=%%F"
if defined MISSING goto err_payfile

rem ---- Step 2: find the Applio folder ----
set "APPLIO=D:\Applio-3.6.4"
if not "%~1"=="" set "APPLIO=%~1"

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
echo.
echo Target: !APPLIO!
echo.
echo IMPORTANT: close Applio completely before continuing.
echo Also close any console window started by run-applio.bat.
echo.
pause

rem ---- Step 5: check every file before changing anything ----
echo.
echo Checking files...
set "CHECK_ERR="
call :check_one 1 core.py
call :check_one 2 rvc\infer\infer.py
call :check_one 3 rvc\infer\pipeline.py
call :check_one 4 rvc\lib\utils.py
call :check_one 5 tabs\inference\inference.py
if defined CHECK_ERR goto fail

call :confirm_one 1 core.py
call :confirm_one 2 rvc\infer\infer.py
call :confirm_one 3 rvc\infer\pipeline.py
call :confirm_one 4 rvc\lib\utils.py
call :confirm_one 5 tabs\inference\inference.py

rem ---- Step 6: backup (never overwrites an existing backup) ----
echo.
echo Backing up original files to:
echo   !BK!
if not exist "!BK!\" mkdir "!BK!"
if not exist "!BK!\" goto fail_backup
set "BK_ERR="
call :backup_one 1 core.py
call :backup_one 2 rvc\infer\infer.py
call :backup_one 3 rvc\infer\pipeline.py
call :backup_one 4 rvc\lib\utils.py
call :backup_one 5 tabs\inference\inference.py
if defined BK_ERR goto fail_backup

> "!BK!\NEW_FILES.txt" echo rvc\lib\tools\audio_restore.py
>> "!BK!\NEW_FILES.txt" echo rvc\lib\tools\audio_restore_worker.py
if not exist "!BK!\NEW_FILES.txt" goto fail_backup

rem ---- Step 7: copy payload into the Applio tree ----
echo.
echo Copying patched files...
set "CP_ERR="
call :copy_one 1 core.py
call :copy_one 2 rvc\infer\infer.py
call :copy_one 3 rvc\infer\pipeline.py
call :copy_one 4 rvc\lib\utils.py
call :copy_one 5 tabs\inference\inference.py
call :copy_plain rvc\lib\tools\audio_restore.py
call :copy_plain rvc\lib\tools\audio_restore_worker.py
if defined CP_ERR goto fail_copy

goto success

rem ---- Messages and exits ----
:success
echo.
echo ==========================================
echo  Install complete.
echo ==========================================
echo.
echo Next steps:
echo   1. Start Applio with run-applio.bat.
echo   2. Open the Inference tab.
echo   3. Use the Vocal restoration panel.
echo.
echo The first time you use a restorer, Applio downloads a large sidecar
echo environment, about 6 GB for each restorer. Internet access is needed
echo for that first use.
echo Keep at least 12 GB free on the drive that holds Applio.
echo.
pause
exit /b 0

:cancelled
echo.
echo Cancelled. No files were changed.
pause
exit /b 1

:user_abort
echo.
echo Install cancelled. No files were changed.
pause
exit /b 1

:fail_backup
echo.
echo ERROR: could not create the backup. No files were changed.
pause
exit /b 1

:fail_copy
echo.
echo ERROR: a file copy failed. The Applio folder may be partly patched.
echo Run uninstall.bat to restore the original files, then try again.
pause
exit /b 1

:fail
echo.
echo Install FAILED. See the messages above.
pause
exit /b 1

:err_nopayload
echo ERROR: the payload folder was not found next to install.bat.
echo Extract the complete patch package and run this again.
goto fail

:err_nostock
echo ERROR: stock_hashes.txt was not found next to install.bat.
echo Extract the complete patch package and run this again.
goto fail

:err_payfile
echo ERROR: a payload file is missing: !MISSING!
echo Extract the complete patch package and run this again.
goto fail

:err_bang
echo ERROR: this folder path contains an exclamation mark. Move the patch folder to a path without one, such as C:\ApplioPatch, and run again.
goto fail

:err_zip
echo ERROR: the patch seems to be running from inside a ZIP file or a temporary folder. Extract the whole ZIP to a normal folder first, then run install.bat again.
goto fail

rem ---- Subroutines ----

:is_valid_target
set "VALID=0"
if "!APPLIO!"=="" goto :eof
if not exist "!APPLIO!\core.py" goto :eof
if not exist "!APPLIO!\rvc\infer\pipeline.py" goto :eof
set "VALID=1"
goto :eof

:check_one
rem %1 = index, %2 = relative path
set "CK_IDX=%~1"
set "CK_REL=%~2"
set "CK_SRC=%PAYLOAD%\%~2"
set "CK_DST=!APPLIO!\%~2"
set "ST!CK_IDX!=UNKNOWN"
set "SHASH="
set "PHASH="
set "THASH="
for /f "tokens=1" %%H in ('findstr /i /l /c:" %~2" "%STOCKFILE%"') do if not defined SHASH set "SHASH=%%H"
if not defined SHASH goto ck_nostock
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "%CK_SRC%" SHA256') do if not defined PHASH set "PHASH=%%H"
set "PHASH=!PHASH: =!"
if "!PHASH:~63,1!"=="" goto ck_badhash
if not "!PHASH:~64,1!"=="" goto ck_badhash
if not exist "!CK_DST!" goto ck_new
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "!CK_DST!" SHA256') do if not defined THASH set "THASH=%%H"
set "THASH=!THASH: =!"
if "!THASH:~63,1!"=="" goto ck_badhash
if not "!THASH:~64,1!"=="" goto ck_badhash
if /i "!THASH!"=="!SHASH!" goto ck_patch
if /i "!THASH!"=="!PHASH!" goto ck_skip
set "ST!CK_IDX!=MOD"
echo   !CK_REL!: modified by something else
goto :eof

:ck_new
echo ERROR: !CK_REL! is missing from the Applio folder. This is not a complete Applio 3.6.4.
set "CHECK_ERR=1"
goto :eof

:ck_patch
set "ST!CK_IDX!=PATCH"
echo   !CK_REL!: original, will be patched
goto :eof

:ck_skip
set "ST!CK_IDX!=SKIP"
echo   !CK_REL!: already patched, skipped
goto :eof

:ck_nostock
echo ERROR: stock_hashes.txt has no line for !CK_REL!
set "CHECK_ERR=1"
goto :eof

:ck_badhash
echo ERROR: could not read a SHA256 hash for !CK_REL!
set "CHECK_ERR=1"
goto :eof

:confirm_one
rem %1 = index, %2 = relative path
if not "!ST%~1!"=="MOD" goto :eof
if exist "!BK!\%~2" goto :eof
set "CF_REL=%~2"
echo.
echo WARNING: !CF_REL! differs from both the original and the patched version.
echo It was probably modified by something else.
echo Continuing will overwrite that version.
choice /c YN /n /m "Overwrite anyway? (Y/N) "
if errorlevel 2 goto user_abort
goto :eof

:backup_one
rem %1 = index, %2 = relative path
if defined BK_ERR goto :eof
if "!ST%~1!"=="NEW" goto :eof
if "!ST%~1!"=="SKIP" goto :eof
set "BF=!BK!\%~2"
set "BS=!APPLIO!\%~2"
if exist "!BF!" goto bk_keep
set "BD="
for %%D in ("!BF!") do set "BD=%%~dpD"
if not exist "!BD!" mkdir "!BD!"
if not exist "!BD!" goto bk_fail
copy /y "!BS!" "!BF!" >nul || goto bk_fail
echo   backed up %~2
goto :eof

:bk_keep
echo   backup already exists, keeping it: %~2
goto :eof

:bk_fail
echo ERROR: could not back up %~2
set "BK_ERR=1"
goto :eof

:copy_one
rem %1 = index, %2 = relative path
if "!ST%~1!"=="SKIP" goto :eof
call :copy_plain "%~2"
goto :eof

:copy_plain
rem %1 = relative path
if defined CP_ERR goto :eof
set "CPD=!APPLIO!\%~1"
set "CPDIR="
for %%D in ("!CPD!") do set "CPDIR=%%~dpD"
if not exist "!CPDIR!" mkdir "!CPDIR!"
if not exist "!CPDIR!" goto cp_fail
copy /y "%PAYLOAD%\%~1" "!CPD!" >nul || goto cp_fail
fc /b "%PAYLOAD%\%~1" "!CPD!" >nul || goto cp_fail
echo   copied %~1
goto :eof

:cp_fail
echo ERROR: could not copy or verify %~1. Antivirus software or Windows Controlled folder access may be blocking writes to the Applio folder.
set "CP_ERR=1"
goto :eof
