; Instalador do Routrip. Gerado por scripts\make_installer.ps1, que passa a versão:
;   ISCC.exe /DAppVersion=1.0.0 installer\routrip.iss
;
; O resultado é um único Routrip-Setup-<versão>.exe, que é o arquivo publicado na
; release: instala o programa, cria os atalhos e registra o desinstalador em
; Painel de Controle > Programas e Recursos.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Routrip"
#define DistDir "..\backend\dist\Routrip"
; Runtime Evergreen do WebView2: presente nos Windows 10/11 atualizados, baixado só
; quando falta.
#define WebView2Guid "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
#define WebView2Url "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

[Setup]
; Identidade do programa para o Windows: é por ela que uma versão nova substitui a
; anterior em vez de aparecer duplicada em Programas e Recursos. Nunca mudar.
AppId={{6C1E2B7A-4F0D-4E7B-9A51-2D8C3F9E1A47}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Sem administrador por padrão (instala em %LocalAppData%\Programs); o diálogo oferece
; instalar para todos os usuários.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=Routrip-Setup-{#AppVersion}
SetupIconFile=..\backend\assets\icon.ico
UninstallDisplayIcon={app}\Routrip.exe
UninstallDisplayName={#AppName}
; Fecha o Routrip aberto antes de sobrescrever ou remover os arquivos.
CloseApplications=yes
WizardStyle=modern
; O pacote é quase todo a base do CNEFE e DLLs: LZMA2 sólido no nível máximo é o que
; mais encolhe o download. A descompressão continua rápida; só o build fica lento.
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
; Marcada por padrão; quem não quiser o atalho desmarca na tela de tarefas.
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Routrip.exe"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Routrip.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Routrip.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Instalado: Boolean;
var
  Versao: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}', 'pv', Versao) and (Versao <> '') and (Versao <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}', 'pv', Versao) and (Versao <> '') and (Versao <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  Result := '';
  if WebView2Instalado then
    Exit;
  try
    DownloadTemporaryFile('{#WebView2Url}', 'MicrosoftEdgeWebview2Setup.exe', '', nil);
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '',
                SW_HIDE, ewWaitUntilTerminated, Codigo) or (Codigo <> 0) then
      Result := 'Não foi possível instalar o Microsoft Edge WebView2 Runtime (código ' +
                IntToStr(Codigo) + '). Instale-o manualmente e rode este instalador de novo.';
  except
    Result := 'Não foi possível baixar o Microsoft Edge WebView2 Runtime. Verifique a ' +
              'conexão com a internet e tente de novo.';
  end;
end;
