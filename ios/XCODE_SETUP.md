# Dopenexa — Xcode-ready

1. Open `Dopenexa.xcodeproj` in Xcode 16 or newer.
2. Select the `Dopenexa` scheme and an iPhone/iPad simulator.
3. Set your Apple Developer Team under Signing & Capabilities if Xcode requests it.
4. Run the app.

## Backend
The app defaults to `http://localhost:8000`. Start the FastAPI backend from the repository root.
For staging and production, set `DOPENEXA_API_URL` through the corresponding xcconfig in `ios/Config/`. Do not point a production archive at localhost. Development may continue using the local API URL.

## Production
Set a real bundle identifier, Apple Team, HTTPS API URL, APNs configuration, payment-provider credentials, and production AI credentials before release.
