using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class InstallerConfig
{
    internal const string Version = "v.10 (web)";
    internal const string RepoUrl = "__REPO_URL__";
    internal const string RepoSha256 = "__REPO_SHA256__";
}

internal sealed class InstallerForm : Form
{
    private readonly TextBox destination = new TextBox();
    private readonly Button browse = new Button();
    private readonly Button install = new Button();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly Label status = new Label();
    private readonly CheckBox desktopShortcut = new CheckBox();
    private readonly CheckBox runChecker = new CheckBox();
    private readonly CheckBox setupEnvironment = new CheckBox();

    internal InstallerForm()
    {
        Text = "CrystEngKit ORCA Setup " + InstallerConfig.Version;
        ClientSize = new Size(590, 270);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9F);

        var heading = new Label
        {
            Text = "Install CrystEngKit ORCA",
            Font = new Font("Segoe UI", 16F),
            AutoSize = true,
            Location = new Point(22, 18)
        };
        var description = new Label
        {
            Text = "Downloads the latest repository version, then installs it for this user.",
            AutoSize = true,
            Location = new Point(25, 57)
        };
        var destinationLabel = new Label
        {
            Text = "Install location:",
            AutoSize = true,
            Location = new Point(25, 91)
        };

        destination.Location = new Point(28, 113);
        destination.Size = new Size(455, 25);
        destination.Text = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs",
            "CrystEngKit_ORCA");

        browse.Text = "Browse...";
        browse.Location = new Point(492, 111);
        browse.Size = new Size(75, 28);
        browse.Click += BrowseClick;

        desktopShortcut.Text = "Create desktop shortcut";
        desktopShortcut.Checked = true;
        desktopShortcut.AutoSize = true;
        desktopShortcut.Location = new Point(28, 150);

        runChecker.Text = "Run installation checker when finished";
        runChecker.Checked = true;
        runChecker.AutoSize = true;
        runChecker.Location = new Point(225, 150);

        setupEnvironment.Text = "Create Python environment and install required packages";
        setupEnvironment.Checked = true;
        setupEnvironment.AutoSize = true;
        setupEnvironment.Location = new Point(28, 177);

        progress.Location = new Point(28, 207);
        progress.Size = new Size(455, 18);
        progress.Style = ProgressBarStyle.Marquee;
        progress.Visible = false;

        status.Text = "Ready.";
        status.AutoSize = true;
        status.Location = new Point(28, 235);

        install.Text = "Install";
        install.Location = new Point(492, 205);
        install.Size = new Size(75, 32);
        install.Click += InstallClick;

        Controls.AddRange(new Control[]
        {
            heading, description, destinationLabel, destination, browse, desktopShortcut,
            runChecker, setupEnvironment, progress, status, install
        });
    }

    private void BrowseClick(object sender, EventArgs e)
    {
        using (var dialog = new FolderBrowserDialog())
        {
            dialog.Description = "Choose the CrystEngKit ORCA installation folder";
            dialog.SelectedPath = destination.Text;
            if (dialog.ShowDialog(this) == DialogResult.OK)
                destination.Text = dialog.SelectedPath;
        }
    }

    private void InstallClick(object sender, EventArgs e)
    {
        var installDirectory = destination.Text.Trim();
        if (installDirectory.Length == 0)
        {
            MessageBox.Show(this, "Choose an installation folder.", Text,
                MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        SetBusy(true, "Downloading latest release...");
        var worker = new BackgroundWorker();
        worker.DoWork += delegate { InstallFiles(installDirectory); };
        worker.RunWorkerCompleted += delegate(object completedSender, RunWorkerCompletedEventArgs completed)
        {
            if (completed.Error != null)
            {
                SetBusy(false, "Installation failed.");
                MessageBox.Show(this, completed.Error.Message, Text,
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            try
            {
                CreateStartMenuShortcut(installDirectory);
                if (desktopShortcut.Checked)
                    CreateDesktopShortcut(installDirectory);
                if (runChecker.Checked)
                    StartChecker(installDirectory, setupEnvironment.Checked);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this,
                    "The files were installed, but a post-install step failed:\r\n\r\n" + ex.Message,
                    Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }

            progress.Visible = false;
            status.Text = "Installation complete.";
            install.Text = "Close";
            install.Enabled = true;
            install.Click -= InstallClick;
            install.Click += delegate { Close(); };
        };
        worker.RunWorkerAsync();
    }

    private void SetBusy(bool busy, string message)
    {
        destination.Enabled = !busy;
        browse.Enabled = !busy;
        install.Enabled = !busy;
        desktopShortcut.Enabled = !busy;
        runChecker.Enabled = !busy;
        setupEnvironment.Enabled = !busy;
        progress.Visible = busy;
        status.Text = message;
    }

    private static void InstallFiles(string installDirectory)
    {
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        var tempRoot = Path.Combine(Path.GetTempPath(), "CrystEngKit_ORCA_" + Guid.NewGuid().ToString("N"));
        var zipPath = Path.Combine(tempRoot, "repository.zip");

        try
        {
            Directory.CreateDirectory(tempRoot);
            using (var client = new WebClient())
                client.DownloadFile(InstallerConfig.RepoUrl, zipPath);

            if (!String.IsNullOrWhiteSpace(InstallerConfig.RepoSha256))
            {
                var actualHash = GetSha256(zipPath);
                if (!actualHash.Equals(InstallerConfig.RepoSha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException(
                        "The downloaded repository checksum did not match. Installation was stopped.");
            }

            Directory.CreateDirectory(installDirectory);
            ExtractRepositoryToInstall(zipPath, installDirectory);
            EnsureWindowsLaunchers(installDirectory);
            CreateUninstaller(installDirectory);
            RegisterUninstallEntry(installDirectory);
        }
        finally
        {
            try { if (Directory.Exists(tempRoot)) Directory.Delete(tempRoot, true); }
            catch { }
        }
    }

    private static string GetSha256(string file)
    {
        using (var stream = File.OpenRead(file))
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "");
    }

    private static void ExtractRepositoryToInstall(string archivePath, string destination)
    {
        var destinationRoot = Path.GetFullPath(destination + Path.DirectorySeparatorChar);
        string archiveRoot = null;

        using (var archive = ZipFile.OpenRead(archivePath))
        {
            foreach (var entry in archive.Entries)
            {
                var entryName = entry.FullName.Replace('\\', '/');
                var separator = entryName.IndexOf('/');
                if (separator < 0)
                    throw new InvalidOperationException("The repository archive had an unexpected structure.");

                var currentRoot = entryName.Substring(0, separator);
                if (String.IsNullOrEmpty(archiveRoot))
                    archiveRoot = currentRoot;
                else if (!archiveRoot.Equals(currentRoot, StringComparison.Ordinal))
                    throw new InvalidOperationException("The repository archive had an unexpected structure.");

                var relativeName = entryName.Substring(separator + 1);
                if (relativeName.Length == 0)
                    continue;
                if (ShouldSkipRepositoryEntry(relativeName))
                    continue;

                var output = Path.GetFullPath(Path.Combine(destination, relativeName));
                if (!output.StartsWith(destinationRoot, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Unsafe path found in repository archive.");

                if (entryName.EndsWith("/", StringComparison.Ordinal))
                {
                    Directory.CreateDirectory(output);
                    continue;
                }

                var parent = Path.GetDirectoryName(output);
                if (!String.IsNullOrEmpty(parent))
                    Directory.CreateDirectory(parent);
                entry.ExtractToFile(output, true);
            }
        }

        if (String.IsNullOrEmpty(archiveRoot))
            throw new InvalidOperationException("The repository archive was empty.");
    }

    private static bool ShouldSkipRepositoryEntry(string relativeName)
    {
        var normalized = relativeName.Replace('\\', '/');
        return normalized.StartsWith("install/releases/", StringComparison.OrdinalIgnoreCase);
    }

    private static void CreateDesktopShortcut(string installDirectory)
    {
        var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        CreateShortcut(Path.Combine(desktop, "ORCA Input Builder.lnk"), installDirectory);
        CreateShortcut(Path.Combine(desktop, "CrystEngKit ORCA.lnk"), installDirectory);
    }

    private static void CreateStartMenuShortcut(string installDirectory)
    {
        var menu = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Programs), "CrystEngKit ORCA");
        Directory.CreateDirectory(menu);
        CreateShortcut(Path.Combine(menu, "ORCA Input Builder.lnk"), installDirectory);
        CreateShortcut(
            Path.Combine(menu, "Uninstall CrystEngKit ORCA.lnk"),
            installDirectory,
            "uninstall.cmd");
    }

    private static void CreateShortcut(string shortcutPath, string installDirectory, string targetFile = "launch_orca_builder.cmd")
    {
        var launcher = Path.Combine(installDirectory, targetFile);
        if (!File.Exists(launcher))
            throw new FileNotFoundException("The shortcut target was not found.", launcher);
        var shellType = Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell = Activator.CreateInstance(shellType);
        dynamic shortcut = shell.CreateShortcut(shortcutPath);
        shortcut.TargetPath = launcher;
        shortcut.WorkingDirectory = installDirectory;
        var icon = Path.Combine(installDirectory, "tools", "images", "orca_builder.ico");
        if (File.Exists(icon))
            shortcut.IconLocation = icon;
        shortcut.Save();
    }

    private static void StartChecker(string installDirectory, bool setupEnvironment)
    {
        var checker = Path.Combine(installDirectory, "run_install_checker.cmd");
        if (!File.Exists(checker))
            throw new FileNotFoundException("The installation checker launcher was not found.", checker);
        var arguments = setupEnvironment ? "--setup-venv" : "";
        Process.Start(new ProcessStartInfo(checker, arguments)
        {
            WorkingDirectory = installDirectory,
            UseShellExecute = true
        });
    }

    private static void EnsureWindowsLaunchers(string installDirectory)
    {
        var sourceDirectory = Path.Combine(installDirectory, "packaging", "windows");
        CopyLauncherIfNeeded(sourceDirectory, installDirectory, "launch_orca_builder.cmd");
        CopyLauncherIfNeeded(sourceDirectory, installDirectory, "run_install_checker.cmd");
    }

    private static void CopyLauncherIfNeeded(string sourceDirectory, string installDirectory, string fileName)
    {
        var destination = Path.Combine(installDirectory, fileName);
        if (File.Exists(destination))
            return;

        var source = Path.Combine(sourceDirectory, fileName);
        if (!File.Exists(source))
            throw new FileNotFoundException("The web installer could not find a required launcher script in the downloaded repository.", source);

        File.Copy(source, destination, true);
    }

    private static void CreateUninstaller(string installDirectory)
    {
        var uninstallPath = Path.Combine(installDirectory, "uninstall.cmd");
        var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        var menu = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Programs), "CrystEngKit ORCA");

        var lines = new[]
        {
            "@echo off",
            "setlocal",
            "echo This will remove CrystEngKit ORCA from:",
            "echo " + installDirectory,
            "echo.",
            "choice /C YN /M \"Uninstall CrystEngKit ORCA\"",
            "if errorlevel 2 exit /b 0",
            "del /f /q \"" + Path.Combine(desktop, "ORCA Input Builder.lnk") + "\" >nul 2>nul",
            "del /f /q \"" + Path.Combine(desktop, "CrystEngKit ORCA.lnk") + "\" >nul 2>nul",
            "rmdir /s /q \"" + menu + "\" >nul 2>nul",
            "reg delete HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\CrystEngKit_ORCA /f >nul 2>nul",
            "echo Removing files...",
            "cd /d \"%TEMP%\"",
            "set \"REMOVE_DIR=" + installDirectory + "\"",
            "set \"CLEANUP=%TEMP%\\crystengkit_orca_uninstall_%RANDOM%%RANDOM%.cmd\"",
            "> \"%CLEANUP%\" echo @echo off",
            ">> \"%CLEANUP%\" echo timeout /t 2 /nobreak ^>nul",
            ">> \"%CLEANUP%\" echo rmdir /s /q \"%REMOVE_DIR%\"",
            "start \"\" \"%CLEANUP%\"",
            "exit /b 0",
        };
        File.WriteAllLines(uninstallPath, lines);
    }

    private static void RegisterUninstallEntry(string installDirectory)
    {
        var uninstallPath = Path.Combine(installDirectory, "uninstall.cmd");
        using (var key = Registry.CurrentUser.CreateSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CrystEngKit_ORCA"))
        {
            if (key == null)
                return;
            key.SetValue("DisplayName", "CrystEngKit ORCA");
            key.SetValue("DisplayVersion", InstallerConfig.Version);
            key.SetValue("Publisher", "Yury Torubaev");
            key.SetValue("InstallLocation", installDirectory);
            key.SetValue("DisplayIcon", Path.Combine(installDirectory, "tools", "images", "orca_builder.ico"));
            key.SetValue("UninstallString", "\"" + uninstallPath + "\"");
            key.SetValue("QuietUninstallString", "\"" + uninstallPath + "\"");
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        }
    }
}

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0].Equals("/probe", StringComparison.OrdinalIgnoreCase))
            return 0;

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new InstallerForm());
        return 0;
    }
}
