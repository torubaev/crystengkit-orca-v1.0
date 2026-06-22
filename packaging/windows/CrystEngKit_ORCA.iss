; Full offline Windows installer for CrystEngKit ORCA.
; All project files are embedded. No network download is performed by Setup.

#define MyAppName "CrystEngKit ORCA"
#define MyAppVersion "1.0.2"
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
DefaultDirName={autopf}\CrystEngKit ORCA
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\install\releases
OutputBaseFilename=CrystEngKit-ORCA-Setup-1.0
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
Name: "runchecker"; Description: "Run installation checker after setup"; GroupDescription: "Post-install checks:"; Flags: checkedonce
Name: "installpython"; Description: "Install Python 3.12 with winget if Python 3.9+ is not found"; GroupDescription: "Python setup:"; Flags: unchecked
Name: "setupvenv"; Description: "Create a local Python environment and install required packages"; GroupDescription: "Python setup:"; Flags: checkedonce

[Files]
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\index.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,*.pyo"
Source: "..\..\images\*"; DestDir: "{app}\images"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\install\*"; DestDir: "{app}\install"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "releases\*,__pycache__\*,*.pyc,*.pyo"
Source: "..\..\tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,*.pyo,*.log"
Source: "..\..\benchmark_sets\*"; DestDir: "{app}\benchmark_sets"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "..\..\S22_NCI_benchmark_set\*"; DestDir: "{app}\S22_NCI_benchmark_set"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "launch_orca_builder.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "run_install_checker.cmd"; DestDir: "{app}"; Flags: ignoreversion

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
