from collections import defaultdict
from datetime import datetime
from urllib.parse import quote
import json
import os
import re
import sys


def parse_file(filename):
    """Parse the pipe-separated file and group by pattern name."""
    patterns = defaultdict(list)

    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split(" | ")
            if len(parts) < 3:
                continue

            pattern_name = parts[0] if parts[0].strip() else "unknown"
            modification_type = parts[1]

            if (
                modification_type == "notifyOperationReplaced (with op)"
                and len(parts) == 4
            ):
                # Format: pattern | notifyOperationReplaced (with op) | old_op | new_op
                old_op = parts[2]
                new_op = parts[3]
                patterns[pattern_name].append(
                    {"type": modification_type, "old_op": old_op, "new_op": new_op}
                )
            else:
                # Format: pattern | modification_type | op_name [| extra]
                op_name = parts[2]
                patterns[pattern_name].append(
                    {"type": modification_type, "op": op_name}
                )

    return patterns


unique_id = 0


def sanitize_filename(pattern_name):
    """Convert pattern name to a valid filename."""
    global unique_id
    # Remove template parameters and namespaces for filename
    name = pattern_name.split("<")[0]  # Remove template params
    name = name.split("::")[-1]  # Take last part after ::
    # Replace invalid characters
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name) + f"_{unique_id}"
    unique_id += 1
    return name.lower()


def extract_class_name(pattern_name):
    """Extract just the class name without namespaces or template args."""
    # Remove template parameters
    name = pattern_name.split("<")[0]
    # Remove namespaces - take last part after ::
    name = name.split("::")[-1]
    return name


def create_hugo_post(pattern_name, operations, output_dir):
    """Create a Hugo blog post for a pattern."""
    filename = sanitize_filename(pattern_name)
    filepath = os.path.join(output_dir, f"{filename}.md")

    # Create GitHub search URL
    class_name = extract_class_name(pattern_name)
    search_query = quote(f'path:mlir "{class_name}"')
    github_url = f"https://github.com/search?q=repo%3Allvm%2Fllvm-project+{search_query}&type=code"

    # Group operations by type
    operations_by_type = defaultdict(list)

    for op in operations:
        if op["type"] == "notifyOperationReplaced (with op)":
            operations_by_type["Operations replaced"].append(op)
        elif op["type"] == "notifyOperationInserted":
            operations_by_type["Operations inserted"].append(op)
        elif op["type"] == "notifyOperationErased":
            operations_by_type["Operations erased"].append(op)
        elif op["type"] == "notifyOperationModified":
            operations_by_type["Operations modified"].append(op)
        elif op["type"] == "notifyOperationReplaced (with values)":
            operations_by_type["Operations replaced with values"].append(op)
        else:
            raise ValueError("unknown modification type: " + op["type"])

    # Generate content
    today = datetime.now().strftime("%Y-%m-%d")

    content = f"""---
title: "{pattern_name}"
date: {today}
---

# `{pattern_name}`

[Search in LLVM Project]({github_url})

## Operations Modified

"""

    for op_type, ops in operations_by_type.items():
        content += f"### {op_type}\n\n"
        for op in ops:
            if op_type == "Operations replaced":
                content += f"- `{op['old_op']}` → `{op['new_op']}`\n"
                continue
            content += f"- `{op['op']}`\n"
        content += "\n"

    # Write file
    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(content)

    print(f"Generated: {filepath}")


def generate_posts(patterns, output_dir="website/content/patterns/"):
    """
    Generate Hugo blog posts from pattern file.

    Args:
        patterns: The parsed input file
        output_dir: Directory to write Hugo posts (default: content/patterns/)
    """
    print(f"Found {len(patterns)} patterns")

    for pattern_name, operations in patterns.items():
        create_hugo_post(pattern_name, operations, output_dir)

    print(f"Generated {len(patterns)} blog posts in {output_dir}")


def preprocess_data(
    input_file,
    output_dir="search_data",
    class_pages_dir="website/content/patterns/",
    index_output_dir="website/static/",
    index_output_filename="pattern_catalog_index.json",
):
    """
    Preprocesses the input file into a search index and generates
    class-specific HTML pages.
    """
    os.makedirs(output_dir, exist_ok=True)
    search_index = defaultdict(set)

    patterns = parse_file(input_file)

    for pattern_name, mods in patterns.items():
        for mod in mods:
            mod_type = mod["type"]
            if mod_type == "notifyOperationReplaced (with op)":
                search_index[mod["old_op"]].add(pattern_name)
                search_index[mod["new_op"]].add(pattern_name)
            else:
                search_index[mod["op"]].add(pattern_name)

    # Convert sets to lists for JSON serialization
    for op_name, class_names_set in search_index.items():
        search_index[op_name] = list(class_names_set)

    # Save the search index
    with open(os.path.join(index_output_dir, index_output_filename), "w") as f:
        json.dump(search_index, f, indent=2)

    generate_posts(patterns, class_pages_dir)

    print(
        f"Preprocessing complete. Search index saved to '{os.path.join(output_dir, index_output_filename)}'"
    )
    print(f"Class pages generated in '{class_pages_dir}'")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise ValueError(
            "Usage: postprocess_pattern_catalog.py path/to/pattern_catalog.txt"
        )
    preprocess_data(sys.argv[1])
