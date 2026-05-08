import pathlib
import py_compile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT_DIR / "operate" / "v2" / "strategy_v2.py",
    ROOT_DIR / "operate" / "v2" / "v2_bot.py",
    ROOT_DIR / "operate" / "v2" / "strategy_v2_visualizer.py",
    ROOT_DIR / "operate" / "backtest_v1_v2.py",
]


class V2ScriptsSyntaxTest(unittest.TestCase):
    def test_v2_related_scripts_have_valid_python_syntax(self):
        for path in TARGETS:
            with self.subTest(path=path.name):
                py_compile.compile(str(path), doraise=True)


if __name__ == "__main__":
    unittest.main()
