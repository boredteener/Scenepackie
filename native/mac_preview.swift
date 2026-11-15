// A tiny native macOS preview window, bundled with Scenepackie.
// Exits after playback finishes or the editor closes the window.
import AppKit
import AVKit
import AVFoundation

final class ScenepackiePreview: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var window: NSWindow?
    private var player: AVPlayer?
    private var finishObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard CommandLine.arguments.count == 2 else {
            NSApp.terminate(nil)
            return
        }
        let url = URL(fileURLWithPath: CommandLine.arguments[1])
        guard FileManager.default.fileExists(atPath: url.path) else {
            NSApp.terminate(nil)
            return
        }

        let item = AVPlayerItem(url: url)
        let player = AVPlayer(playerItem: item)
        self.player = player

        let playerView = AVPlayerView(frame: NSRect(x: 0, y: 0, width: 880, height: 495))
        playerView.player = player
        playerView.controlsStyle = .floating

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 880, height: 495),
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered, defer: false
        )
        window.title = "scenepackie · clip preview"
        window.contentView = playerView
        window.center()
        window.delegate = self
        self.window = window

        finishObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { _ in
            // Exiting signals the Python app to ask whether to keep this clip.
            NSApp.terminate(nil)
        }
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        player.play()
    }

    func windowWillClose(_ notification: Notification) {
        // Closing the preview early is also an intentional review decision.
        NSApp.terminate(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        player?.pause()
        if let observer = finishObserver {
            NotificationCenter.default.removeObserver(observer)
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let handler = ScenepackiePreview()
app.delegate = handler
app.run()
