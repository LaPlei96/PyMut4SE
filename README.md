# PyMut4SE

PyMut4SE is a Python mutation-generation and execution tool. This version focuses on generating first-order and higher-order mutants for Python functions, executing them against configured inputs, and storing the results in SQLite.

The repository includes a ready-to-run QuixBugs example dataset to replicate the experiments done for the "Neural Change Prediction: Relating Software Changes to Their Effects and Vice Versa" paper.

PyMut4SE is currently under development with a release planned in the next months.

## Current Scope

Supported today:

- Generate Python mutants from configured source files.
- Generate higher-order mutants up to a requested mutation degree.
- Execute original code and mutants in standalone mode.
- Store code chunks, inputs, environments, and outputs in SQLite.
- Run QuixBugs examples from existing JSON configs.

Not released yet:

- Full mutation-testing reports with expected-output comparison.
- `project` and `project-container` execution modes.
- Complete operator set planned for the future release.

## Requirements

- Python `>=3.13`
- `uv`
- `sqlite3`, only needed for `generate.sh`

Install dependencies:

```bash
uv sync
```

## QuixBugs Run Sequence

Use this sequence from the repository root to generate and execute mutants on QuixBugs.

1. Install dependencies:

```bash
uv sync
```

2. Generate QuixBugs config files: (only needs to be done once)

```bash
uv run python src/datasets/quixbugs/config_generator.py
```

3. Create a database by running:
```
uv run database/db_setup_quixbugs.py 
```

4. Run one QuixBugs program first, for a quick test:

```bash
uv run python -m pymut4se.scripts.HOM_gen_and_execution --config conf/quix_bugs_gen/quicksort_config.json --degree 1 --db quixbugs.db
```

5. Inspect the test database:

```bash
sqlite3 quixbugs.db '.tables'
sqlite3 quixbugs.db 'select count(*) from code_chunk'
sqlite3 quixbugs.db 'select success, count(*) from execution_output group by success;'
```

6. Run all QuixBugs configs and merge the results:

```bash
./generate.sh \
  --config-dir conf/quix_bugs_gen \
  --degree 1 \
  --parallel 4 \
  --merged-db merged_hom.db \
  --db-dir tmp_hom_dbs
```

7. Inspect the merged database:

```bash
sqlite3 merged_hom.db '.tables'
sqlite3 merged_hom.db 'select function_name, mutation_degree, count(*) from code_chunk group by function_name, mutation_degree order by function_name, mutation_degree;'
sqlite3 merged_hom.db 'select success, count(*) from execution_output group by success;'
```

Start with `--degree 1`. Higher degrees can produce many more mutants and take substantially longer. The amount of workers running in ``--parallel`` can be increased or decreased based on your hardware.

## Database Tables

The SQLite schema contains:

- `code_chunk`: original and mutated code.
- `input`: function inputs and execution settings.
- `project`: reserved for project-level execution metadata.
- `execution_environment`: local/container execution metadata.
- `execution_output`: execution results.

## Running External Code Against Stored Inputs

`exec_input.py` executes a code string or code file against all inputs already stored for a function.

```bash
uv run python -m pymut4se.scripts.exec_input \
  --db quixbugs.db \
  --function-name quicksort \
  --code 'def quicksort(arr): return sorted(arr)'
```

Or with a file:

```bash
uv run python -m pymut4se.scripts.exec_input \
  --db quixbugs.db \
  --function-name quicksort \
  --code-file src/datasets/quixbugs/src/quicksort.py
```

## Known Limitations

- Standalone execution is the only mode currently available (the other will come with the release).
- Expected outputs are stored in dataset files but not used for verdicts.
- Higher mutation degrees can grow quickly.
- `generate.sh` requires the `sqlite3` CLI.
- `quixbugs.db` may not contain tables until the schema setup script or a generation run creates them.