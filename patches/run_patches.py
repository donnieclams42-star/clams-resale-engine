import subprocess

patches = [
    "patch_login.py",
]

for patch in patches:
    print(f"Running {patch}...")
    subprocess.run(["python", f"patches/{patch}"])