#!/usr/bin/env python3
"""
Script to collect all Python files from src/cartesia directory and print them
into a single text file with appropriate markers for AI analysis.
"""

import os
import time
from pathlib import Path

def collect_python_files(root_dir, output_file):
    """
    Recursively collects all .py files from the given directory and writes them
    to a single text file with appropriate markers.
    
    Args:
        root_dir (str): Root directory to search for Python files
        output_file (str): Path to the output text file
    """
    # Convert to Path object
    root_path = Path(root_dir)
    
    # Ensure the root directory exists
    if not root_path.exists() or not root_path.is_dir():
        print(f"Error: Directory '{root_dir}' does not exist")
        return
    
    # Get all Python files recursively
    python_files = list(root_path.glob('**/*.py'))
    
    # Sort files for consistent output
    python_files.sort()
    
    # Count files found
    file_count = len(python_files)
    print(f"Found {file_count} Python files in {root_dir}")
    
    # Create output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp for the header
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    # Write all files to the output file
    with open(output_file, 'w', encoding='utf-8') as f:
        # Write header
        f.write(f"# CARTESIA PYTHON CODEBASE COLLECTION\n")
        f.write(f"# Generated on: {timestamp}\n")
        f.write(f"# Total files: {file_count}\n")
        f.write(f"# Root directory: {root_dir}\n")
        f.write("\n" + "="*80 + "\n\n")
        
        # Process each file
        for i, py_file in enumerate(python_files, 1):
            # Get relative path from the root directory
            rel_path = py_file.relative_to(root_path)
            
            try:
                # Read file content
                with open(py_file, 'r', encoding='utf-8') as src_file:
                    content = src_file.read()
                
                # Write file information and content with markers
                f.write(f"FILE_START: {rel_path} ({i}/{file_count})\n")
                f.write(f"FILE_PATH: {py_file}\n")
                f.write("-"*80 + "\n\n")
                f.write(content)
                f.write("\n\n")
                f.write("-"*80 + "\n")
                f.write(f"FILE_END: {rel_path}\n\n")
                f.write("="*80 + "\n\n")
                
                print(f"Processed ({i}/{file_count}): {rel_path}")
            
            except Exception as e:
                f.write(f"ERROR: Could not read {rel_path}: {str(e)}\n\n")
                print(f"Error processing {rel_path}: {str(e)}")
    
    print(f"\nComplete! All Python files have been written to: {output_file}")
    print(f"Total files processed: {file_count}")

if __name__ == "__main__":
    # Configuration
    SOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "cartesia/tts")
    OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cartesia_python_files.txt")
    
    # Execute the collection
    collect_python_files(SOURCE_DIR, OUTPUT_FILE)
