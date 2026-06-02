"""
Config generator for QuixBugs functions.

Generates configuration dictionaries for all functions in quixbugs/src
that have corresponding input files in quixbugs/inputs/.
"""
import json
from pathlib import Path
from datasets.quixbugs.inputs.code.inputs import Inputs

def get_function_name_from_file(filename: str) -> str:
    """Extract function name from filename by removing .py extension."""
    return filename[:-3]  # Remove .py


def find_input_file(function_name: str, inputs_dir: Path) -> str | None:
    """
    Find the input file path for a given function.

    Returns the relative path from project root if found, None otherwise.
    Checks for both JSON and Python code inputs.
    """
    # Check for JSON input
    json_path = inputs_dir / "json" / f"{function_name}.jsonl"
    if json_path.exists():
        return f"src/datasets/quixbugs/inputs/json/{function_name}.jsonl"

    # Check for Python code input
    code_path = inputs_dir / "code" / f"inputs_{function_name}.py"
    path_generated = inputs_dir / "json" / "generated" / f"{function_name}.json"

    if code_path.exists():
        path_generated.parent.mkdir(parents=True, exist_ok=True)  # Ensure generated dir exists
        module = f"datasets.quixbugs.inputs.code.inputs_{function_name}"
        try:
            # Dynamically import the module and get inputs
            inputs_module = __import__(module, fromlist=["Inputs"])
            print(inputs_module)
            inputs_class = getattr(inputs_module, f"Inputs{function_name.title().replace('_', '')}")
            print(inputs_class)
            inputs = inputs_class.get_inputs()
            print(f"Generated inputs for {function_name}: {inputs}")
            # Save inputs to JSON
            Inputs.to_json(inputs, path_generated)
            return f"src/datasets/quixbugs/inputs/json/generated/{function_name}.json"
        except Exception as e:
            print(f"Error processing {code_path}: {e}")

    return None


def generate_config(file_path: str, function_name: str, inputs_file: str | None) -> dict:
    """Generate a configuration dictionary for a function."""
    if inputs_file is None:
        return None  # Skip functions without inputs

    return {
        "file_path": f"src/datasets/quixbugs/src/{file_path}",
        "function_name": function_name,
        "operators": [],
        "execution": {
            "mode": "standalone",
            "python_executable": None,
            "working_dir": None,
            "test_command": None,
            "requirements_path": None,
            "timeout_seconds": 1,
        },
        "inputs_file": inputs_file,
    }


def generate_all_configs(src_dir: Path, inputs_dir: Path) -> dict:
    """
    Generate configuration dictionaries for all functions in src_dir.

    Returns a dictionary mapping function names to their config dictionaries.
    """
    configs = {}

    # Files to skip
    skip_files = {"__init__.py", "node.py"}

    # Iterate over Python files in src directory
    for file in sorted(src_dir.glob("*.py")):
        if file.name in skip_files:
            continue

        # Skip test files
        if "_test.py" in file.name:
            continue

        function_name = get_function_name_from_file(file.name)

        # Find corresponding input file
        inputs_file = find_input_file(function_name, inputs_dir)

        # Generate config if inputs exist
        if inputs_file:
            config = generate_config(file.name, function_name, inputs_file)
            if config:
                configs[function_name] = config

    return configs


def save_configs(configs: dict, output_dir: Path) -> None:
    """Save configuration dictionaries to individual JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for function_name, config in configs.items():
        output_file = output_dir / f"{function_name}_config.json"
        print("1")
        with open(output_file, "w") as f:
            json.dump(config, f, indent=2)
        print(f"Generated: {output_file}")


def main():
    """Main entry point for config generation."""
    # Get project root (assuming this script is in quixbugs/)
    project_root = Path(__file__).parent.parent

    src_dir = project_root  / "quixbugs" / "src"
    inputs_dir = project_root  / "quixbugs" / "inputs"
    output_dir = project_root.parent.parent / "conf" / "quix_bugs_gen"

    if not src_dir.exists():
        print(f"Error: Source directory not found: {src_dir}")
        return

    if not inputs_dir.exists():
        print(f"Error: Inputs directory not found: {inputs_dir}")
        return

    # Generate all configs
    print(f"Scanning {src_dir} for functions...")
    configs = generate_all_configs(src_dir, inputs_dir)

    print(f"Found {len(configs)} functions with inputs")

    # Save configs
    print(f"Saving configs to {output_dir}...")
    save_configs(configs, output_dir)

    print("Done!")


if __name__ == "__main__":
    main()
