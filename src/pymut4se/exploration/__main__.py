import argparse
import json

from pymut4se.exploration import explore_path


def main() -> None:
    """Run project exploration and print an entity summary."""
    parser = argparse.ArgumentParser(description="Explore Python packages, modules, and function code chunks.")
    parser.add_argument("path", help="Python file or directory to explore.")
    args = parser.parse_args()

    project = explore_path(args.path).project
    print(
        json.dumps(
            {
                "project_id": project.project_id,
                "packages": project.package_count,
                "modules": project.module_count,
                "code_chunks": project.code_chunk_count,
                "test_suites": project.test_suite_count,
                "test_cases": project.test_case_count,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
