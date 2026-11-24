import AVFoundation
import Darwin
import Foundation

// The add-in and this application communicate through a private per-clip directory.
let args = CommandLine.arguments
guard args.count == 3, let owner = Int32(args[2]) else { exit(2) }
let folder = URL(fileURLWithPath: args[1], isDirectory: true)
func marker(_ name: String, _ value: String = "") {
    try? value.write(to: folder.appendingPathComponent(name), atomically: true, encoding: .utf8)
}
func stopped() -> Bool {
    FileManager.default.fileExists(atPath: folder.appendingPathComponent("stop").path) ||
        kill(owner, 0) != 0
}
func fail(_ message: String) -> Never {
    marker("error", message)
    exit(1)
}
func tick() {
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.05))
}

switch AVCaptureDevice.authorizationStatus(for: .audio) {
case .authorized:
    break
case .notDetermined:
    let decided = DispatchSemaphore(value: 0)
    AVCaptureDevice.requestAccess(for: .audio) { _ in decided.signal() }
    let deadline = ProcessInfo.processInfo.systemUptime + 45
    while !stopped() && ProcessInfo.processInfo.systemUptime < deadline {
        if decided.wait(timeout: .now() + 0.05) == .success { break }
    }
    if stopped() { marker("done"); exit(0) }
    guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
        fail("Allow exCADmple Microphone in System Settings > Privacy & Security > Microphone.")
    }
case .denied, .restricted:
    fail("Allow exCADmple Microphone in System Settings > Privacy & Security > Microphone.")
@unknown default:
    fail("Could not check microphone permissions on this Mac.")
}

do {
    let recorder = try AVAudioRecorder(url: folder.appendingPathComponent("voice.wav"), settings: [
        AVFormatIDKey: kAudioFormatLinearPCM,
        AVSampleRateKey: 16000.0,
        AVNumberOfChannelsKey: 1,
        AVLinearPCMBitDepthKey: 16,
        AVLinearPCMIsBigEndianKey: false,
        AVLinearPCMIsFloatKey: false,
    ])
    if stopped() { marker("done"); exit(0) }
    guard recorder.record() else { fail("Could not start recording. Check the sound input device in System Settings.") }
    marker("ready")
    while !stopped() && recorder.isRecording { tick() }
    let duration = Int((recorder.currentTime * 1000).rounded())
    recorder.stop()
    if !stopped() { fail("The audio input disconnected. Please record the message again.") }
    marker("done", String(duration))
} catch {
    fail("Could not open the audio input. Check the sound input settings on this Mac.")
}
