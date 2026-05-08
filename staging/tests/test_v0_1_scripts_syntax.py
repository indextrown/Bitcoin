import pathlib
import py_compile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT_DIR / "operate" / "v0-1" / "strategy_v0_1.py",
    ROOT_DIR / "operate" / "v0-1" / "v0_1_bot.py",
]


class V01ScriptsSyntaxTest(unittest.TestCase):
    def test_v0_1_scripts_have_valid_python_syntax(self):
        for path in TARGETS:
            with self.subTest(path=path.name):
                py_compile.compile(str(path), doraise=True)


if __name__ == "__main__":
    unittest.main()
