import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social.social_signal import SocialSignalEngine


def main():
    parser = argparse.ArgumentParser(description="Manual social signal smoke test.")
    parser.add_argument(
        "--write-real-state",
        action="store_true",
        help="Write to data/social_state.json. Default uses a temporary state file.",
    )
    args = parser.parse_args()

    temp_dir = None
    if args.write_real_state:
        state_file = "data/social_state.json"
    else:
        temp_dir = TemporaryDirectory()
        state_file = str(Path(temp_dir.name) / "social_state.json")

    engine = SocialSignalEngine(state_file=state_file)

    print("\n==============================")
    print("MANUAL SOCIAL CATALYST TEST")
    print("==============================")
    if not args.write_real_state:
        print("Safe mode: writing to temporary state only.")
        print("Use --write-real-state to write data/social_state.json.")
    print("Example account: elonmusk")
    print("Example text: Grok is based and spicy today")
    print("")

    account = input("Account handle without @: ").strip()
    text = input("Post/tweet text: ").strip()
    url = input("Optional URL, press enter to skip: ").strip()

    if not account or not text:
        print("Account and text are required.")
        if temp_dir:
            temp_dir.cleanup()
        return

    signal = engine.add_signal(
        account=account,
        text=text,
        url=url or None,
    )

    print("\nSocial signal saved")
    print("Account:", signal["account"])
    print("Weight:", signal["weight"])
    print("Keywords:", signal["keywords"])
    print("Expires at:", signal["expires_at"])
    print("\nState file:", state_file)
    if temp_dir:
        temp_dir.cleanup()


if __name__ == "__main__":
    main()
