import AppKit
import Foundation

struct Section: Codable { let id: String; let title: String; let status: String; let summary: String }
struct Project: Codable { let id: String; let name: String; let source_count: Int }
struct Navigation: Codable { let entity: String; let source_locator: String; let reverse_route: String }
struct Workflow: Codable { let schema_version: String; let project: Project; let sections: [Section]; let navigation: Navigation }
struct WorkflowEnvelope: Codable { let schema_version: String; let ok: Bool; let operation: String; let workflow: Workflow }
struct DeferredRegistry: Codable { let schema_version: String; let status: String; let features: [String]; let actions_available: Bool }
struct DeferredEnvelope: Codable { let schema_version: String; let ok: Bool; let operation: String; let registry: DeferredRegistry }
struct PreviewEnvelope: Codable {
    let schema_version: String; let ok: Bool; let operation: String; let state: String
    let target: String; let writes_performed: Bool; let external_actions_performed: Bool; let cloud_verified: Bool
}

enum BridgeError: Error { case missingResource, failed(String), invalidResponse }

final class Bridge {
    private let resources: URL
    init(resources: URL) { self.resources = resources }

    func call(_ operation: String) throws -> Data {
        guard ["workflow", "obsidian-preview", "onedrive-preview", "deferred"].contains(operation) else {
            throw BridgeError.failed("Unsupported operation")
        }
        let script = resources.appendingPathComponent("bridge.py")
        guard FileManager.default.fileExists(atPath: script.path) else { throw BridgeError.missingResource }
        let process = Process(); let output = Pipe(); let errors = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [script.path, operation]
        process.standardOutput = output; process.standardError = errors
        try process.run(); process.waitUntilExit()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        if process.terminationStatus != 0 {
            let detail = String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "bridge failed"
            throw BridgeError.failed(detail)
        }
        guard !data.isEmpty else { throw BridgeError.invalidResponse }
        return data
    }

    func workflow() throws -> Workflow { try JSONDecoder().decode(WorkflowEnvelope.self, from: call("workflow")).workflow }
    func deferred() throws -> DeferredRegistry { try JSONDecoder().decode(DeferredEnvelope.self, from: call("deferred")).registry }
    func preview(_ operation: String) throws -> PreviewEnvelope { try JSONDecoder().decode(PreviewEnvelope.self, from: call(operation)) }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSTableViewDataSource, NSTableViewDelegate {
    private var window: NSWindow!
    private let table = NSTableView()
    private let titleLabel = NSTextField(labelWithString: "")
    private let statusLabel = NSTextField(labelWithString: "")
    private let detail = NSTextView()
    private let actionButton = NSButton(title: "", target: nil, action: nil)
    private var workflow: Workflow!
    private var bridge: Bridge!

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let resources = Bundle.main.resourceURL else { NSApp.terminate(nil); return }
        bridge = Bridge(resources: resources)
        do { workflow = try bridge.workflow() } catch { fatalError("Closed Integra bridge failed: \(error)") }
        buildWindow()
        window.makeKeyAndOrderFront(nil)
        if let marker = ProcessInfo.processInfo.environment["INTEGRA_LAUNCH_PROBE"] {
            try? "LAUNCHED\n".write(toFile: marker, atomically: true, encoding: .utf8)
            NSApp.terminate(nil)
        }
    }

