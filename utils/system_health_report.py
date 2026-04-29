import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.system_health import SystemHealth


def main():
    report = SystemHealth().report()

    print("SYSTEM READINESS:", report["overall"])
    print("OK:", report["counts"]["OK"])
    print("WARN:", report["counts"]["WARN"])
    print("FAIL:", report["counts"]["FAIL"])
    print()

    for row in report["rows"]:
        print(f"{row['status']:4} {row['check']}: {row['detail']}")


if __name__ == "__main__":
    main()
