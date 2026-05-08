import pathlib
import py_compile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "develop" / "upbit_develop_library.py"


class SyntaxCheckTest(unittest.TestCase):
    def test_upbit_develop_library_has_valid_python_syntax(self):
        py_compile.compile(str(MODULE_PATH), doraise=True)


if __name__ == "__main__":
    unittest.main()
