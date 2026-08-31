"""What a deployment has actually kept.

    python -m tools.store                    # a summary
    python -m tools.store --signatures       # who signed what
    python -m tools.store --thread DEMO-x    # replay one encounter, step by step
    python -m tools.store --reset            # destroy all of it and start clean

The point of a durable checkpoint is that somebody can ask, later and from
outside the process, what the system saw when it produced an output. This is
that question, asked from outside the process — against Postgres or against the
files, whichever the deployment is using. It should not be possible to tell
which from the answers.
"""

from __future__ import annotations

import argparse
import sys

from service.store import Store


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the durable store.")
    parser.add_argument("--dir", default=None)
    parser.add_argument("--thread", help="replay one encounter step by step")
    parser.add_argument("--signatures", action="store_true")
    parser.add_argument("--reset", action="store_true",
                        help="destroy every checkpoint, signature and queued item")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt (for scripts)")
    args = parser.parse_args()

    store = Store(args.dir)
    if args.reset:
        return _reset(store, assume_yes=args.yes)

    facts = store.summary()
    if store.backend == "files" and not store.dir.exists():
        print(f"\n  Nothing stored yet at {store.dir}/.")
        print("  Run `make`. The clinician surface persists every encounter.\n")
        return 0

    print(f"\n  {facts['backend']}  {facts['location']}")
    print("  " + "-" * 52)
    print(f"  encounters checkpointed   {facts['encounters_checkpointed']}")
    print(f"  signatures on record      {facts['signatures']}")
    print(f"  queued for submission     {facts['queued']}")
    print(f"  already sent              {facts['sent']}")
    if facts["damaged_lines"]:
        print(f"  unreadable log lines      {facts['damaged_lines']}  "
              "(kept visible rather than dropped)")

    if args.signatures:
        print("\n  Signatures")
        for record in store.audit_log().records:
            print(f"    {record.signed_at}  {record.practitioner_id} ({record.role})"
                  f"  {record.decision}")
            print(f"      signed a draft from {' | '.join(record.proposal_provenance)}")

    if args.thread:
        runtime = store.runtime()
        if args.thread not in runtime.threads():
            print(f"\n  No encounter {args.thread!r}. Known: "
                  f"{', '.join(runtime.threads()[:8]) or 'none'}\n")
            return 2
        print(f"\n  Replay of {args.thread}: what the system saw, in order")
        for index in range(len(runtime.checkpoints[args.thread])):
            checkpoint = runtime.replay(args.thread, index)
            keys = sorted(checkpoint.state)[:6] if isinstance(checkpoint.state, dict) else []
            print(f"    [{checkpoint.sequence}] {checkpoint.step:<12} "
                  f"{'fields: ' + ', '.join(keys) if keys else ''}")
    elif not args.signatures:
        threads = store.runtime().threads()
        if threads:
            print(f"\n  Encounters: {', '.join(threads[:10])}"
                  f"{' …' if len(threads) > 10 else ''}")
            print(f"  Replay one:  python -m tools.store --thread {threads[0]}")
    print()
    return 0


def _reset(store, *, assume_yes: bool) -> int:
    """Wipe the store, after saying plainly what that means.

    It asks first, and the prompt names the backend and the counts, because
    "start afresh" and "delete the signatures a licensed doctor put their name
    to" are the same keystroke here and only one of them is what anybody wants
    to have typed by accident.

    This is not what /clinic's "Clear this list" does. That writes a marker
    forward and destroys nothing, which is the behaviour the product has. This
    is the operator's hammer, for a prototype store full of synthetic demo runs.
    """
    facts = store.summary()
    total = (facts["encounters_checkpointed"] + facts["signatures"]
             + facts["queued"] + facts["sent"])
    if total == 0:
        print(f"\n  Nothing stored in {facts['backend']} ({facts['location']}). "
              "Already clean.\n")
        return 0

    print(f"\n  About to destroy everything in {facts['backend']} "
          f"({facts['location']}):")
    print(f"    {facts['encounters_checkpointed']} encounter(s) checkpointed")
    print(f"    {facts['signatures']} signature(s) on record")
    print(f"    {facts['queued'] + facts['sent']} outbound item(s)")
    print("\n  Signatures are the record of who took clinical responsibility for a")
    print("  draft. In a real deployment destroying them would be unlawful; this")
    print("  exists because a prototype store fills with synthetic demo runs.")

    if not assume_yes:
        try:
            if input("\n  Type 'yes' to continue: ").strip().lower() != "yes":
                print("  Nothing was destroyed.\n")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\n  Nothing was destroyed.\n")
            return 1

    destroyed = store.reset()
    print(f"\n  Destroyed: {destroyed['checkpoints']} checkpoint(s), "
          f"{destroyed['signatures']} signature(s), {destroyed['outbound']} outbound item(s).")
    print("  The next `make` will run everything fresh.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
