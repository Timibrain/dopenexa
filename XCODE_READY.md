# Dopenexa Xcode-ready package

## Mac setup
1. Install Xcode and Docker Desktop.
2. Unzip the package.
3. Run `./setup.sh` from the project root.
4. Open `ios/Dopenexa.xcodeproj`.
5. Select the shared `Dopenexa` scheme and an iPhone Simulator.
6. Press Run.

The iOS app is configured for `http://localhost:8000` in Debug/Release. The backend is started by Docker Compose.

### Physical iPhone
The simulator can use localhost. A physical iPhone cannot use the Mac's localhost; set `DOPENEXA_API_URL` in the Xcode configuration to your Mac's LAN IP, for example `http://192.168.1.20:8000`, or use a production HTTPS API.

### Apple signing
Automatic signing is enabled. Xcode may ask you to select your Apple Developer team; that step requires your Apple account and cannot be pre-authorized in a project archive.
