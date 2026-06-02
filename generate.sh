#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./generate.sh --config-dir <dir> --degree <n> [--parallel <n>] [--merged-db <path>] [--db-dir <dir>]

Description:
  For each JSON config file in <dir>, run:
    uv run src/pymut4se/scripts/HOM_gen_and_execution.py \
      --config <config_path> --degree <n> --db <db_path>

  Then merge all generated SQLite DBs into one merged DB.

Options:
  --config-dir   Directory containing config JSON files (required)
  --degree       Max mutation degree passed to HOM_gen_and_execution.py (required)
  --parallel     Number of concurrent HOM runs (default: 1)
  --merged-db    Output merged DB path (default: ./merged_hom.db)
  --db-dir       Directory for per-config DB files (default: ./tmp_hom_dbs)
  -h, --help     Show this help
USAGE
}

CONFIG_DIR=""
DEGREE=""
PARALLEL=1
MERGED_DB="$(pwd)/merged_hom.db"
DB_DIR="$(pwd)/tmp_hom_dbs"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config-dir)
      if [[ $# -lt 2 ]]; then
        echo "Error: --config-dir requires a value." >&2
        exit 1
      fi
      CONFIG_DIR="$2"
      shift 2
      ;;
    --degree)
      if [[ $# -lt 2 ]]; then
        echo "Error: --degree requires a value." >&2
        exit 1
      fi
      DEGREE="$2"
      shift 2
      ;;
    --parallel)
      if [[ $# -lt 2 ]]; then
        echo "Error: --parallel requires a value." >&2
        exit 1
      fi
      PARALLEL="$2"
      shift 2
      ;;
    --merged-db)
      if [[ $# -lt 2 ]]; then
        echo "Error: --merged-db requires a value." >&2
        exit 1
      fi
      MERGED_DB="$2"
      shift 2
      ;;
    --db-dir)
      if [[ $# -lt 2 ]]; then
        echo "Error: --db-dir requires a value." >&2
        exit 1
      fi
      DB_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$CONFIG_DIR" || -z "$DEGREE" ]]; then
  echo "Error: --config-dir and --degree are required." >&2
  usage
  exit 1
fi

if [[ ! -d "$CONFIG_DIR" ]]; then
  echo "Error: config directory does not exist: $CONFIG_DIR" >&2
  exit 1
fi

if ! [[ "$DEGREE" =~ ^[0-9]+$ ]]; then
  echo "Error: --degree must be a non-negative integer." >&2
  exit 1
fi

if ! [[ "$PARALLEL" =~ ^[0-9]+$ ]] || [[ "$PARALLEL" -lt 1 ]]; then
  echo "Error: --parallel must be an integer >= 1." >&2
  exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "Error: sqlite3 is required but not found in PATH." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required but not found in PATH." >&2
  exit 1
fi

mkdir -p "$DB_DIR"
mkdir -p "$(dirname "$MERGED_DB")"

init_db_schema() {
  local db_path="$1"
  sqlite3 "$db_path" <<'SQL'
CREATE TABLE IF NOT EXISTS code_chunk(
  chunk_id TEXT PRIMARY KEY,
  code TEXT,
  pl TEXT,
  function_name TEXT,
  mutation_degree INTEGER,
  location TEXT,
  original_code TEXT,
  parent_id TEXT,
  line_changed INTEGER,
  mutation_type TEXT,
  mutation_operator TEXT,
  mutation_tool TEXT
);

CREATE TABLE IF NOT EXISTS input(
  type TEXT,
  value TEXT,
  function_name TEXT,
  mode TEXT,
  code_location TEXT,
  working_dir TEXT,
  test_command TEXT,
  timeout_seconds INTEGER,
  extra_env TEXT,
  requirements_path TEXT,
  input_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS project(
  pl TEXT,
  type TEXT,
  working_dir TEXT,
  requirements_path TEXT,
  project_uuid TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS execution_environment(
  name TEXT,
  type TEXT,
  version TEXT,
  os TEXT,
  version_details TEXT,
  python_executable TEXT,
  container_image TEXT,
  environment_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS execution_output(
  success TEXT,
  output TEXT,
  code_chunk_id TEXT,
  execution_environment_id TEXT,
  input_id TEXT,
  error_message TEXT,
  time_taken REAL,
  execution_id TEXT PRIMARY KEY
);
SQL
}

merge_one_db_into_merged() {
  local source_db="$1"
  local escaped_source_db="${source_db//\'/\'\'}"
  sqlite3 "$MERGED_DB" <<SQL
ATTACH DATABASE '$escaped_source_db' AS src;

INSERT OR IGNORE INTO code_chunk SELECT * FROM src.code_chunk;
INSERT OR IGNORE INTO input SELECT * FROM src.input;
INSERT OR IGNORE INTO project SELECT * FROM src.project;
INSERT OR IGNORE INTO execution_environment SELECT * FROM src.execution_environment;
INSERT OR IGNORE INTO execution_output SELECT * FROM src.execution_output;

DETACH DATABASE src;
SQL
}

# Recreate merged DB from scratch for reproducibility.
rm -f "$MERGED_DB"
init_db_schema "$MERGED_DB"

shopt -s nullglob
config_files=("$CONFIG_DIR"/*.json)
shopt -u nullglob

if [[ ${#config_files[@]} -eq 0 ]]; then
  echo "Error: no .json config files found in $CONFIG_DIR" >&2
  exit 1
fi

total_configs="${#config_files[@]}"
echo "Starting HOM generation for $total_configs config file(s) with parallelism=$PARALLEL"
echo "Per-config logs will be written to: $DB_DIR"

run_one_config() {
  local cfg="$1"
  cfg_name="$(basename "$cfg" .json)"
  db_path="$DB_DIR/${cfg_name}.db"
  log_path="$DB_DIR/${cfg_name}.log"

  echo "==> Processing $cfg_name"

  rm -f "$db_path"
  init_db_schema "$db_path"

  uv run src/pymut4se/scripts/HOM_gen_and_execution.py \
    --config "$cfg" \
    --degree "$DEGREE" \
    --db "$db_path" >"$log_path" 2>&1
}

declare -a db_paths=()
declare -a pids=()
failed=0
completed_jobs=0

# Portable concurrency limiter (works on older bash without `wait -n`).
sem_fifo="$(mktemp -u "/tmp/hom_sem.XXXXXX")"
mkfifo "$sem_fifo"
exec 9<>"$sem_fifo"
rm -f "$sem_fifo"
for ((i = 0; i < PARALLEL; i++)); do
  printf '%s\n' "." >&9
done

for cfg in "${config_files[@]}"; do
  cfg_name="$(basename "$cfg" .json)"
  db_path="$DB_DIR/${cfg_name}.db"
  db_paths+=("$db_path")

  # Acquire one slot; blocks when PARALLEL jobs are already active.
  read -r -u 9 _

  (
    run_one_config "$cfg"
    job_status=$?
    # Release slot for next job.
    printf '%s\n' "." >&9
    exit "$job_status"
  ) &
  pids+=("$!")
  echo "Queued: $cfg_name (max parallel: $PARALLEL)"
done

for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    failed=1
  fi
  ((completed_jobs += 1))
  echo "Progress HOM runs: $completed_jobs/$total_configs completed"
done

exec 9>&-
exec 9<&-

if [[ "$failed" -ne 0 ]]; then
  echo "Error: at least one HOM run failed. See per-config logs in: $DB_DIR" >&2
  exit 1
fi

echo "All HOM runs completed. Starting merge into: $MERGED_DB"
merge_index=0
for db_path in "${db_paths[@]}"; do
  ((merge_index += 1))
  echo "Merging DB $merge_index/$total_configs: $db_path"
  merge_one_db_into_merged "$db_path"
done

echo "Done. Per-config DBs are in: $DB_DIR"
echo "Merged DB: $MERGED_DB"
