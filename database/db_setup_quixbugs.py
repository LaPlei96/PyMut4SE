import sqlite3

conn = sqlite3.connect("quixbugs.db")
cursor = conn.cursor()

create_code_table = """CREATE TABLE IF NOT EXISTS code_chunk(
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
)"""

create_input_table = """CREATE TABLE IF NOT EXISTS input(
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
)"""

create_project_table = """CREATE TABLE IF NOT EXISTS project(
    pl TEXT,
    type TEXT,
    working_dir TEXT,
    requirements_path TEXT,
    project_uuid TEXT PRIMARY KEY
)"""

create_execution_environment_table = """CREATE TABLE IF NOT EXISTS execution_environment(
    name TEXT,
    type TEXT,
    version TEXT,
    os TEXT,
    version_details TEXT,
    python_executable TEXT,
    container_image TEXT,
    environment_id TEXT PRIMARY KEY
)"""

create_execution_output_table = """CREATE TABLE IF NOT EXISTS execution_output(
    success TEXT,
    output TEXT,
    code_chunk_id TEXT,
    execution_environment_id TEXT,
    input_id TEXT,
    error_message TEXT,
    time_taken REAL,
    execution_id TEXT PRIMARY KEY
)"""

cursor.execute(create_code_table)
cursor.execute(create_input_table)
cursor.execute(create_project_table)
cursor.execute(create_execution_environment_table)
cursor.execute(create_execution_output_table)
conn.commit()
conn.close()