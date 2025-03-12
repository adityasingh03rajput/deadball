[app]

# Title of your application
title = DarkBall

# Package name (must be unique)
package.name = DarkBallGame

# Package domain (must be unique)
package.domain = org.example

# Source code location
source.include_exts = py,png,jpg,kv,atlas

# Requirements
requirements = kivy==2.1.0

# Orientation (portrait or landscape)
orientation = landscape

# Fullscreen mode (1 for fullscreen, 0 for windowed)
fullscreen = 1

# Presplash screen (optional)
# presplash.filename = %(source.dir)s/assets/presplash.png

# Icon (optional)
# icon.filename = %(source.dir)s/assets/icon.png

# Android specific configurations
[app:android]

# Android SDK and NDK paths (auto-detected by Buildozer)
# android.sdk_path = /path/to/android/sdk
# android.ndk_path = /path/to/android/ndk

# Android API level (minimum and target)
android.api = 30
android.minapi = 21

# Permissions required by the app
android.permissions = INTERNET

# Features required by the app
android.features =

# Android app version (integer)
version = 1.0

# Android app version code (integer)
version.code = 1

# Android app release mode (debug or release)
# release mode requires signing keys
# android.release_artifact = release

# Log level for Buildozer (0 = quiet, 1 = normal, 2 = verbose)
log_level = 2
