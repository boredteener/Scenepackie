// Native Scenepackie clip player. Launch through macOS LaunchServices.
// The parent app waits for this app to quit and then asks Yes / No.
import AppKit
import AVKit
import AVFoundation
import Foundation

final class PreviewController: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var window: NSWindow?
    private var player: AVPlayer?
    private var endObserver: NSObjectProtocol?
    private var itemObserver: NSKeyValueObservation?
    private var readySent = false

    private func fail(_ explanation: String) {
        fputs("Scenepackie preview: \(explanation)\n", stderr)
        NSApp.terminate(nil)
        // Exit status distinguishes a failed preview from an intentionally closed window.
        exit(2)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard CommandLine.arguments.count == 3 else {
            fail("missing clip or ready-file path")
            return
        }
        let url = URL(fileURLWithPath: CommandLine.arguments[1])
        let readyPath = URL(fileURLWithPath: CommandLine.arguments[2])
        guard FileManager.default.fileExists(atPath: url.path) else {
            fail("preview clip does not exist")
            return
        }

        let item = AVPlayerItem(url: url)
        let player = AVPlayer(playerItem: item)
        self.player = player

        let rect = NSRect(x: 0, y: 0, width: 880, height: 495)
        let view = AVPlayerView(frame: rect)
        view.player = player
        view.controlsStyle = .floating
        view.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: rect,
                              styleMask: [.titled, .closable, .resizable, .miniaturizable],
                              backing: .buffered, defer: false)
        window.title = "scenepackie · clip preview"
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.center()
        window.delegate = self
        self.window = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        itemObserver = item.observe(\.status, options: [.initial, .new]) { [weak self] item, _ in
            DispatchQueue.main.async {
                guard let self = self else { return }
                switch item.status {
                case .readyToPlay:
                    if !self.readySent {
                        do {
                            try "ready".write(to: readyPath, atomically: true, encoding: .utf8)
                        } catch {
                            self.fail("could not report player readiness: \(error.localizedDescription)")
                            return
                        }
                        self.readySent = true
                        self.player?.play()
                    }
                case .failed:
                    self.fail(item.error?.localizedDescription ?? "the clip could not be played")
                default:
                    break
                }
            }
        }

        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { _ in
            NSApp.terminate(nil)
        }
    }

    func windowWillClose(_ notification: Notification) {
        NSApp.terminate(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        player?.pause()
        itemObserver?.invalidate()
        if let token = endObserver {
            NotificationCenter.default.removeObserver(token)
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let controller = PreviewController()
app.delegate = controller
app.run()
