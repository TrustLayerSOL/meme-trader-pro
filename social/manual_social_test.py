from social.social_signal import SocialSignalEngine


def main():
    engine = SocialSignalEngine()

    print("\n==============================")
    print("🧪 MANUAL SOCIAL CATALYST TEST")
    print("==============================")
    print("Example account: elonmusk")
    print("Example text: Grok is based and spicy today")
    print("")

    account = input("Account handle without @: ").strip()
    text = input("Post/tweet text: ").strip()
    url = input("Optional URL, press enter to skip: ").strip()

    if not account or not text:
        print("❌ Account and text are required.")
        return

    signal = engine.add_signal(
        account=account,
        text=text,
        url=url or None,
    )

    print("\n✅ Social signal saved")
    print("Account:", signal["account"])
    print("Weight:", signal["weight"])
    print("Keywords:", signal["keywords"])
    print("Expires at:", signal["expires_at"])
    print("\nCheck data/social_state.json")


if __name__ == "__main__":
    main()