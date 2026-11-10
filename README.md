# TaxiGraph

TaxiGraph is a journey-planning project for Cape Town's informal minibus taxi network: the routes, ranks, and boarding practices that formal transit data typically leaves out.

Rather than guessing at schedules or inventing service where none is confirmed, TaxiGraph treats every claim (a route, a stop, a fare, a direction of travel) as evidence that must be sourced, dated, and verified before it reaches a rider. Unknown stays unknown; it is never quietly filled in as zero, daily, or bidirectional.

## Status

**Feasibility-spike stage.** The project's first milestone is proving that a small, manually verified set of real Cape Town journeys can be routed correctly, before any database, frontend, or public deployment is built.

The software half of that spike now passes: an explicitly synthetic test network builds and routes correctly through a real, pinned OpenTripPlanner 2.9.0 instance ([details](docs/FEASIBILITY-RESULTS.md)). **No real Cape Town journey has been validated, and no route data has been published.** That requires resolved data-use rights and field-verified evidence that don't exist yet. See [docs/MVP-SPEC.md](docs/MVP-SPEC.md) for the exact gates that must pass before that claim can be made.

## How it's meant to work

- **Own the hard part.** TaxiGraph owns source adapters, a canonical data model, identity resolution, provenance, and verification for informal transit data. GTFS is treated as an *export format*, not the source of truth.
- **Reuse the routing engine.** [OpenTripPlanner](https://www.opentripplanner.org/) handles transit routing, transfers, and OSM-based walking directions; it isn't reinvented here.
- **Reuse the map.** [MapLibre GL JS](https://maplibre.org/) will eventually power the client map, once real journeys pass the feasibility gate.
- **Files first, database later.** The feasibility spike works entirely with files. PostGIS is introduced only after real-data feasibility is proven.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full component breakdown and boundaries, and [docs/ADR.md](docs/ADR.md) for the decisions behind them.

## Run the tests

Needs Python 3.13 or newer. The tests use only the synthetic fixture and need no network, Java or OTP download.

```bash
cd spikes/feasibility
python -m pip install -e ".[dev]"
python -m pytest
```

The full smoke check (`python -m taxigraph_spike check --mode smoke`) also needs Java and the pinned tools; see [spikes/feasibility/README.md](spikes/feasibility/README.md).

## Documentation

| Doc | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Ground rules for anyone (human or agent) working in this repo |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Selected architecture, component boundaries, integration contracts |
| [docs/MVP-SPEC.md](docs/MVP-SPEC.md) | The staged milestones and the gates each one must pass |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Sequential implementation tasks |
| [docs/DATA-MODEL.md](docs/DATA-MODEL.md) | Canonical data model |
| [docs/DATA-SOURCES.md](docs/DATA-SOURCES.md) | Source data and rights/licensing notes |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Background research behind the architecture decision |
| [docs/SOL-HANDOFF.md](docs/SOL-HANDOFF.md) | Spec for the current active task (feasibility harness) |
| [docs/FEASIBILITY-RESULTS.md](docs/FEASIBILITY-RESULTS.md) | Current status of the feasibility spike |

## Principles

- **No invented transport facts.** Schedules, headways, fares, operating days, and boarding permissions are never assumed; they're only recorded when there's evidence for them.
- **Provenance survives every transformation.** Source, retrieval time, verification time, and evidence status travel with every claim from raw import to public export.
- **Real data and test fixtures never mix.** Synthetic data used to exercise the software is always clearly labelled and kept separate from verified Cape Town data.

## License

[MIT](LICENSE) © 2026 Ubayd Hattas
