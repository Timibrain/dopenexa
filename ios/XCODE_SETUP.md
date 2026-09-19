# Dopenexa — Xcode-ready

1. Open `Dopenexa.xcodeproj` in Xcode 16 or newer.
2. Select the `Dopenexa` scheme and an iPhone/iPad simulator.
3. Set your Apple Developer Team under Signing & Capabilities if Xcode requests it.
4. Run the app.

## Backend
The app's default simulator and Release configurations use `https://api.dopenexa.com`.
For local development, select `ios/Config/Development.xcconfig` or pass it to `xcodebuild`; it keeps the API at `http://localhost:8000`.
Staging and production use the corresponding HTTPS API configuration. Do not point a production archive at localhost.

## Production
Set a real bundle identifier, Apple Team, HTTPS API URL, APNs configuration, payment-provider credentials, and production AI credentials before release.
