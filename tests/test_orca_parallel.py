import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from shared.orca_parallel import add_mpi_to_path, default_orca_nprocs, find_mpi_launcher


class OrcaParallelTests(unittest.TestCase):
    @patch("shared.orca_parallel.shutil.which", return_value=r"C:\MPI\mpiexec.exe")
    def test_parallel_default_when_launcher_is_on_path(self, _which):
        self.assertEqual(find_mpi_launcher(), r"C:\MPI\mpiexec.exe")
        self.assertEqual(default_orca_nprocs(), 4)

    @patch("shared.orca_parallel.Path.is_file", return_value=False)
    @patch("shared.orca_parallel.shutil.which", return_value=None)
    def test_serial_default_without_launcher(self, _which, _is_file):
        with patch("shared.orca_parallel.os.name", "nt"):
            self.assertEqual(find_mpi_launcher(), "")
            self.assertEqual(default_orca_nprocs(), 1)

    @patch("shared.orca_parallel.find_mpi_launcher", return_value=r"C:\MPI\Bin\mpiexec.exe")
    def test_detected_launcher_directory_is_added_to_subprocess_path(self, _find):
        environment = add_mpi_to_path({"PATH": r"C:\ORCA"})
        self.assertEqual(environment["PATH"].split(os.pathsep)[-1], r"C:\MPI\Bin")


if __name__ == "__main__":
    unittest.main()
