import AppKit
import AVKit
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

    func call(_ operation: String, request: [String: Any] = [:]) throws -> Data {
        let allowed = ["workflow", "obsidian-preview", "onedrive-preview", "deferred", "projects", "create-project", "open-project", "jobs", "start-job", "cancel-job", "resume-job", "import-media", "media-preflight", "project-view", "package-preview", "package-publish"]
        guard allowed.contains(operation) else {
            throw BridgeError.failed("Unsupported operation")
        }
        let script = resources.appendingPathComponent("bridge.py")
        guard FileManager.default.fileExists(atPath: script.path) else { throw BridgeError.missingResource }
        let process = Process(); let output = Pipe(); let errors = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [script.path, operation]
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process.environment = environment
        process.standardOutput = output; process.standardError = errors
        if !request.isEmpty {
            let input = Pipe(); process.standardInput = input
            try process.run()
            input.fileHandleForWriting.write(try JSONSerialization.data(withJSONObject: request))
            try input.fileHandleForWriting.close()
        } else {
            try process.run()
        }
        process.waitUntilExit()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        if process.terminationStatus != 0 {
            if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let message = object["error"] as? String, !message.isEmpty { throw BridgeError.failed(message) }
            let stderr = errors.fileHandleForReading.readDataToEndOfFile()
            let detail = String(data: stderr, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            throw BridgeError.failed(detail.isEmpty ? "Integra service failed without diagnostic output" : detail)
        }
        guard !data.isEmpty else { throw BridgeError.invalidResponse }
        return data
    }

    func workflow() throws -> Workflow { try JSONDecoder().decode(WorkflowEnvelope.self, from: call("workflow")).workflow }
    func deferred() throws -> DeferredRegistry { try JSONDecoder().decode(DeferredEnvelope.self, from: call("deferred")).registry }
    func preview(_ operation: String) throws -> PreviewEnvelope { try JSONDecoder().decode(PreviewEnvelope.self, from: call(operation)) }
    func json(_ operation: String, request: [String: Any] = [:]) throws -> [String: Any] {
        let value = try JSONSerialization.jsonObject(with: call(operation, request: request))
        guard let object = value as? [String: Any], object["ok"] as? Bool == true else { throw BridgeError.invalidResponse }
        return object
    }
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
    private var activeProjectID: String?
    private var playerWindow: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let resources = Bundle.main.resourceURL else { NSApp.terminate(nil); return }
        bridge = Bridge(resources: resources)
        do { workflow = try bridge.workflow() } catch { fatalError("Closed Integra bridge failed: \(error)") }
        if let projects = try? bridge.json("projects")["result"] as? [[String:Any]], let latest=projects.last {
            activeProjectID=latest["project_id"] as? String
        }
        buildWindow()
        window.makeKeyAndOrderFront(nil)
        if let marker = ProcessInfo.processInfo.environment["INTEGRA_LAUNCH_PROBE"] {
            let proof = "LAUNCHED visible=\(window.isVisible) sections=\(workflow.sections.count) title=\(window.title)\n"
            try? proof.write(toFile: marker, atomically: true, encoding: .utf8)
            NSApp.terminate(nil)
        }
    }

    private func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1040, height: 680),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = activeProjectID == nil ? "Integra — New local project" : "Integra — Local project"
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
        if section.id == "projects" {
            let projects = (try? bridge.json("projects")["result"] as? [[String:Any]]) ?? []
            if let latest=projects.last {
                let name=latest["name"] as? String ?? "Local project"; let count=latest["source_count"] as? Int ?? 0
                text="Active local project: \(name)\nSources: \(count)\n\nChoose a video or audio file to copy it into Integra and start local transcription."
                window.title="Integra — \(name)"
            } else { text="No local project yet. Choose a video or audio file; Integra will create the project automatically." }
        }
        if section.id == "navigation" { text += "\n\nEntity: \(workflow.navigation.entity)\nLocator: \(workflow.navigation.source_locator)\nReverse: \(workflow.navigation.reverse_route)" }
        if section.id == "deferred", let registry = try? bridge.deferred() {
            text += "\n\n" + registry.features.map { "• \($0) — Later / Unavailable" }.joined(separator: "\n")
        }
        detail.string = text
        if section.id == "projects" { actionButton.title = "Choose video or audio"; actionButton.isHidden = false; actionButton.isEnabled = true }
        else if section.id == "operations" { actionButton.title = "Run local integrity job"; actionButton.isHidden = false; actionButton.isEnabled = true }
        else if ["transcript", "knowledge", "media"].contains(section.id) { actionButton.title = "Refresh project result"; actionButton.isHidden = false; actionButton.isEnabled = true }
        else if section.id == "navigation" { actionButton.title = "Open first exact media interval"; actionButton.isHidden = false; actionButton.isEnabled = true }
        else if section.id == "obsidian" { actionButton.title = "Choose package and export target"; actionButton.isHidden = false; actionButton.isEnabled = true }
        else if section.id == "onedrive" { actionButton.title = "Choose package and OneDrive folder"; actionButton.isHidden = false; actionButton.isEnabled = true }
        else { actionButton.isHidden = true; actionButton.isEnabled = false }
    }

    @objc private func runAction() {
        let id = workflow.sections[table.selectedRow].id
        do {
            if id == "projects" { try projectAction(); return }
            if id == "operations" { try operationAction(); return }
            if ["transcript", "knowledge", "media", "navigation"].contains(id) { try projectView(section: id); return }
            try publicationAction(kind: id)
        } catch { detail.string += "\n\nPreview failed safely: \(error)" }
    }

    private func projectAction() throws {
        let list = try bridge.json("projects")["result"] as? [[String: Any]] ?? []
        if let latest = list.last, let projectID = latest["project_id"] as? String { activeProjectID = projectID }
        else { let created = try bridge.json("create-project", request: ["name": "Integra Local Project"]); activeProjectID = (created["result"] as? [String:Any])?["project_id"] as? String }
        guard let projectID=activeProjectID else { throw BridgeError.invalidResponse }
        _ = try bridge.json("media-preflight")
        let panel=NSOpenPanel(); panel.title="Choose video or audio for local transcription"; panel.canChooseFiles=true; panel.canChooseDirectories=false
        guard panel.runModal() == .OK, let url=panel.url else { return }
        let job=try bridge.json("import-media",request:["project_id":projectID,"source_path":url.path])
        detail.string += "\n\nSource copied into Integra storage. Local transcription started:\n\(job["result"] ?? [:])\n\nOpen Transcript & Topics and press Refresh."
    }

    private func operationAction() throws {
        var list = try bridge.json("projects")["result"] as? [[String: Any]] ?? []
        if list.isEmpty { _ = try bridge.json("create-project", request: ["name": "Integra Local Project"]); list = try bridge.json("projects")["result"] as? [[String: Any]] ?? [] }
        guard let projectID = list.last?["project_id"] as? String else { throw BridgeError.invalidResponse }
        activeProjectID=projectID
        let jobs=try bridge.json("jobs",request:["project_id":projectID])["result"] as? [[String:Any]] ?? []
        if let current=jobs.last, current["kind"] as? String == "LOCAL_MEDIA_TRANSCRIPTION", let state=current["state"] as? String, let jobID=current["job_id"] as? String {
            if ["RUNNING","QUEUED"].contains(state) { let result=try bridge.json("cancel-job",request:["project_id":projectID,"job_id":jobID]); detail.string += "\n\nTranscription cancelled safely:\n\(result["result"] ?? [:])"; return }
            if ["CANCELLED","FAILED"].contains(state) { let result=try bridge.json("resume-job",request:["project_id":projectID,"job_id":jobID]); detail.string += "\n\nTranscription resumed from owned source:\n\(result["result"] ?? [:])"; return }
        }
        let job = try bridge.json("start-job", request: ["project_id": projectID])
        detail.string += "\n\nLocal integrity job completed with persisted result:\n\(job["result"] ?? [:])"
    }

    private func projectView(section: String) throws {
        if activeProjectID == nil { activeProjectID = ((try bridge.json("projects")["result"] as? [[String:Any]])?.last)?["project_id"] as? String }
        guard let projectID=activeProjectID else { throw BridgeError.failed("Create a project and choose media first") }
        let envelope=try bridge.json("project-view",request:["project_id":projectID]); guard let view=envelope["result"] as? [String:Any] else { throw BridgeError.invalidResponse }
        if let job=view["job"] as? [String:Any], job["state"] as? String != "COMPLETED" { detail.string="Job: \(job["state"] ?? "UNKNOWN") — \(job["progress"] ?? 0)%\n\(job["message"] ?? "")"; return }
        let key = section == "media" ? "transcript" : section
        let value = view[key] ?? view["job"] ?? [:]
        let data=try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys]); detail.string=String(data:data,encoding:.utf8) ?? ""
        if section == "navigation", let job=view["job"] as? [String:Any], let source=job["owned_path"] as? String,
           let navigation=view["navigation"] as? [String:Any], let route=(navigation["routes"] as? [[String:Any]])?.first,
           let locator=route["locator"] as? String { openMedia(path:source,locator:locator) }
    }

    private func openMedia(path: String, locator: String) {
        let pattern="#t=([0-9.]+),([0-9.]+)"; guard let regex=try? NSRegularExpression(pattern:pattern), let match=regex.firstMatch(in:locator,range:NSRange(locator.startIndex...,in:locator)),
              let startRange=Range(match.range(at:1),in:locator), let seconds=Double(locator[startRange]) else { return }
        let player=AVPlayer(url:URL(fileURLWithPath:path)); let view=AVPlayerView(frame:NSRect(x:0,y:0,width:760,height:460)); view.player=player; view.controlsStyle = .floating
        let window=NSWindow(contentRect:view.frame,styleMask:[.titled,.closable,.resizable],backing:.buffered,defer:false); window.title="Integra — exact source interval"; window.contentView=view; window.center(); window.makeKeyAndOrderFront(nil)
        player.seek(to:CMTime(seconds:seconds,preferredTimescale:1000),toleranceBefore:.zero,toleranceAfter:.zero); player.play(); playerWindow=window
    }

    private func publicationAction(kind: String) throws {
        if activeProjectID == nil { activeProjectID = ((try bridge.json("projects")["result"] as? [[String:Any]])?.last)?["project_id"] as? String }
        guard let projectID=activeProjectID, let view=(try bridge.json("project-view",request:["project_id":projectID])["result"] as? [String:Any]), let job=view["job"] as? [String:Any], var packagePath=job["package_dir"] as? String else { throw BridgeError.failed("Complete media transcription first") }
        if kind == "onedrive" { let pointer=URL(fileURLWithPath:packagePath).appendingPathComponent("onedrive_package.json"); let data=try Data(contentsOf:pointer); packagePath=(try JSONSerialization.jsonObject(with:data) as? [String:Any])?["package_dir"] as? String ?? packagePath }
        let packageURL=URL(fileURLWithPath:packagePath)
        let targetPanel = NSOpenPanel(); targetPanel.title = kind == "obsidian" ? "Choose Obsidian Vault" : "Choose filesystem-backed OneDrive folder"; targetPanel.canChooseDirectories = true; targetPanel.canChooseFiles = false
        guard targetPanel.runModal() == .OK, let targetURL = targetPanel.url else { return }
        let request = ["package_dir": packageURL.path, "target_dir": targetURL.path]
        let preview = try bridge.json("package-preview", request: request)
        detail.string += "\n\nVerified preview:\n\(preview["result"] ?? [:])"
        let alert = NSAlert(); alert.messageText = "Publish this verified package?"; alert.informativeText = "Integra writes only to its managed subtree. OneDrive local publication never means cloud verification."; alert.addButton(withTitle: "Publish"); alert.addButton(withTitle: "Cancel")
        if alert.runModal() == .alertFirstButtonReturn {
            let result = try bridge.json("package-publish", request: request)
            detail.string += "\n\nPublication result:\n\(result["result"] ?? [:])"
        }
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