    private func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1040, height: 680),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Integra — \(workflow.project.name)"
        window.center(); window.minSize = NSSize(width: 820, height: 520)

        let split = NSSplitView(); split.isVertical = true; split.dividerStyle = .thin
        split.translatesAutoresizingMaskIntoConstraints = false
        let sidebar = NSScrollView(); sidebar.hasVerticalScroller = true; sidebar.documentView = table
        sidebar.translatesAutoresizingMaskIntoConstraints = false
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("section")); column.width = 270
        table.addTableColumn(column); table.headerView = nil; table.delegate = self; table.dataSource = self
        table.rowHeight = 38; table.allowsEmptySelection = false

        let content = NSView(); content.translatesAutoresizingMaskIntoConstraints = false
        titleLabel.font = .systemFont(ofSize: 27, weight: .bold); titleLabel.translatesAutoresizingMaskIntoConstraints = false
        statusLabel.font = .systemFont(ofSize: 13, weight: .semibold); statusLabel.textColor = .secondaryLabelColor
        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        detail.isEditable = false; detail.drawsBackground = false; detail.font = .systemFont(ofSize: 15)
        detail.textContainerInset = NSSize(width: 2, height: 8)
        let detailScroll = NSScrollView(); detailScroll.documentView = detail; detailScroll.hasVerticalScroller = true
        detailScroll.translatesAutoresizingMaskIntoConstraints = false
        actionButton.target = self; actionButton.action = #selector(runAction); actionButton.bezelStyle = .rounded
        actionButton.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(titleLabel); content.addSubview(statusLabel); content.addSubview(detailScroll); content.addSubview(actionButton)
        NSLayoutConstraint.activate([
            titleLabel.topAnchor.constraint(equalTo: content.topAnchor, constant: 34), titleLabel.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 34), titleLabel.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -34),
            statusLabel.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 8), statusLabel.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            actionButton.topAnchor.constraint(equalTo: statusLabel.bottomAnchor, constant: 18), actionButton.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            detailScroll.topAnchor.constraint(equalTo: actionButton.bottomAnchor, constant: 18), detailScroll.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor), detailScroll.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -34), detailScroll.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -28)
        ])
        split.addArrangedSubview(sidebar); split.addArrangedSubview(content)
        sidebar.widthAnchor.constraint(equalToConstant: 280).isActive = true
        window.contentView = split
        table.selectRowIndexes(IndexSet(integer: 0), byExtendingSelection: false); render(0)
    }

    func numberOfRows(in tableView: NSTableView) -> Int { workflow.sections.count }
    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let field = NSTextField(labelWithString: workflow.sections[row].title)
        field.font = .systemFont(ofSize: 14, weight: .medium); field.lineBreakMode = .byTruncatingTail
        return field
    }
    func tableViewSelectionDidChange(_ notification: Notification) { if table.selectedRow >= 0 { render(table.selectedRow) } }

    private func render(_ row: Int) {
        let section = workflow.sections[row]; titleLabel.stringValue = section.title
        statusLabel.stringValue = section.status == "AVAILABLE" ? "AVAILABLE — governed local reference" : "LATER / UNAVAILABLE — read-only"
        var text = section.summary
        if section.id == "navigation" { text += "\n\nEntity: \(workflow.navigation.entity)\nLocator: \(workflow.navigation.source_locator)\nReverse: \(workflow.navigation.reverse_route)" }
        if section.id == "deferred", let registry = try? bridge.deferred() {
            text += "\n\n" + registry.features.map { "• \($0) — Later / Unavailable" }.joined(separator: "\n")
        }
        detail.string = text
        if section.id == "obsidian" { actionButton.title = "Run safe Obsidian preview"; actionButton.isHidden = false; actionButton.isEnabled = true }
        else if section.id == "onedrive" { actionButton.title = "Run safe OneDrive preview"; actionButton.isHidden = false; actionButton.isEnabled = true }
        else { actionButton.isHidden = true; actionButton.isEnabled = false }
    }

    @objc private func runAction() {
        let id = workflow.sections[table.selectedRow].id
        let operation = id == "obsidian" ? "obsidian-preview" : "onedrive-preview"
        do {
            let preview = try bridge.preview(operation)
            detail.string += "\n\nPreview: \(preview.state)\nWrites: \(preview.writes_performed)\nExternal actions: \(preview.external_actions_performed)\nCloud verified: \(preview.cloud_verified)"
        } catch { detail.string += "\n\nPreview failed safely: \(error)" }
    }
}

@main
struct IntegraApplication {
    @MainActor static func main() {
        if CommandLine.arguments.contains("--self-test") {
            guard let resources = Bundle.main.resourceURL else { exit(2) }
            do {
                let bridge = Bridge(resources: resources); let workflow = try bridge.workflow(); let deferred = try bridge.deferred()
                guard workflow.sections.count == 9, deferred.actions_available == false,
                      workflow.sections.last?.status == "LATER_UNAVAILABLE" else { exit(3) }
                print("INTEGRA_MACOS_SELF_TEST: PASS"); exit(0)
            } catch { print("INTEGRA_MACOS_SELF_TEST: FAIL \(error)"); exit(4) }
        }
        let app = NSApplication.shared
        let delegate = AppDelegate(); app.delegate = delegate
        app.setActivationPolicy(.regular); app.activate(ignoringOtherApps: true); app.run()
    }
}
