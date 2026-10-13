"""python scripts/analyze.py  ->  persona tables, significance tests, charts in results/"""
import _path  # noqa: F401
from traffix.evaluation import analysis

if __name__ == "__main__":
    analysis.run()
