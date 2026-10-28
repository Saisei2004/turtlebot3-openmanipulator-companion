@echo off
rem tb3-companion のサーバー（操作画面 + rosbridge + ドライバ）を、WSL の Ubuntu で起動する。
rem WSL のディストリビューション名は config\tb3.env の WSL_DISTRO（既定 Ubuntu-22.04）。tb3ctl が無くてもこれで動く。
setlocal
set "ROOT=%~dp0..\..\.."
set "DISTRO=Ubuntu-22.04"
if exist "%ROOT%\config\tb3.env" (
  for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b /c:"WSL_DISTRO=" "%ROOT%\config\tb3.env"`) do set "DISTRO=%%b"
)
start "" http://localhost:8080/
wsl.exe -d %DISTRO% --cd "%ROOT%" -- bash pc/scripts/start_server.sh
endlocal
