import pathlib

MAIN_FILE = pathlib.Path("main.py")

print("Applying login patch...")

text = MAIN_FILE.read_text(encoding="utf-8", errors="ignore")

old = '<input name="password" placeholder="Password">'

new = (
    '<input name="email" placeholder="Email" required><br>'
    '<input type="password" name="password" placeholder="Password" required><br>'
    '<input name="invite" placeholder="Invite Code" required>'
)

if old in text:
    text = text.replace(old, new)
    MAIN_FILE.write_text(text, encoding="utf-8")
    print("Login form patched successfully.")
else:
    print("Login form already patched or pattern not found.")