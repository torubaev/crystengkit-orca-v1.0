using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class InstallerConfig
{
    internal const string Version = "__APP_VERSION__";
    internal const string PackageUrl = "__PACKAGE_URL__";
    internal const string PackageSha256 = "__PACKAGE_SHA256__";
}

internal sealed class BootstrapperForm : Form
{
    private readonly Button start = new Button();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly Label status = new Label();
    private readonly bool existingInstallation;

    internal BootstrapperForm()
    {
        existingInstallation = FindExistingInstallation() != null;
        Text = "CrystEngKit ORCA Setup " + InstallerConfig.Version;
        ClientSize = new Size(590, 230);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9F);

        var heading = new Label
        {
            Text = existingInstallation ? "Update CrystEngKit ORCA" : "Install CrystEngKit ORCA",
            Font = new Font("Segoe UI", 16F),
            AutoSize = true,
            Location = new Point(22, 20)
        };
        var description = new Label
        {
            Text = existingInstallation
                ? "A matching installation was found. The verified installer will update it in place."
                : "No matching installation was found. The verified installer will create a new installation.",
            AutoSize = false,
            Size = new Size(540, 42),
            Location = new Point(25, 62)
        };
        var preservation = new Label
        {
            Text = "Projects and user settings are preserved. The managed Python environment is checked only for missing requirements.",
            AutoSize = false,
            Size = new Size(540, 40),
            Location = new Point(25, 101)
        };

        progress.Location = new Point(28, 151);
        progress.Size = new Size(455, 18);
        progress.Style = ProgressBarStyle.Marquee;
        progress.Visible = false;

        status.Text = "Ready to download the signed/versioned installer.";
        status.AutoSize = true;
        status.Location = new Point(28, 188);

        start.Text = existingInstallation ? "Update" : "Install";
        start.Location = new Point(492, 146);
        start.Size = new Size(75, 32);
        start.Click += StartClick;

        Controls.AddRange(new Control[] { heading, description, preservation, progress, status, start });
    }

    private void StartClick(object sender, EventArgs e)
    {
        start.Enabled = false;
        progress.Visible = true;
        status.Text = "Downloading and verifying the full installer...";
        var worker = new BackgroundWorker();
        worker.DoWork += delegate(object workSender, DoWorkEventArgs work)
        {
            work.Result = DownloadVerifiedPackage();
        };
        worker.RunWorkerCompleted += delegate(object completedSender, RunWorkerCompletedEventArgs completed)
        {
            if (completed.Error != null)
            {
                progress.Visible = false;
                start.Enabled = true;
                status.Text = "Download failed.";
                MessageBox.Show(this, completed.Error.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            try
            {
                var package = (string)completed.Result;
                Process.Start(new ProcessStartInfo(package) { UseShellExecute = true });
                Close();
            }
            catch (Exception ex)
            {
                progress.Visible = false;
                start.Enabled = true;
                status.Text = "Could not start the full installer.";
                MessageBox.Show(this, ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        };
        worker.RunWorkerAsync();
    }

    private static string DownloadVerifiedPackage()
    {
        if (!InstallerConfig.PackageUrl.StartsWith("https://github.com/", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("The embedded installer URL is invalid.");
        if (InstallerConfig.PackageSha256.Length != 64)
            throw new InvalidOperationException("The embedded installer checksum is invalid.");

        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        var directory = Path.Combine(Path.GetTempPath(), "CrystEngKit-ORCA", InstallerConfig.Version);
        Directory.CreateDirectory(directory);
        var package = Path.Combine(directory, "CrystEngKit-ORCA-Setup-" + InstallerConfig.Version + ".exe");
        using (var client = new WebClient())
            client.DownloadFile(InstallerConfig.PackageUrl, package);
        var actual = GetSha256(package);
        if (!actual.Equals(InstallerConfig.PackageSha256, StringComparison.OrdinalIgnoreCase))
        {
            try { File.Delete(package); } catch { }
            throw new InvalidOperationException("The downloaded installer failed SHA-256 verification and was removed.");
        }
        return package;
    }

    private static string GetSha256(string file)
    {
        using (var stream = File.OpenRead(file))
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }

    private static string FindExistingInstallation()
    {
        var subkeys = new[]
        {
            @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CrystEngKit_ORCA",
            @"Software\Microsoft\Windows\CurrentVersion\Uninstall\{7E5ED58D-6A52-4A90-9CE5-C95806F8ED2D}_is1"
        };
        foreach (var hive in new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine })
        foreach (var view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
        foreach (var subkey in subkeys)
        {
            try
            {
                using (var baseKey = RegistryKey.OpenBaseKey(hive, view))
                using (var key = baseKey.OpenSubKey(subkey))
                {
                    var path = key == null ? null :
                        ((key.GetValue("InstallLocation") as string) ?? (key.GetValue("AppPath") as string));
                    if (!String.IsNullOrWhiteSpace(path) && Directory.Exists(path))
                        return path;
                }
            }
            catch { }
        }
        return null;
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
        Application.Run(new BootstrapperForm());
        return 0;
    }
}
