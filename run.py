import os
import subprocess

# Path to the 'src' directory
src_directory = "./src"

# Iterate over each file in the 'src' directory
for filename in os.listdir(src_directory):
    if filename.endswith(".py"):
        # Construct the full file path
        file_path = os.path.join(src_directory, filename)

        # Run the Python script
        print(f"Running {filename}...")
        subprocess.run(["python", file_path])


for filename in os.listdir("./test"):
    if filename.endswith(".py"):
        # Construct the full file path
        file_path = os.path.join(src_directory, filename)

        # Run the Python script
        print(f"Running {filename}...")
        subprocess.run(["python", file_path])
