using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Windows.Forms;

internal static class InstallerConfig
{
    internal const string Version = "1.0.2";
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
            Text = "Downloads and verifies the selected repository release, then installs it for this user.",
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
            "CrystEngKit ORCA");

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

        SetBusy(true, "Downloading verified release...");
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
        var extractDirectory = Path.Combine(tempRoot, "extract");

        try
        {
            Directory.CreateDirectory(tempRoot);
            Directory.CreateDirectory(extractDirectory);
            using (var client = new WebClient())
                client.DownloadFile(InstallerConfig.RepoUrl, zipPath);

            var actualHash = GetSha256(zipPath);
            if (!actualHash.Equals(InstallerConfig.RepoSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException(
                    "The downloaded repository checksum did not match. Installation was stopped.");

            ExtractSafely(zipPath, extractDirectory);
            var roots = Directory.GetDirectories(extractDirectory);
            if (roots.Length != 1)
                throw new InvalidOperationException("The repository archive had an unexpected structure.");

            Directory.CreateDirectory(installDirectory);
            CopyDirectory(roots[0], installDirectory);
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

    private static void ExtractSafely(string archivePath, string destination)
    {
        var destinationRoot = Path.GetFullPath(destination + Path.DirectorySeparatorChar);
        using (var archive = ZipFile.OpenRead(archivePath))
        {
            foreach (var entry in archive.Entries)
            {
                var output = Path.GetFullPath(Path.Combine(destination, entry.FullName));
                if (!output.StartsWith(destinationRoot, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Unsafe path found in repository archive.");

                if (entry.FullName.EndsWith("/", StringComparison.Ordinal) ||
                    entry.FullName.EndsWith("\\", StringComparison.Ordinal))
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
    }

    private static void CopyDirectory(string source, string destination)
    {
        foreach (var directory in Directory.GetDirectories(source, "*", SearchOption.AllDirectories))
            Directory.CreateDirectory(directory.Replace(source, destination));
        foreach (var file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
            File.Copy(file, file.Replace(source, destination), true);
        foreach (var file in Directory.GetFiles(source, "*", SearchOption.TopDirectoryOnly))
            File.Copy(file, Path.Combine(destination, Path.GetFileName(file)), true);
    }

    private static void CreateDesktopShortcut(string installDirectory)
    {
        CreateShortcut(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                "CrystEngKit ORCA.lnk"),
            installDirectory);
    }

    private static void CreateStartMenuShortcut(string installDirectory)
    {
        var menu = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Programs), "CrystEngKit ORCA");
        Directory.CreateDirectory(menu);
        CreateShortcut(Path.Combine(menu, "ORCA Input Builder.lnk"), installDirectory);
    }

    private static void CreateShortcut(string shortcutPath, string installDirectory)
    {
        var shellType = Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell = Activator.CreateInstance(shellType);
        dynamic shortcut = shell.CreateShortcut(shortcutPath);
        shortcut.TargetPath = Path.Combine(installDirectory, "launch_orca_builder.cmd");
        shortcut.WorkingDirectory = installDirectory;
        var icon = Path.Combine(installDirectory, "tools", "images", "orca_builder.ico");
        if (File.Exists(icon))
            shortcut.IconLocation = icon;
        shortcut.Save();
    }

    private static void StartChecker(string installDirectory, bool setupEnvironment)
    {
        var checker = Path.Combine(installDirectory, "run_install_checker.cmd");
        var arguments = setupEnvironment ? "--setup-venv" : "";
        Process.Start(new ProcessStartInfo(checker, arguments)
        {
            WorkingDirectory = installDirectory,
            UseShellExecute = true
        });
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
