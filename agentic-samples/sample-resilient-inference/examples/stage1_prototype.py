"""Stage 1: run the ticket agent through one bounded Amazon Bedrock route."""

from dataclasses import asdict
import json

from reliable_inference import draft_reply


def main() -> None:
    draft = draft_reply(
        "Where is order #10042?",
        "Order #10042 shipped on 4 August. Tracking ID ZX-1942.",
    )
    print(draft.text)
    print(json.dumps(asdict(draft), indent=2))


if __name__ == "__main__":
    main()
