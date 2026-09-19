# Dopenexa iOS

SwiftUI source for Sprint 1.5.

## Configure API

The app's default Debug/Release configurations use `https://api.dopenexa.com`. Local development remains available through `Config/Development.xcconfig`.

For a local build, pass the development xcconfig to `xcodebuild` (or select it in Xcode):

```bash
xcodebuild -project Dopenexa.xcodeproj -scheme Dopenexa -configuration Debug \
  -xcconfig Config/Development.xcconfig -sdk iphonesimulator build
```

## Build

Create an iOS SwiftUI App target named `Dopenexa` in Xcode and add the contents of `ios/Dopenexa` to the target. The source is intentionally kept Xcode-project agnostic so it can be inserted into the team's preferred workspace.
