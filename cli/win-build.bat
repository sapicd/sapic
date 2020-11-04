@echo off

pyinstaller.exe -F cli.py -i logo.ico -n picbed-cli && del *.spec && rd /S /Q build
