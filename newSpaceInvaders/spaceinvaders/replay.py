"""Deterministic record/replay — the desync-detection primitive.

The simulation is fully determined by ``(seed, cfg, input_log)``: same seed
feeds the same RNG draws, same ``cfg`` fixes every tuning constant, and the
same per-tick inputs drive :meth:`~spaceinvaders.world.GameWorld.step`
identically every time (see :mod:`spaceinvaders.world`). This module makes
that property machine-checkable instead of merely asserted in a docstring —
:class:`RoundRecord` captures everything needed to reproduce a round, and
:func:`replay` reproduces it.

The point is two-fold: an authoritative :class:`~spaceinvaders.server.Room`
can hand its ``input_log`` here to catch a client that silently diverged
(replay locally, compare :func:`state_hash` against what was broadcast), and
this same machinery gives the test suite bit-exact reproducibility for free.

``RoundRecord.input_log`` deliberately mirrors ``Room.input_log`` byte-for-byte
(``[(tick, {pid: [intent_name, ...]})]``, one entry per tick, with only the
*pids* holding a non-empty intent set present in that tick's dict) so a live
``Room``'s log can be handed to :func:`replay` with no conversion.
Everything here is JSON only — never ``pickle`` (see
:mod:`spaceinvaders.protocol` for why that matters in this project).
"""
import argparse
import dataclasses
import hashlib
import json
import random
from dataclasses import dataclass, field

from .config import Config
from .input import Intent, encode_inputs
from .world import GameState, GameWorld


@dataclass
class RoundRecord:
    """Everything required to reproduce one round bit-for-bit.

    ``ticks`` is the total number of ``world.step`` calls made, independent of
    ``input_log`` — a round with no player input at all still has ``ticks``
    ticks of enemy movement/RNG-driven firing to replay, but would otherwise
    leave an empty log with no way to know how far to step.

    ``active_pids`` is the set of participant slots to reconstruct the world
    with (passed straight to :class:`~spaceinvaders.world.GameWorld`) — a
    server ``Room`` sizes its world from *capacity* (``max_players``), not
    headcount, so a room with unfilled slots must record which pids were
    actually playing or the replay would reconstruct every slot as active and
    diverge immediately. ``None`` (the default, and what
    :func:`record_headless` produces) means every slot is active.
    """
    seed: int
    cfg: dict
    num_players: int
    dt: float
    ticks: int
    input_log: list = field(default_factory=list)
    active_pids: list = None
    final_hash: str = None


def record_headless(cfg: Config, seed: int, num_players: int, dt: float,
                    steps: int, inputs_by_step: dict = None) -> RoundRecord:
    """Run ``steps`` ticks of a fresh world and capture a :class:`RoundRecord`.

    ``inputs_by_step`` maps a step index to ``{pid: set(Intent)}``, exactly
    like :func:`spaceinvaders.engine.run_headless`. Uses the same
    :func:`~spaceinvaders.input.encode_inputs` that ``Room.run`` uses to build
    its own log, so the two stay interchangeable by construction rather than
    by convention.
    """
    inputs_by_step = inputs_by_step or {}
    world = GameWorld(cfg, rng=random.Random(seed), num_players=num_players)
    input_log = []
    tick = 0
    for i in range(steps):
        if world.state is not GameState.RUNNING:
            break
        inputs = inputs_by_step.get(i) or {}
        world.step(dt, inputs)
        tick += 1
        input_log.append((tick, encode_inputs(inputs)))
    record = RoundRecord(
        seed=seed,
        cfg=dataclasses.asdict(cfg),
        num_players=num_players,
        dt=dt,
        ticks=tick,
        input_log=input_log,
    )
    record.final_hash = state_hash(world)
    return record


def replay(record: RoundRecord) -> GameWorld:
    """Reconstruct and re-simulate a round from a :class:`RoundRecord`.

    Same seed + cfg + input_log in, bit-identical final ``snapshot()`` out —
    every time, on any machine, since the RNG is seeded and nothing here
    touches the wall clock.
    """
    cfg = Config(**record.cfg)
    world = GameWorld(cfg, rng=random.Random(record.seed),
                      num_players=record.num_players,
                      active_pids=record.active_pids)
    inputs_by_tick = {
        tick: {
            int(pid): {Intent[name] for name in names}
            for pid, names in held_by_pid.items()
        }
        for tick, held_by_pid in record.input_log
    }
    for i in range(record.ticks):
        world.step(record.dt, inputs_by_tick.get(i + 1) or {})
    return world


def state_hash(world_or_snapshot) -> str:
    """A short, deterministic fingerprint of a world's current state.

    Cheap enough to compare on every broadcast tick: canonical (sorted-key,
    separator-tight) JSON of the snapshot, hashed with sha256. Two
    independently-produced states hash equal iff their snapshots are equal.
    """
    snapshot = (world_or_snapshot.snapshot()
                if hasattr(world_or_snapshot, "snapshot") else world_or_snapshot)
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_json(record: RoundRecord) -> str:
    return json.dumps(dataclasses.asdict(record), sort_keys=True)


def from_json(text: str) -> RoundRecord:
    obj = json.loads(text)
    input_log = [
        (tick, {int(pid): list(names) for pid, names in held_by_pid.items()})
        for tick, held_by_pid in obj["input_log"]
    ]
    return RoundRecord(
        seed=obj["seed"],
        cfg=obj["cfg"],
        num_players=obj["num_players"],
        dt=obj["dt"],
        ticks=obj["ticks"],
        input_log=input_log,
        active_pids=obj.get("active_pids"),
        final_hash=obj.get("final_hash"),
    )


def _demo_record() -> RoundRecord:
    cfg = Config(enemy_rows=2, enemy_cols=3, enemy_fire_chance=2.0)
    inputs_by_step = {
        0: {0: {Intent.RIGHT, Intent.FIRE}},
        10: {1: {Intent.LEFT}},
    }
    return record_headless(cfg, seed=42, num_players=2, dt=1.0 / 30.0,
                           steps=60, inputs_by_step=inputs_by_step)


def _cli_record_demo(path: str) -> None:
    record = _demo_record()
    with open(path, "w") as fh:
        fh.write(to_json(record))
    print(f"wrote {path} (ticks={record.ticks}, final_hash={record.final_hash})")


def _cli_verify(path: str) -> None:
    with open(path) as fh:
        record = from_json(fh.read())
    actual = state_hash(replay(record))
    if actual == record.final_hash:
        print(f"OK: replay matches stored hash ({actual})")
    else:
        print(f"MISMATCH: stored={record.final_hash} actual={actual}")
        raise SystemExit(1)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Record or verify a deterministic Space Invaders replay")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record-demo", metavar="PATH",
                       help="record a short deterministic demo round to PATH")
    group.add_argument("--verify", metavar="PATH",
                       help="replay PATH and check it matches its stored hash")
    args = parser.parse_args(argv)

    if args.record_demo:
        _cli_record_demo(args.record_demo)
    else:
        _cli_verify(args.verify)


if __name__ == "__main__":  # pragma: no cover
    main()
