import os
import sys
import urllib.request
import tarfile
import subprocess
import shutil

LKH_VERSION = "LKH-3.0.14"
URL = f"http://akira.ruc.dk/~keld/research/LKH-3/{LKH_VERSION}.tgz"
TAR_FILE = f"{LKH_VERSION}.tgz"
EXTRACT_DIR = LKH_VERSION

def download_file(url, dest):
    print(f"Downloading {url} to {dest}...")
    try:
        urllib.request.urlretrieve(url, dest)
        print("Download completed successfully.")
    except Exception as e:
        print(f"Failed to download from main URL: {e}")
        # Try a backup URL or older version if needed
        backup_url = f"https://akira.ruc.dk/~keld/research/LKH-3/LKH-3.0.11.tgz"
        print(f"Trying backup URL: {backup_url}")
        dest_backup = "LKH-3.0.11.tgz"
        urllib.request.urlretrieve(backup_url, dest_backup)
        return dest_backup, "LKH-3.0.11"
    return dest, LKH_VERSION

def main():
    workspace = os.path.dirname(os.path.abspath(__file__))
    os.chdir(workspace)

    # 1. Download LKH3
    tar_path, version = download_file(URL, TAR_FILE)
    extract_dir = version

    # 2. Extract LKH3
    print(f"Extracting {tar_path}...")
    if os.path.exists(extract_dir):
        print(f"Removing existing directory {extract_dir}...")
        shutil.rmtree(extract_dir)

    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=".")
    print(f"Extracted to {extract_dir}.")

    # Clean up tgz file
    try:
        os.remove(tar_path)
    except:
        pass

    # 3. Clean precompiled Linux .o files
    lkh_dir = os.path.join(workspace, extract_dir)
    obj_dir = os.path.join(lkh_dir, "SRC", "OBJ")
    if os.path.exists(obj_dir):
        print(f"Cleaning precompiled Linux object files in {obj_dir}...")
        for f in os.listdir(obj_dir):
            if f.endswith(".o"):
                try:
                    os.remove(os.path.join(obj_dir, f))
                except Exception as e:
                    print(f"Error removing {f}: {e}")

    # Modify GetTime.c for Windows compatibility (disable getrusage)
    get_time_path = os.path.join(lkh_dir, "SRC", "GetTime.c")
    if os.path.exists(get_time_path):
        print(f"Modifying {get_time_path} for Windows compatibility...")
        with open(get_time_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("#define HAVE_GETRUSAGE", "/* #define HAVE_GETRUSAGE */")
        with open(get_time_path, "w", encoding="utf-8") as f:
            f.write(content)


    # 4. Compile using mingw32-make
    print(f"Compiling LKH in {extract_dir}...")
    lkh_dir = os.path.join(workspace, extract_dir)
    
    # We run mingw32-make. Let's check if we can run it.
    try:
        # Run make command directly in the SRC directory to avoid hardcoded 'make' in root Makefile
        # We also pass CC=gcc because Windows MinGW has gcc.exe but not cc.exe
        result = subprocess.run(
            ["mingw32-make", "-j", "-C", "SRC", "CC=gcc"], 
            cwd=lkh_dir, 
            capture_output=True, 
            text=True, 
            check=True
        )
        print("Compilation stdout:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("Compilation failed!")
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        sys.exit(1)

    # 4. Verify LKH.exe is generated
    exe_name = "LKH.exe"
    exe_path = os.path.join(lkh_dir, exe_name)
    if os.path.exists(exe_path):
        print(f"Success! {exe_name} compiled successfully at {exe_path}.")
        # Copy to the root workspace
        target_path = os.path.join(workspace, exe_name)
        shutil.copy2(exe_path, target_path)
        print(f"Copied {exe_name} to root workspace at {target_path}")
    else:
        # In Linux it compiles to "LKH", but we are on Windows with MinGW, so it should be LKH.exe or LKH
        alternative_exe_path = os.path.join(lkh_dir, "LKH")
        if os.path.exists(alternative_exe_path):
            print(f"Success! Compiled binary found at {alternative_exe_path}.")
            target_path = os.path.join(workspace, "LKH.exe")
            shutil.copy2(alternative_exe_path, target_path)
            print(f"Copied LKH to {target_path}")
        else:
            print("Error: Could not find compiled LKH binary in build directory.")
            sys.exit(1)

if __name__ == "__main__":
    main()
