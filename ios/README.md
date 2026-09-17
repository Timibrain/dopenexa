# Dopenexa iOS

SwiftUI source for Sprint 1.5.

## Configure API

The app defaults to `http://localhost:8000`. For a physical iPhone, use the Mac's LAN IP or a staging HTTPS URL.

At runtime you can set:

```swift
UserDefaults.standard.set("http://192.168.1.20:8000", forKey: "dopenexa_api_url")
```

before `APIClient.shared` is first initialized.

## Build

Create an iOS SwiftUI App target named `Dopenexa` in Xcode and add the contents of `ios/Dopenexa` to the target. The source is intentionally kept Xcode-project agnostic so it can be inserted into the team's preferred workspace.
