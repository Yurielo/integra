import AppKit
import Foundation

func writePNG(_ image: NSImage, to path: String) throws {
  let size = NSSize(width: 512, height: 512)
  let canvas = NSImage(size: size)
  canvas.lockFocus()
  NSGraphicsContext.current?.imageInterpolation = .high
  image.draw(in: NSRect(origin: .zero, size: size))
  canvas.unlockFocus()
  guard let tiff = canvas.tiffRepresentation,
    let bitmap = NSBitmapImageRep(data: tiff),
    let png = bitmap.representation(using: .png, properties: [:])
  else { throw NSError(domain: "IntegraIconProbe", code: 1) }
  try png.write(to: URL(fileURLWithPath: path), options: .atomic)
}

guard CommandLine.arguments.count >= 4 else { exit(2) }
let mode = CommandLine.arguments[1]
let target = CommandLine.arguments[2]

if mode == "finder" {
  guard CommandLine.arguments.count == 4 else { exit(2) }
  let output = CommandLine.arguments[3]
  try writePNG(NSWorkspace.shared.icon(forFile: target), to: output)
  print("INTEGRA_FINDER_ICON: PASS")
} else if mode == "running" {
  guard CommandLine.arguments.count == 5 else { exit(2) }
  let expectedBundle = URL(fileURLWithPath: CommandLine.arguments[3]).standardizedFileURL
  let output = CommandLine.arguments[4]
  let deadline = Date().addingTimeInterval(10)
  var application: NSRunningApplication?
  repeat {
    application = NSRunningApplication.runningApplications(withBundleIdentifier: target).first {
      $0.bundleURL?.standardizedFileURL == expectedBundle
    }
    if application == nil { Thread.sleep(forTimeInterval: 0.1) }
  } while application == nil && Date() < deadline
  guard let application, application.activationPolicy == .regular, let icon = application.icon else {
    exit(3)
  }
  try writePNG(icon, to: output)
  print("INTEGRA_DOCK_CMDTAB_ICON: PASS activationPolicy=regular")
  if ProcessInfo.processInfo.environment["INTEGRA_ICON_PROBE_TERMINATE"] == "1" {
    guard application.forceTerminate() else { exit(5) }
    Thread.sleep(forTimeInterval: 0.2)
  }
} else {
  exit(4)
}
