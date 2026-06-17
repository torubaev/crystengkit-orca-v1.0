; Inno Setup script for a small web installer.
;
; Build with Inno Setup Compiler:
;   ISCC.exe packaging\windows\CrystEngKit_ORCA_Web.iss
;
; This installer downloads the repository ZIP during installation. Keep
; CrystEngKit_ORCA.iss as the offline/self-contained installer.

#define MyAppName "CrystEngKit ORCA"
#define MyAppVersion "1.0"
#define MyAppPublisher "CrystEngKit"
#define MyAppURL "https://github.com/torubaev/crystengkit-orca-v1.0"
#define MyRepoZipURL "https://github.com/torubaev/crystengkit-orca-v1.0/archive/refs/heads/main.zip"

[Setup]
AppId={{7E5ED58D-6A52-4A90-9CE5-C95806F8ED2D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\CrystEngKit ORCA
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist\installer
OutputBaseFilename=CrystEngKit-ORCA-WebSetup-{#MyAppVersion}
SetupIconFile=..\..\tools\images\orca_builder.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UseSetupLdr=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\tools\images\orca_builder.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "runchecker"; Description: "Run installation checker after repository download"; GroupDescription: "Post-install checks:"; Flags: checkedonce
Name: "installpython"; Description: "Install Python 3.12 with winget if Python 3.9+ is not found"; GroupDescription: "Python setup:"; Flags: unchecked
Name: "setupvenv"; Description: "Create a local Python environment for CrystEngKit and install required packages"; GroupDescription: "Python setup:"; Flags: checkedonce

[Files]
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\tools\images\orca_builder.ico"; DestDir: "{app}\tools\images"; Flags: ignoreversion
Source: "download_repo.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch_orca_builder.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "run_install_checker.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ORCA Input Builder"; Filename: "{app}\launch_orca_builder.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\tools\images\orca_builder.ico"
Name: "{group}\Installation Checker"; Filename: "{app}\run_install_checker.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\tools\images\orca_builder.ico"
Name: "{group}\Documentation"; Filename: "{app}\README.md"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ORCA Input Builder"; Filename: "{app}\launch_orca_builder.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\tools\images\orca_builder.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\download_repo.cmd"; Parameters: """{#MyRepoZipURL}"""; Description: "Download CrystEngKit ORCA repository"
Filename: "{app}\run_install_checker.cmd"; Parameters: "{code:GetCheckerParams}"; Description: "Run installation checker"; Flags: postinstall skipifsilent nowait; Tasks: runchecker

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\benchmark_sets"
Type: filesandordirs; Name: "{app}\docs"
Type: filesandordirs; Name: "{app}\examples"
Type: filesandordirs; Name: "{app}\images"
Type: filesandordirs; Name: "{app}\install"
Type: filesandordirs; Name: "{app}\packaging"
Type: filesandordirs; Name: "{app}\S22_NCI_benchmark_set"
Type: filesandordirs; Name: "{app}\tools"
Type: files; Name: "{app}\index.html"
Type: files; Name: "{app}\README.md"
Type: files; Name: "{app}\LICENSE"
Type: files; Name: "{app}\installation_report.html"

[Code]
function GetCheckerParams(Param: String): String;
begin
  Result := '';
  if WizardIsTaskSelected('installpython') then
    Result := Result + ' --install-python-if-missing';
  if WizardIsTaskSelected('setupvenv') then
    Result := Result + ' --setup-venv';
end;
