macOS will refuse to open this the first time, saying "Apple could not verify
'ReactorDrone' is free of malware." That is not a warning about the game — Apple
charges $99/yr for the developer certificate that suppresses it, and this build
does not have one.

To open it:

1. Click **Done** on the warning. Do not click Move to Trash.
2. Open **System Settings** → **Privacy & Security**.
3. Scroll down to the line saying ReactorDrone was blocked, and click **Open Anyway**.
4. Confirm when prompted. The game opens, and you only do this once.

Prefer the terminal? Run `xattr -dr com.apple.quarantine ReactorDrone.app`
instead. Right-click → Open no longer works on macOS Sequoia and later.
