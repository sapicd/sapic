@echo off

if "%1"=="" (set cmd=pyinstaller.exe) else (set cmd=%1)

%cmd% -F cli.py -i logo.ico -n picbed-cli --distpath .\ && del *.spec && rd /S /Q build
