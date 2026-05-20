#define AppName "HEPiC"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppPublisher "Zhengyang Liu"
#define AppExeName "HEPiC.exe"
#define SourceDir "dist\HEPiC"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer_output
OutputBaseFilename=HEPiC_v{#AppVersion}_Setup
SetupIconFile=assets\hepic.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; 安装完成后不自动启动（可改为 yes）
DisableFinishedPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional tasks:"; Flags: unchecked

[Files]
; 把 PyInstaller 打包输出的整个目录复制进去
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单快捷方式
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; 桌面快捷方式（仅在用户勾选时创建）
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; 安装完成后可选择立即启动
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
