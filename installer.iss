; SmartClipboard Installer Script
; Built with Inno Setup 6

#define MyAppName "SmartClipboard"
#define MyAppVersion "5.0"
#define MyAppPublisher "SmartClipboard"
#define MyAppExeName "SmartClipboard.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
OutputDir=.
OutputBaseFilename=SmartClipboard_{#MyAppVersion}_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\SmartClipboard\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\SmartClipboard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifsilent

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;

  // 尝试关闭运行中的应用
  if Exec('taskkill.exe', '/F /IM SmartClipboard.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    // 给应用一点时间完全关闭
    Sleep(500);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // 再次确保应用已关闭
    Exec('taskkill.exe', '/F /IM SmartClipboard.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(500);
  end;
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
