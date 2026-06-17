// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "iOSApp",
    platforms: [.iOS(.v16)],
    targets: [
        .executableTarget(name: "iOSApp", path: "Sources/iOSApp")
    ]
)
