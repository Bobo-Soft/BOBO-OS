// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "SwiftUIApp",
    platforms: [.iOS(.v16), .macOS(.v13)],
    targets: [
        .executableTarget(name: "SwiftUIApp", path: "Sources/SwiftUIApp")
    ]
)
