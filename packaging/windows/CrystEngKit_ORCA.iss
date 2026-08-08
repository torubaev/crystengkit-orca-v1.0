; Full offline Windows installer for CrystEngKit ORCA.
; All project files are embedded. No network download is performed by Setup.

#define MyAppName "CrystEngKit ORCA"
#ifndef MyAppVersion
  #error MyAppVersion must be supplied by build_installer.ps1
#endif
#ifndef SourceRoot
  #error SourceRoot must be supplied by build_installer.ps1
#endif
#define MyAppPublisher "CrystEngKit"
#define MyAppURL "https://github.com/torubaev/crystengkit-orca-v1.0"

[Setup]
AppId={{7E5ED58D-6A52-4A90-9CE5-C95806F8ED2D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Keep the application in a user-writable location. CrystEngKit creates its
; managed .venv, checker report, and local settings beside the installed tools.
; This matches the proven installation model used by the original web setup.
DefaultDirName={localappdata}\Programs\CrystEngKit_ORCA
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile={#SourceRoot}\LICENSE
OutputDir=..\..\install\releases
OutputBaseFilename=CrystEngKit-ORCA-Setup-{#MyAppVersion}
SetupIconFile={#SourceRoot}\tools\images\orca_builder.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UseSetupLdr=x64
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\tools\images\orca_builder.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "runchecker"; Description: "Run installation checker after setup"; GroupDescription: "Post-install checks:"; Flags: checkedonce
Name: "installpython"; Description: "Install Python 3.12 with winget if Python 3.9+ is not found"; GroupDescription: "Python setup:"; Flags: unchecked
Name: "setupvenv"; Description: "Create a local Python environment and install required packages"; GroupDescription: "Python setup:"; Flags: checkedonce

[Files]
Source: "{#SourceRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\index.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\crystengkit_v1.0_1.png"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceRoot}\app_metadata\*"; DestDir: "{app}\app_metadata"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,*.pyo"
Source: "{#SourceRoot}\images\*"; DestDir: "{app}\images"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\install\*"; DestDir: "{app}\install"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "releases\*,__pycache__\*,*.pyc,*.pyo"
Source: "{#SourceRoot}\tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,*.pyo,*.log,*_settings.json,orca_gaussian_builder_settings.json"
Source: "{#SourceRoot}\benchmark_sets\*"; DestDir: "{app}\benchmark_sets"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#SourceRoot}\S22_NCI_benchmark_set\*"; DestDir: "{app}\S22_NCI_benchmark_set"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#SourceRoot}\packaging\windows\launch_orca_builder.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\packaging\windows\run_install_checker.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ORCA Input Builder"; Filename: "{app}\launch_orca_builder.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\tools\images\orca_builder.ico"
Name: "{group}\Installation Checker"; Filename: "{app}\run_install_checker.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\tools\images\orca_builder.ico"
Name: "{group}\Documentation"; Filename: "{app}\README.md"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ORCA Input Builder"; Filename: "{app}\launch_orca_builder.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\tools\images\orca_builder.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\run_install_checker.cmd"; Parameters: "{code:GetCheckerParams}"; Description: "Run installation checker"; Flags: postinstall skipifsilent nowait; Tasks: runchecker

[Code]
function GetCheckerParams(Param: String): String;
begin
  Result := '';
  if WizardIsTaskSelected('installpython') then
    Result := Result + ' --install-python-if-missing';
  if WizardIsTaskSelected('setupvenv') then
    Result := Result + ' --setup-venv';
end;
