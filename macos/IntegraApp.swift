import AppKit
import AVFoundation
import AVKit
import Foundation

enum BridgeError: Error, LocalizedError {
  case missingResource
  case failed(String)
  case invalidResponse
  var errorDescription: String? {
    switch self {
    case .missingResource: return "В приложении отсутствует локальный сервис."
    case .failed(let value): return value
    case .invalidResponse: return "Локальный сервис вернул некорректный ответ."
    }
  }
}

// Validate before ending the native modal session. A failed check must not
// dismiss/re-run NSAlert or discard the user's in-memory decisions.
final class KnowledgeReviewDialog: NSObject {
  let alert = NSAlert()
  let feedback = NSTextField(wrappingLabelWithString: "")
  var validate: () -> String? = { nil }
  var invalidField: NSView?

  func accessory(_ scroll: NSScrollView) -> NSView {
    let view = NSView(frame: NSRect(x: 0, y: 0, width: 660, height: 500))
    feedback.frame = NSRect(x: 0, y: 444, width: 640, height: 56)
    scroll.frame = NSRect(x: 0, y: 0, width: 660, height: 440)
    view.addSubview(feedback); view.addSubview(scroll)
    return view
  }

  func configure(primaryTitle: String) {
    feedback.textColor = .systemRed
    alert.addButton(withTitle: primaryTitle)
    alert.addButton(withTitle: "Отмена")
    alert.layout()
    alert.buttons[0].target = self
    alert.buttons[0].action = #selector(submit)
  }

  func validateSubmission() -> Bool {
    if let message = validate() {
      feedback.stringValue = message
      if let field = invalidField {
        field.scrollToVisible(field.bounds)
        alert.window.makeFirstResponder(field)
      }
      return false
    }
    feedback.stringValue = ""
    return true
  }

  // Input checks used by the real review form and the native regression probe.
  func validateReview(reviewer: NSTextField,
                      entries: [(NSPopUpButton, NSTextField, Bool, Bool)]) -> String? {
    if reviewer.stringValue.range(of: "^[a-z][a-z0-9._:-]{2,127}$", options: .regularExpression) == nil {
      invalidField = reviewer
      return "Введите ID проверяющего латиницей (3–128 символов). Решения сохранены в этой форме."
    }
    for (index, entry) in entries.enumerated() {
      if entry.0.indexOfSelectedItem == 0 {
        invalidField = entry.0
        return "Предложение \(index + 1): выберите решение."
      }
      if entry.1.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        invalidField = entry.1
        return "Предложение \(index + 1): заполните обоснование решения."
      }
      if entry.0.indexOfSelectedItem == 1 && entry.2 {
        invalidField = entry.0
        return "Предложение \(index + 1): поля изменены — выберите «Изменить и принять» или восстановите исходные значения."
      }
      if entry.0.indexOfSelectedItem == 2 && !entry.3 {
        invalidField = entry.0
        return "Предложение \(index + 1): изменение не поддерживается. Выберите принять, отклонить или отложить."
      }
    }
    return nil
  }

  @objc func submit() {
    guard validateSubmission() else { return }
    NSApp.stopModal(withCode: .alertFirstButtonReturn)
    alert.window.orderOut(nil)
  }

  func run() -> NSApplication.ModalResponse { alert.runModal() }
}

final class Bridge: @unchecked Sendable {
  private let resources: URL
  init(resources: URL) { self.resources = resources }
  func call(_ operation: String, request: [String: Any] = [:]) throws -> Data {
    let allowed = [
      "workflow", "deferred", "projects", "create-project", "open-project", "jobs", "start-job",
      "cancel-job", "resume-job", "import-media", "media-preflight", "seminartext-preflight", "project-view",
      "detect-sources", "discover-folder-sources", "discover-zoom-folder-sources", "discover-youtube-playlist", "capability-registry", "build-plan", "execute-plan", "run-status",
      "recent-runs", "available-packages", "cancel-run", "retry-run", "media-navigation", "create-media-clip", "build-reviewed-package", "package-preview", "package-publish",
      "obsidian-preview", "transcript-text", "translate-transcript", "translate-topics", "topic-translation",
      "onedrive-preview",
      "prepare-transcript-review", "apply-transcript-review", "prepare-topic-review",
      "prepare-process-topic-review", "apply-process-topic-review", "process-topics",
      "prepare-knowledge-review", "apply-knowledge-review", "create-machine-evidence",
      "knowledge-sources", "knowledge-open", "knowledge-save", "knowledge-navigation", "knowledge-package",
      "knowledge-k2-open", "knowledge-k2-prepare", "knowledge-k2-apply", "knowledge-k2-navigation", "knowledge-k2-package",
      "shutdown-active-runs",
    ]
    guard allowed.contains(operation) else { throw BridgeError.failed("Unsupported operation") }
    let script = resources.appendingPathComponent("bridge.py")
    guard FileManager.default.fileExists(atPath: script.path) else {
      throw BridgeError.missingResource
    }
    let process = Process()
    let output = Pipe()
    let errors = Pipe()
    let input = Pipe()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    process.arguments = [script.path, operation]
    var environment = ProcessInfo.processInfo.environment
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process.environment = environment
    process.standardOutput = output
    process.standardError = errors
    process.standardInput = input
    try process.run()
    input.fileHandleForWriting.write(try JSONSerialization.data(withJSONObject: request))
    try input.fileHandleForWriting.close()
    // Drain review packages while the child runs; a large JSON response can
    // otherwise fill the pipe and prevent the process from ever exiting.
    let data = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    if process.terminationStatus != 0 {
      if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let message = object["error"] as? String, !message.isEmpty
      {
        throw BridgeError.failed(message)
      }
      let stderr =
        String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      throw BridgeError.failed(
        stderr.isEmpty ? "Integra service failed without diagnostic output" : stderr)
    }
    guard !data.isEmpty else { throw BridgeError.invalidResponse }
    return data
  }
  func json(_ operation: String, request: [String: Any] = [:]) throws -> [String: Any] {
    guard
      let object = try JSONSerialization.jsonObject(with: call(operation, request: request))
        as? [String: Any], object["ok"] as? Bool == true
    else { throw BridgeError.invalidResponse }
    return object
  }
}

final class DropBox: NSBox {
  var receive: (([String]) -> Void)?
  override init(frame frameRect: NSRect) {
    super.init(frame: frameRect)
    boxType = .custom
    cornerRadius = 10
    borderWidth = 1
    borderColor = .separatorColor
    title = "Перетащите файлы сюда"
    titlePosition = .atTop
    let label = NSTextField(labelWithString: "Перетащите файлы сюда")
    label.font = .systemFont(ofSize: 15, weight: .medium)
    label.textColor = .secondaryLabelColor
    label.translatesAutoresizingMaskIntoConstraints = false
    addSubview(label)
    NSLayoutConstraint.activate([
      label.centerXAnchor.constraint(equalTo: centerXAnchor),
      label.centerYAnchor.constraint(equalTo: centerYAnchor),
    ])
    registerForDraggedTypes([.fileURL])
  }
  required init?(coder: NSCoder) { fatalError() }
  override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation { .copy }
  override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
    let options: [NSPasteboard.ReadingOptionKey: Any] = [.urlReadingFileURLsOnly: true]
    guard
      let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: options)
        as? [URL], !urls.isEmpty
    else { return false }
    receive?(urls.map(\.path))
    return true
  }
}

final class FlippedStackView: NSStackView {
  override var isFlipped: Bool { true }
}

final class TranslationButton: NSButton {
  var projectID = ""
  var sourceRunID = ""
  var sourceID = ""
  var targetLanguage = ""
}

final class TranslationTargetPicker: NSPopUpButton {
  weak var translationButton: TranslationButton?
}

final class ResponsiveResultsGrid: NSStackView {
  static let wideBreakpoint: CGFloat = 720
  let leftColumn = NSStackView()
  let rightColumn = NSStackView()

  override init(frame frameRect: NSRect) {
    super.init(frame: frameRect)
    for column in [leftColumn, rightColumn] {
      column.orientation = .vertical
      column.alignment = .leading
      column.spacing = 12
      addArrangedSubview(column)
    }
    alignment = .top
    distribution = .fillEqually
    spacing = 16
    updateColumns()
  }
  required init?(coder: NSCoder) { fatalError() }
  override func layout() {
    super.layout()
    updateColumns()
  }
  private func updateColumns() {
    let target: NSUserInterfaceLayoutOrientation = bounds.width >= Self.wideBreakpoint ? .horizontal : .vertical
    if orientation != target { orientation = target }
  }
}

final class TechnicalDisclosure: NSStackView {
  private let toggle = NSButton(checkboxWithTitle: "Технические данные", target: nil, action: nil)
  let details = NSStackView()

  override init(frame frameRect: NSRect) {
    super.init(frame: frameRect)
    orientation = .vertical
    alignment = .leading
    spacing = 8
    toggle.target = self
    toggle.action = #selector(setExpanded(_:))
    toggle.state = .off
    details.orientation = .vertical
    details.alignment = .leading
    details.spacing = 6
    details.isHidden = true
    addArrangedSubview(toggle)
    addArrangedSubview(details)
  }
  required init?(coder: NSCoder) { fatalError() }
  @objc private func setExpanded(_ sender: NSButton) { details.isHidden = sender.state != .on }
}

struct SidebarItem {
  let title: String
  let id: String
  let header: Bool
  let enabled: Bool
}

  @MainActor
  final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSTableViewDataSource, NSTableViewDelegate
  {
  private var window: NSWindow!, bridge: Bridge!
  private let sidebar = NSTableView(), content = FlippedStackView(),
    status = NSTextField(labelWithString: "")
  private var sources = [[String: Any]](), capabilities = [[String: Any]](),
    selected = Set<String>(), plan: [String: Any]?
  private var recognitionMode = "normal"
  private var sourceSpeechLanguage = "ru"
  private var topicDetail = "auto"
  private var projectID: String?, runID: String?, timer: Timer?
  private var mediaPlayer: AVPlayer?, mediaWindow: NSWindow?
  private var reviewPlayer: AVPlayer?
  private var terminationPending = false
  private var retryPending = false
  private var cancelPending = false
  private var operationsVisible = false
  private var navigationGeneration = 0
  private var operationsRequestID: UUID?
  private var operationsSnapshot: Data?
  private var operationsError = ""
  private var completedOperationsPolls = 0
  private let operationsQueue = DispatchQueue(label: "Integra.operations-read", qos: .userInitiated)
  private let serviceQueue = DispatchQueue(label: "Integra.native-services", qos: .userInitiated)
  private let items: [SidebarItem] = [
    .init(title: "INTEGRA", id: "", header: true, enabled: false),
    .init(title: "＋ Новая обработка", id: "new", header: false, enabled: true),
    .init(title: "БИБЛИОТЕКА", id: "", header: true, enabled: false),
    .init(title: "Исходники", id: "sources", header: false, enabled: true),
    .init(title: "Проекты", id: "projects", header: false, enabled: true),
    .init(title: "Обработанные материалы", id: "materials", header: false, enabled: true),
    .init(title: "РАБОТА", id: "", header: true, enabled: false),
    .init(title: "Выполняется", id: "operations", header: false, enabled: true),
    .init(title: "Требует проверки — В разработке", id: "review", header: false, enabled: false),
    .init(title: "ЗНАНИЯ", id: "", header: true, enabled: false),
    .init(title: "База знаний", id: "knowledge", header: false, enabled: true),
    .init(title: "Поиск — В разработке", id: "search", header: false, enabled: false),
    .init(title: "СОЗДАТЬ", id: "", header: true, enabled: false),
    .init(title: "Видео и клипы — В разработке", id: "clips", header: false, enabled: false),
    .init(title: "Учебные материалы — В разработке", id: "learning", header: false, enabled: false),
    .init(title: "Маркетинг — В разработке", id: "marketing", header: false, enabled: false),
    .init(title: "ПУБЛИКАЦИЯ", id: "", header: true, enabled: false),
    .init(title: "Готово", id: "ready", header: false, enabled: true),
    .init(title: "История", id: "history", header: false, enabled: true),
    .init(title: "SYSTEM", id: "", header: true, enabled: false),
    .init(title: "Диагностика", id: "diagnostics", header: false, enabled: true),
    .init(title: "Настройки — В разработке", id: "settings", header: false, enabled: false),
  ]

  func applicationDidFinishLaunching(_ notification: Notification) {
    if CommandLine.arguments.contains("--ui-probe-dark") {
      NSApp.appearance = NSAppearance(named: .darkAqua)
    }
    guard let resources = Bundle.main.resourceURL else {
      NSApp.terminate(nil)
      return
    }
    bridge = Bridge(resources: resources)
    if let recent = try? bridge.json("recent-runs")["result"] as? [[String: Any]],
      let latest = recent.first, let project = latest["project"] as? [String: Any],
      let run = latest["run"] as? [String: Any]
    {
      projectID = project["project_id"] as? String
      runID = run["run_id"] as? String
    }
    buildMenu()
    buildWindow()
    renderNew()
    window.makeKeyAndOrderFront(nil)
    if let index = CommandLine.arguments.firstIndex(of: "--ui-probe-source"),
      CommandLine.arguments.indices.contains(index + 1)
    {
      detect([CommandLine.arguments[index + 1]])
    }
    if let marker = ProcessInfo.processInfo.environment["INTEGRA_LAUNCH_PROBE"] {
      try? "LAUNCHED visible=\(window.isVisible) workflow=source-first title=\(window.title)\n"
        .write(toFile: marker, atomically: true, encoding: .utf8)
      NSApp.terminate(nil)
    } else if ProcessInfo.processInfo.environment["INTEGRA_CLOSE_PROBE"] != nil {
      DispatchQueue.main.async { self.window.performClose(nil) }
    } else if ProcessInfo.processInfo.environment["INTEGRA_QUIT_PROBE"] != nil {
      DispatchQueue.main.async {
        guard let event = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [.command], timestamp: 0, windowNumber: self.window.windowNumber, context: nil, characters: "q", charactersIgnoringModifiers: "q", isARepeat: false, keyCode: 12) else { return }
        _ = NSApp.mainMenu?.performKeyEquivalent(with: event)
      }
    }
    runOperationsProbeIfRequested()
    if let url = pendingKnowledgeURL { pendingKnowledgeURL = nil; openKnowledgeURL(url) }
  }

  private var pendingKnowledgeURL: URL?
  func application(_ application: NSApplication, open urls: [URL]) {
    guard urls.count == 1, let url = urls.first else { return }
    if bridge == nil { pendingKnowledgeURL = url } else { openKnowledgeURL(url) }
  }

  private func openKnowledgeURL(_ url: URL) {
    guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
      components.scheme == "integra", components.host == "knowledge", components.path == "/fragment",
      components.user == nil, components.password == nil, components.port == nil,
      let queries = components.queryItems, queries.count == 6 else { status.stringValue = "Недопустимая ссылка на источник"; return }
    let required: Set<String> = ["project_id", "run_id", "source_id", "fragment_id", "source_revision_sha256", "notebook_id"]
    guard Set(queries.map { $0.name }) == required, queries.allSatisfy({ $0.value != nil }) else { status.stringValue = "Неполная ссылка на источник"; return }
    let request = Dictionary(uniqueKeysWithValues: queries.map { ($0.name, $0.value! as Any) })
    window.makeKeyAndOrderFront(nil)
    presentKnowledgeNavigation(request)
  }

  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
  func windowShouldClose(_ sender: NSWindow) -> Bool {
    NSApp.terminate(nil)
    return false
  }
  func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
    guard !terminationPending else { return .terminateLater }
    terminationPending = true
    window.ignoresMouseEvents = true
    timer?.invalidate()
    status.stringValue = "Останавливаю активную обработку перед закрытием…"
    let service = bridge!
    serviceQueue.async {
      do {
        let result = try service.json("shutdown-active-runs")["result"] as? [String: Any]
        guard result?["state"] as? String == "SHUTDOWN_READY" else {
          throw BridgeError.failed("Остановка обработки не подтверждена.")
        }
        // terminateLater can run AppKit's modal loop, which does not drain the
        // main dispatch queue. Deliver its reply in that run-loop mode too.
        RunLoop.main.perform(inModes: [.default, .modalPanel, .eventTracking]) {
          MainActor.assumeIsolated { NSApp.reply(toApplicationShouldTerminate: true) }
        }
      } catch {
        let message = error.localizedDescription
        RunLoop.main.perform(inModes: [.default, .modalPanel, .eventTracking]) {
          MainActor.assumeIsolated {
            self.terminationPending = false
            self.window.ignoresMouseEvents = false
            NSApp.reply(toApplicationShouldTerminate: false)
            self.window.makeKeyAndOrderFront(nil)
            self.status.textColor = .systemRed
            self.status.stringValue = "Не удалось безопасно остановить обработку: \(message). Приложение осталось открытым."
            self.operationsError = self.status.stringValue
            if self.operationsVisible { self.startPolling() }
            if let marker = ProcessInfo.processInfo.environment["INTEGRA_SHUTDOWN_FAILURE_PROBE"] {
              try? self.status.stringValue.write(toFile: marker, atomically: true, encoding: .utf8)
            }
          }
        }
      }
    }
    return .terminateLater
  }

  func applicationWillTerminate(_ notification: Notification) {
    timer?.invalidate()
    if let marker = ProcessInfo.processInfo.environment["INTEGRA_CLOSE_PROBE"] {
      try? "TERMINATED_AFTER_LAST_WINDOW_CLOSED\n"
        .write(toFile: marker, atomically: true, encoding: .utf8)
    }
    if let marker = ProcessInfo.processInfo.environment["INTEGRA_QUIT_PROBE"] {
      try? "TERMINATED_AFTER_CONFIRMED_SHUTDOWN\n".write(toFile: marker, atomically: true, encoding: .utf8)
    }
  }

  private func buildMenu() {
    let menu = NSMenu()
    let appItem = NSMenuItem()
    let appMenu = NSMenu(title: "Integra")
    let quit = NSMenuItem(title: "Завершить Integra", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
    quit.target = NSApp
    appMenu.addItem(quit)
    appItem.submenu = appMenu
    menu.addItem(appItem)
    let editItem = NSMenuItem()
    let editMenu = NSMenu(title: "Правка")
    for (title, action, key) in [("Вырезать", "cut:", "x"), ("Копировать", "copy:", "c"), ("Вставить", "paste:", "v"), ("Выделить всё", "selectAll:", "a")] {
      editMenu.addItem(NSMenuItem(title: title, action: NSSelectorFromString(action), keyEquivalent: key))
    }
    editItem.submenu = editMenu
    menu.addItem(editItem)
    NSApp.mainMenu = menu
  }

  private func buildWindow() {
    window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 1320, height: 760),
      styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
      backing: .buffered, defer: false)
    window.title = "Integra — Новая обработка"
    window.isReleasedWhenClosed = false
    window.delegate = self
    window.minSize = NSSize(width: 1080, height: 620)
    window.center()
    window.toolbar = NSToolbar(identifier: "IntegraToolbar")
    let split = NSSplitView()
    split.isVertical = true
    split.dividerStyle = .thin
    let sideScroll = NSScrollView()
    sideScroll.hasVerticalScroller = true
    sideScroll.documentView = sidebar
    let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("sidebar"))
    column.width = 360
    sidebar.addTableColumn(column)
    sidebar.headerView = nil
    sidebar.delegate = self
    sidebar.dataSource = self
    sidebar.rowHeight = 31
    sidebar.backgroundColor = .windowBackgroundColor
    let contentScroll = NSScrollView()
    contentScroll.hasVerticalScroller = true
    contentScroll.drawsBackground = true
    contentScroll.backgroundColor = .windowBackgroundColor
    content.orientation = .vertical
    content.alignment = .leading
    content.spacing = 14
    content.edgeInsets = NSEdgeInsets(top: 34, left: 38, bottom: 36, right: 38)
    content.translatesAutoresizingMaskIntoConstraints = false
    contentScroll.documentView = content
    NSLayoutConstraint.activate([
      content.widthAnchor.constraint(equalTo: contentScroll.contentView.widthAnchor),
      content.leadingAnchor.constraint(equalTo: contentScroll.contentView.leadingAnchor),
      content.topAnchor.constraint(equalTo: contentScroll.contentView.topAnchor),
    ])
    split.addArrangedSubview(sideScroll)
    split.addArrangedSubview(contentScroll)
    sideScroll.widthAnchor.constraint(equalToConstant: 370).isActive = true
    window.contentView = split
    sidebar.selectRowIndexes(IndexSet(integer: 1), byExtendingSelection: false)
  }

  func numberOfRows(in tableView: NSTableView) -> Int { items.count }
  func tableView(_ tableView: NSTableView, shouldSelectRow row: Int) -> Bool { items[row].enabled }
  func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView?
  {
    let item = items[row]
    let label = NSTextField(labelWithString: item.title)
    label.font =
      item.header
      ? .systemFont(ofSize: 11, weight: .bold) : .systemFont(ofSize: 14, weight: .medium)
    label.textColor =
      item.header ? .secondaryLabelColor : (item.enabled ? .labelColor : .tertiaryLabelColor)
    return label
  }
  func tableViewSelectionDidChange(_ notification: Notification) {
    let row = sidebar.selectedRow
    if row < 0 { return }
    switch items[row].id {
    case "new": renderNew()
    case "projects": renderProjects()
    case "sources": renderSources()
    case "history": renderHistory()
    case "operations": renderOperations()
    case "materials", "ready": renderOutputs()
    case "knowledge": renderKnowledge()
    case "diagnostics": renderDiagnostics()
    default: break
    }
  }

  private func reset(_ title: String, _ subtitle: String, preservingOperations: Bool = false) {
    if !preservingOperations {
      navigationGeneration += 1
      operationsVisible = false
      operationsSnapshot = nil
      operationsError = ""
      timer?.invalidate()
      timer = nil
    }
    content.arrangedSubviews.forEach {
      content.removeArrangedSubview($0)
      $0.removeFromSuperview()
    }
    let heading = NSTextField(labelWithString: title)
    heading.font = .systemFont(ofSize: 30, weight: .bold)
    add(heading)
    let explanation = NSTextField(wrappingLabelWithString: subtitle)
    explanation.font = .systemFont(ofSize: 14)
    explanation.textColor = .secondaryLabelColor
    explanation.maximumNumberOfLines = 0
    add(explanation)
    status.stringValue = ""
    status.textColor = .systemRed
    status.maximumNumberOfLines = 0
    add(status)
  }
  private func add(_ view: NSView) {
    view.translatesAutoresizingMaskIntoConstraints = false
    content.addArrangedSubview(view)
    view.widthAnchor.constraint(lessThanOrEqualTo: content.widthAnchor, constant: -76).isActive =
      true
  }
  private func button(_ title: String, _ action: Selector, enabled: Bool = true) -> NSButton {
    let value = NSButton(title: title, target: self, action: action)
    value.bezelStyle = .rounded
    value.isEnabled = enabled
    return value
  }
  private func stageLabel(_ stage: String) -> String {
    switch stage {
    case "media_preparation": return "Подготовка аудио"
    case "transcript": return "Расшифровка"
    case "subtitles": return "Субтитры"
    case "word_timeline": return "Word Timeline"
    case "translation": return "Перевод"
    case "topics": return "Темы и таймкоды"
    case "audio_enhancement": return "Улучшение звука"
    case "document_analysis": return "Анализ документа"
    case "ocr": return "OCR BookText / Surya"
    default: return stage
    }
  }
  private func sourcePresentationDetail(_ source: [String: Any]) -> String {
    // Source-type identifiers are contract/persistence values.  The normal
    // user-facing source list uses the established product label instead.
    switch source["source_type"] as? String {
    case "YOUTUBE_VIDEO": return "YouTube"
    case "YOUTUBE_PLAYLIST": return "Плейлист YouTube"
    default: return source["source_type"] as? String ?? "Источник"
    }
  }
  private func section(_ value: String) -> NSTextField {
    let label = NSTextField(labelWithString: value)
    label.font = .systemFont(ofSize: 12, weight: .bold)
    label.textColor = .secondaryLabelColor
    return label
  }
  private func row(_ title: String, detail: String) -> NSView {
    let stack = NSStackView()
    stack.orientation = .vertical
    stack.alignment = .leading
    stack.spacing = 2
    let first = NSTextField(labelWithString: title)
    first.font = .systemFont(ofSize: 14, weight: .medium)
    let second = NSTextField(labelWithString: detail)
    second.font = .systemFont(ofSize: 12)
    second.textColor = .secondaryLabelColor
    stack.addArrangedSubview(first)
    stack.addArrangedSubview(second)
    return stack
  }

  private func renderNew() {
    reset(
      "Новая обработка",
      "Сначала добавьте источник. Integra определит тип, покажет только применимые результаты и сам рассчитает технические зависимости."
    )
    let actions = NSStackView()
    actions.orientation = .horizontal
    actions.spacing = 10
    actions.addArrangedSubview(button("Видео или аудио с Mac", #selector(chooseMedia)))
    actions.addArrangedSubview(button("Документ с Mac", #selector(chooseDocument)))
    actions.addArrangedSubview(button("Несколько файлов", #selector(chooseMultiple)))
    actions.addArrangedSubview(button("Папка с Mac", #selector(chooseFolder)))
    actions.addArrangedSubview(button("Папка Zoom", #selector(chooseZoomFolder)))
    actions.addArrangedSubview(button("YouTube", #selector(addYouTube)))
    add(actions)
    let drop = DropBox(frame: NSRect(x: 0, y: 0, width: 760, height: 92))
    drop.receive = { [weak self] values in self?.detect(values) }
    add(drop)
    drop.heightAnchor.constraint(equalToConstant: 92).isActive = true
    if sources.isEmpty {
      let empty = NSTextField(labelWithString: "Источники ещё не добавлены")
      empty.textColor = .secondaryLabelColor
      add(empty)
      return
    }
    add(section("ИСТОЧНИКИ"))
    for source in sources {
      add(
        row(
          "\(source["display_name"] ?? "Источник")", detail: sourcePresentationDetail(source)
        ))
    }
    if sources.contains(where: { ($0["kind"] as? String) == "MEDIA" || ($0["source_type"] as? String) == "YOUTUBE_VIDEO" }) {
      let mode = NSSegmentedControl(labels: ["Обычный", "Тщательный"], trackingMode: .selectOne, target: self, action: #selector(changeRecognitionMode(_:)))
      mode.selectedSegment = recognitionMode == "careful" ? 1 : 0
      let language = NSPopUpButton()
      language.addItem(withTitle: "Русский")
      language.selectItem(at: 0)
      language.target = self
      language.action = #selector(changeSourceSpeechLanguage(_:))
      add(row("Язык исходной речи", detail: "Русский — единственный язык, поддерживаемый текущим режимом распознавания."))
      add(language)
      add(row("Режим распознавания", detail: "Выберите тщательный режим, когда важнее полнота распознавания, чем скорость."))
      add(mode)
    }
    if selected.contains("topics") {
      let detail = NSSegmentedControl(labels: ["Крупно", "Обычно", "Подробно"], trackingMode: .selectOne, target: self, action: #selector(changeTopicDetail(_:)))
      detail.selectedSegment = topicDetail == "low" ? 0 : topicDetail == "high" ? 2 : 1
      add(row("Детализация тем", detail: "Выбор задаёт реальную детализацию тематического таймкодинга для этой обработки."))
      add(detail)
    }
    if sources.contains(where: { $0["source_type"] as? String == "PDF" }) {
      add(button("Страницы OCR BookText…", #selector(configureOCRPages)))
      if let source = sources.first(where: { $0["source_type"] as? String == "PDF" }) {
        add(row("Выбор страниц OCR", detail: "Включить: \(source["booktext_pages"] as? String ?? "все") · исключить: \(source["booktext_exclude_pages"] as? String ?? "нет"). Нумерация оригинала сохраняется."))
      }
    }
    add(section("ЧТО НУЖНО ПОЛУЧИТЬ?"))
    var category = ""
    for cap in capabilities {
      let next = cap["category"] as? String ?? ""
      if next != category {
        category = next
        let label = NSTextField(labelWithString: category)
        label.font = .systemFont(ofSize: 14, weight: .semibold)
        add(label)
      }
      let available =
        (cap["implementation_state"] as? String == "IMPLEMENTED"
          && cap["runtime_available"] as? Bool == true)
      let id = cap["id"] as? String ?? ""
      let suffix = available ? "" : " — \(cap["ui_state"] ?? "В разработке")"
      let check = NSButton(
        checkboxWithTitle: "\(cap["title"] ?? id)\(suffix)", target: self,
        action: #selector(toggleCapability(_:)))
      check.identifier = NSUserInterfaceItemIdentifier(id)
      check.isEnabled = available
      check.state = selected.contains(id) ? .on : .off
      add(check)
    }
    if let plan = plan {
      add(section("ПЛАН ВЫПОЛНЕНИЯ"))
      for (index, stage) in ((plan["stages"] as? [[String: Any]]) ?? []).enumerated() {
        add(
          row(
            "\(index+1). \(stage["title"] ?? "Этап")",
            detail: stage["technical"] as? Bool == true
              ? "автоматическая зависимость" : "выбранный результат"))
      }
    }
    let execute = button("Выполнить", #selector(execute), enabled: plan != nil)
    execute.keyEquivalent = "\r"
    add(execute)
    saveSnapshotIfRequested()
  }

  private func saveSnapshotIfRequested() {
    guard let path = ProcessInfo.processInfo.environment["INTEGRA_UI_SNAPSHOT"],
      let view = window.contentView
    else { return }
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
      guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
      view.cacheDisplay(in: view.bounds, to: bitmap)
      if let data = bitmap.representation(using: .png, properties: [:]) {
        try? data.write(to: URL(fileURLWithPath: path), options: .atomic)
      }
    }
  }

  @objc private func chooseMedia() { chooseFiles(multiple: false) }
  @objc private func chooseDocument() { chooseFiles(multiple: false) }
  @objc private func chooseMultiple() { chooseFiles(multiple: true) }
  @objc private func configureOCRPages() {
    let alert = NSAlert()
    alert.messageText = "Страницы для OCR"
    alert.informativeText = "Для всех выбранных PDF. Формат: 1-3,5. Пустое поле — все страницы. Это выбор OCR, не удаление страниц оригинала."
    let fields = NSStackView(); fields.orientation = .vertical
    let include = NSTextField(frame: NSRect(x: 0, y: 0, width: 360, height: 24))
    include.placeholderString = "Включить страницы, например 1-3,5"
    let exclude = NSTextField(frame: NSRect(x: 0, y: 0, width: 360, height: 24))
    exclude.placeholderString = "Исключить страницы, например 2"
    fields.addArrangedSubview(include); fields.addArrangedSubview(exclude)
    alert.accessoryView = fields
    alert.addButton(withTitle: "Применить"); alert.addButton(withTitle: "Отмена")
    guard alert.runModal() == .alertFirstButtonReturn else { return }
    for index in sources.indices where sources[index]["source_type"] as? String == "PDF" {
      sources[index]["booktext_pages"] = include.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
      sources[index]["booktext_exclude_pages"] = exclude.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    plan = nil
    selected = []
    renderNew()
  }
  private func chooseFiles(multiple: Bool) {
    let panel = NSOpenPanel()
    panel.title = multiple ? "Выберите несколько источников" : "Выберите источник"
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = multiple
    guard panel.runModal() == .OK else { return }
    detect(panel.urls.map(\.path))
  }
  @objc private func chooseFolder() { presentFolderPicker(zoom: false) }
  @objc private func chooseZoomFolder() { presentFolderPicker(zoom: true) }
  private func presentFolderPicker(zoom: Bool) {
    let panel = NSOpenPanel()
    panel.title = zoom ? "Выберите папку с записью Zoom" : "Выберите папку с материалами"
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    guard panel.runModal() == .OK, let folder = panel.url?.path else { return }
    status.textColor = .secondaryLabelColor
    status.stringValue = zoom ? "Ищу записи Zoom в папке…" : "Ищу поддерживаемые источники в папке…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let operation = zoom ? "discover-zoom-folder-sources" : "discover-folder-sources"
        let discovery = try bridge.json(operation, request: ["folder": folder])["result"] as? [String: Any] ?? [:]
        DispatchQueue.main.async { self.confirmFolderDiscovery(discovery, zoom: zoom) }
      } catch {
        DispatchQueue.main.async {
          self.status.textColor = .systemRed
          self.status.stringValue = error.localizedDescription
        }
      }
    }
  }
  private func confirmFolderDiscovery(_ discovery: [String: Any], zoom: Bool = false) {
    let discovered = discovery["sources"] as? [[String: Any]] ?? []
    let folder = (discovery["folder"] as? [String: Any])?["name"] as? String ?? "выбранной папке"
    let ignored = discovery["ignored"] as? [[String: Any]] ?? []
    guard !discovered.isEmpty else {
      status.textColor = .systemRed
      status.stringValue = zoom ? "В папке «\(folder)» не найдено записей Zoom." : "В папке «\(folder)» не найдено поддерживаемых файлов."
      return
    }
    let names = discovered.prefix(12).map { $0["display_name"] as? String ?? "Источник" }
    let tail = discovered.count > names.count ? "\nи ещё \(discovered.count - names.count)." : ""
    let alert = NSAlert()
    alert.messageText = zoom ? "Подтвердите записи Zoom" : "Подтвердите источники"
    let prefix = zoom ? "Записи Zoom из папки" : "Папка"
    alert.informativeText = "\(prefix) «\(folder)». Будут добавлены \(discovered.count) файлов в этом порядке:\n\(names.joined(separator: "\n"))\(tail)\n\nНе поддерживаются или исключены: \(ignored.count)."
    alert.addButton(withTitle: "Добавить \(discovered.count) источников")
    alert.addButton(withTitle: "Отмена")
    guard alert.runModal() == .alertFirstButtonReturn else { return }
    applyDetected(discovered)
  }
  @objc private func changeRecognitionMode(_ sender: NSSegmentedControl) {
    recognitionMode = sender.selectedSegment == 1 ? "careful" : "normal"
  }
  @objc private func changeSourceSpeechLanguage(_ sender: NSPopUpButton) {
    sourceSpeechLanguage = sender.indexOfSelectedItem == 0 ? "ru" : ""
  }
  @objc private func changeTopicDetail(_ sender: NSSegmentedControl) {
    topicDetail = ["low", "auto", "high"][max(0, min(sender.selectedSegment, 2))]
  }
  @objc private func addYouTube() {
    let alert = NSAlert()
    alert.messageText = "YouTube"
    alert.informativeText =
      "Введите одну или несколько ссылок, каждую с новой строки. Для плейлиста Integra сначала покажет найденные видео и попросит подтвердить выбор."
    let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 420, height: 72))
    field.placeholderString = "https://youtube.com/watch?v=…"
    alert.accessoryView = field
    alert.addButton(withTitle: "Добавить")
    alert.addButton(withTitle: "Отмена")
    if alert.runModal() == .alertFirstButtonReturn {
      resolveYouTubeInputs(field.stringValue.split(whereSeparator: \.isNewline).map(String.init))
    }
  }
  private func resolveYouTubeInputs(_ inputs: [String]) {
    status.textColor = .secondaryLabelColor
    status.stringValue = "Проверяю ссылки YouTube…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let detected = try bridge.json("detect-sources", request: ["inputs": inputs])["result"] as? [[String: Any]] ?? []
        guard detected.contains(where: { ($0["source_type"] as? String) == "YOUTUBE_PLAYLIST" }) else {
          DispatchQueue.main.async { self.applyDetected(detected) }
          return
        }
        var resolved: [[String: Any]] = []
        var unavailable: [[String: Any]] = []
        var titles: [String] = []
        for source in detected {
          if (source["source_type"] as? String) != "YOUTUBE_PLAYLIST" {
            resolved.append(source)
          } else {
            let inventory = try bridge.json("discover-youtube-playlist", request: ["source": source])["result"] as? [String: Any] ?? [:]
            resolved += inventory["sources"] as? [[String: Any]] ?? []
            unavailable += inventory["unavailable"] as? [[String: Any]] ?? []
            if let title = (inventory["playlist"] as? [String: Any])?["playlist_title"] as? String, !title.isEmpty {
              titles.append(title)
            }
          }
        }
        DispatchQueue.main.async { self.confirmYouTubeDiscovery(resolved, unavailable: unavailable, titles: titles) }
      } catch {
        DispatchQueue.main.async {
          self.status.textColor = .systemRed
          self.status.stringValue = error.localizedDescription
        }
      }
    }
  }
  private func confirmYouTubeDiscovery(_ discovered: [[String: Any]], unavailable: [[String: Any]], titles: [String]) {
    guard !discovered.isEmpty else {
      status.textColor = .systemRed
      status.stringValue = "В плейлисте нет доступных видео для добавления."
      return
    }
    let alert = NSAlert()
    alert.messageText = "Подтвердите видео плейлиста"
    let title = titles.isEmpty ? "Плейлист" : titles.joined(separator: ", ")
    alert.informativeText = "\(title). Выберите видео для добавления в этом порядке. Недоступно или исключено: \(unavailable.count)."
    let stack = NSStackView()
    stack.orientation = .vertical
    stack.alignment = .leading
    stack.spacing = 5
    var choices: [(source: [String: Any], control: NSButton)] = []
    for (index, source) in discovered.enumerated() {
      let name = source["display_name"] as? String ?? "Видео"
      let control = NSButton(checkboxWithTitle: "\(index + 1). \(name)", target: nil, action: nil)
      control.state = .on
      control.font = .systemFont(ofSize: 13)
      stack.addArrangedSubview(control)
      choices.append((source, control))
    }
    for item in unavailable {
      let name = item["title"] as? String ?? "Видео"
      let label = NSTextField(labelWithString: "Недоступно: \(name)")
      label.font = .systemFont(ofSize: 12)
      label.textColor = .secondaryLabelColor
      stack.addArrangedSubview(label)
    }
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 500, height: 240))
    scroll.hasVerticalScroller = true
    scroll.borderType = .bezelBorder
    scroll.documentView = stack
    stack.translatesAutoresizingMaskIntoConstraints = false
    NSLayoutConstraint.activate([
      stack.leadingAnchor.constraint(equalTo: scroll.contentView.leadingAnchor, constant: 8),
      stack.trailingAnchor.constraint(equalTo: scroll.contentView.trailingAnchor, constant: -8),
      stack.topAnchor.constraint(equalTo: scroll.contentView.topAnchor, constant: 8),
      stack.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor, constant: -16),
    ])
    alert.accessoryView = scroll
    alert.addButton(withTitle: "Добавить выбранные источники")
    alert.addButton(withTitle: "Отмена")
    guard alert.runModal() == .alertFirstButtonReturn else { return }
    let selectedSources = choices.filter { $0.control.state == .on }.map(\.source)
    guard !selectedSources.isEmpty else {
      status.textColor = .systemRed
      status.stringValue = "Выберите хотя бы одно видео из плейлиста."
      return
    }
    applyDetected(selectedSources)
  }
  private func detect(_ inputs: [String]) {
    status.textColor = .secondaryLabelColor
    status.stringValue = "Определяю тип и реальные возможности…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let detected =
          try bridge.json("detect-sources", request: ["inputs": inputs])["result"]
          as? [[String: Any]] ?? []
        let caps =
          try bridge.json("capability-registry", request: ["sources": detected])["result"]
          as? [[String: Any]] ?? []
        DispatchQueue.main.async {
          self.applyDetected(detected, capabilities: caps)
        }
      } catch {
        DispatchQueue.main.async {
          self.status.textColor = .systemRed
          self.status.stringValue = error.localizedDescription
        }
      }
    }
  }
  private func applyDetected(_ detected: [[String: Any]], capabilities supplied: [[String: Any]]? = nil) {
    sources = detected
    recognitionMode = "normal"
    sourceSpeechLanguage = "ru"
    topicDetail = "auto"
    capabilities = supplied ?? (try? bridge?.json("capability-registry", request: ["sources": detected])["result"] as? [[String: Any]]) ?? []
    if let index = CommandLine.arguments.firstIndex(of: "--ui-probe-output"),
      CommandLine.arguments.indices.contains(index + 1)
    {
      selected = Set(CommandLine.arguments[index + 1].split(separator: ",").map(String.init))
      plan = try? bridge?.json("build-plan", request: ["sources": detected, "selected_outputs": Array(selected).sorted()])["result"] as? [String: Any]
    } else {
      selected = []
      plan = nil
    }
    renderNew()
    runNativeSmokeIfRequested()
  }
  @objc private func toggleCapability(_ sender: NSButton) {
    guard let id = sender.identifier?.rawValue else { return }
    if sender.state == .on { selected.insert(id) } else { selected.remove(id) }
    do {
      plan =
        selected.isEmpty
        ? nil
        : try bridge.json(
          "build-plan", request: ["sources": sources, "selected_outputs": Array(selected).sorted()])[
            "result"] as? [String: Any]
      renderNew()
    } catch {
      plan = nil
      status.stringValue = error.localizedDescription
    }
  }
  @objc private func execute() {
    guard !terminationPending else { return }
    guard let plan = plan else { return }
    status.textColor = .secondaryLabelColor
    status.stringValue = "Создаю проект и ставлю реальную обработку в очередь…"
    let bridge = self.bridge!
    let name = sources.first?["display_name"] as? String ?? "Новая обработка"
    let recognitionMode = self.recognitionMode
    let sourceSpeechLanguage = self.sourceSpeechLanguage
    let topicDetail = self.topicDetail
    serviceQueue.async {
      do {
        let result =
          try bridge.json("execute-plan", request: ["plan": plan, "name": name, "recognition_mode": recognitionMode, "source_speech_language": sourceSpeechLanguage, "topic_detail": topicDetail])["result"]
          as? [String: Any]
        let project = result?["project"] as? [String: Any]
        let run = result?["run"] as? [String: Any]
        DispatchQueue.main.async {
          self.projectID = project?["project_id"] as? String
          self.runID = run?["run_id"] as? String
          self.renderOperations()
        }
      } catch {
        DispatchQueue.main.async {
          self.status.textColor = .systemRed
          self.status.stringValue = error.localizedDescription
        }
      }
    }
  }

  // Opt-in acceptance probe. It drives the same native action and backend as
  // the button, only with caller-owned fixtures in an isolated application root.
  // No semantic decisions, account access or publication are permitted here.
  private func runNativeSmokeIfRequested() {
    let retryProbe = ProcessInfo.processInfo.environment["INTEGRA_NATIVE_RETRY_SMOKE"] == "1"
    let allowedOutputs: Set<String> = retryProbe ? ["word_timeline"] : ["speed_video", "audio_analysis", "document_text"]
    guard let directory = ProcessInfo.processInfo.environment["INTEGRA_NATIVE_SMOKE_DIR"],
      let dataRoot = ProcessInfo.processInfo.environment["INTEGRA_APP_DATA_ROOT"],
      dataRoot == directory + "/app-data", plan != nil,
      !selected.isEmpty, selected.isSubset(of: allowedOutputs),
      sources.allSatisfy({ ($0["input"] as? String)?.hasPrefix(directory + "/") == true })
    else { return }
    func capture(_ name: String) {
      guard let view = window.contentView else { return }
      view.layoutSubtreeIfNeeded()
      guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
      view.cacheDisplay(in: view.bounds, to: bitmap)
      try? bitmap.representation(using: .png, properties: [:])?.write(
        to: URL(fileURLWithPath: directory).appendingPathComponent(name))
    }
    func actionButton(_ view: NSView, action: Selector) -> NSButton? {
      if let button = view as? NSButton, button.action == action, button.isEnabled { return button }
      for child in view.subviews { if let button = actionButton(child, action: action) { return button } }
      return nil
    }
    capture("plan.png")
    guard let view = window.contentView, let button = actionButton(view, action: #selector(execute)) else { return }
    button.performClick(nil)
    let deadline = Date().addingTimeInterval(180)
    var retriedRun: String?
    Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] probe in
      Task { @MainActor in
        guard let self else { probe.invalidate(); return }
        if let projectID = self.projectID, let runID = self.runID,
          let run = try? self.bridge.json("run-status", request: ["project_id": projectID, "run_id": runID])["result"] as? [String: Any],
          ["COMPLETED", "FAILED", "CANCELLED"].contains(run["state"] as? String ?? "")
        {
          if retryProbe && run["state"] as? String == "FAILED" && retriedRun == nil {
            self.renderOperationsSnapshot(run)
            capture("before-retry.png")
            try? JSONSerialization.data(withJSONObject: run, options: [.prettyPrinted, .sortedKeys]).write(
              to: URL(fileURLWithPath: directory).appendingPathComponent("failed-run.json"))
            if let view = self.window.contentView, let retry = actionButton(view, action: #selector(self.retryRun)) {
              retriedRun = runID
              retry.performClick(nil)
              return
            }
          }
          if retriedRun == runID && Date() < deadline { return }
          probe.invalidate()
          self.renderOperationsSnapshot(run)
          capture("results.png")
          try? JSONSerialization.data(withJSONObject: run, options: [.prettyPrinted, .sortedKeys]).write(
            to: URL(fileURLWithPath: directory).appendingPathComponent("native-run.json"))
          NSApp.terminate(nil)
        } else if Date() > deadline {
          probe.invalidate()
          try? "Native smoke timed out; not a successful execution\n".write(
            toFile: directory + "/failure.txt", atomically: true, encoding: .utf8)
          NSApp.terminate(nil)
        }
      }
    }
  }

  // Isolated native acceptance: real reads/actions, with a bounded read-queue
  // gate to exercise a late response without modifying backend state.
  private func runOperationsProbeIfRequested() {
    guard let directory = ProcessInfo.processInfo.environment["INTEGRA_NATIVE_OPERATIONS_PROBE"],
      ProcessInfo.processInfo.environment["INTEGRA_APP_DATA_ROOT"] == directory + "/app-data",
      projectID != nil, runID != nil else { return }
    renderOperations()
    let deadline = Date().addingTimeInterval(60)
    var phase = 0
    var identities = [ObjectIdentifier]()
    var previousPoll = 0
    var stable = 0
    var navigationPreserved = false
    Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] probe in
      Task { @MainActor in
        guard let self else { probe.invalidate(); return }
        if Date() > deadline {
          probe.invalidate()
          try? "Operations probe timed out".write(toFile: directory + "/failure.txt", atomically: true, encoding: .utf8)
          NSApp.terminate(nil)
          return
        }
        if phase == 0, self.completedOperationsPolls > previousPoll {
          previousPoll = self.completedOperationsPolls
          let current = self.content.arrangedSubviews.map(ObjectIdentifier.init)
          if current == identities { stable += 1 } else { stable = 0 }
          identities = current
          if stable >= 2, self.operationsRequestID == nil {
            let gate = DispatchSemaphore(value: 0)
            self.operationsQueue.async { _ = gate.wait(timeout: .now() + 5) }
            self.pollOperations()
            self.renderNew()
            identities = self.content.arrangedSubviews.map(ObjectIdentifier.init)
            gate.signal()
            phase = 1
          }
        } else if phase == 1, self.operationsRequestID == nil {
          navigationPreserved = !self.operationsVisible && identities == self.content.arrangedSubviews.map(ObjectIdentifier.init)
          self.renderOperations()
          phase = 2
        } else if phase == 2 {
          if let cancel = self.content.arrangedSubviews.compactMap({ $0 as? NSButton }).first(where: { $0.action == #selector(self.cancelRun) && $0.isEnabled }) {
            cancel.performClick(nil)
            self.cancelRun() // duplicate dispatch must be guarded while pending
            phase = 3
          }
        } else if phase == 3, !self.cancelPending, self.operationsRequestID == nil,
          let snapshot = self.operationsSnapshot,
          let run = try? JSONSerialization.jsonObject(with: snapshot) as? [String: Any],
          run["state"] as? String == "CANCELLED" {
          probe.invalidate()
          if let view = self.window.contentView {
            view.layoutSubtreeIfNeeded()
            if let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
              view.cacheDisplay(in: view.bounds, to: bitmap)
              try? bitmap.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: directory + "/operations.png"))
            }
          }
          let evidence: [String: Any] = ["unchanged_view_checks": stable, "navigation_preserved": navigationPreserved, "cancelled": true, "terminal_state": "CANCELLED"]
          try? JSONSerialization.data(withJSONObject: evidence, options: [.prettyPrinted, .sortedKeys]).write(to: URL(fileURLWithPath: directory + "/ops-probe.json"))
          NSApp.terminate(nil)
        }
      }
    }
  }

  private func renderOperations() {
    reset(
      "Выполняется",
      "Здесь показано реальное состояние backend-задания. Чтобы остановить обработку, нажмите «Отменить». Закрытие окна/приложения также отменяет активную задачу."
    )
    guard projectID != nil, runID != nil else {
      add(NSTextField(labelWithString: "Активной обработки нет"))
      return
    }
    operationsVisible = true
    pollOperations()
    startPolling()
  }
  private func pollOperations() {
    guard operationsVisible, !terminationPending, operationsRequestID == nil,
      let p = projectID, let r = runID else { return }
    let generation = navigationGeneration
    let requestID = UUID()
    operationsRequestID = requestID
    let service = bridge!
    operationsQueue.async {
      do {
        guard let run = try service.json("run-status", request: ["project_id": p, "run_id": r])["result"] as? [String: Any] else { throw BridgeError.invalidResponse }
        guard let state = run["state"] as? String, ["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"].contains(state) else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          guard self.operationsRequestID == requestID else { return }
          self.operationsRequestID = nil
          guard self.operationsVisible, !self.terminationPending, self.navigationGeneration == generation, self.projectID == p, self.runID == r else { return }
          self.completedOperationsPolls += 1
          let keys = ["state", "message", "completed_sources", "total_sources", "current_stage", "source_results", "error"]
          var displayed = run.filter { keys.contains($0.key) }
          displayed["cancel_pending"] = self.cancelPending
          displayed["retry_pending"] = self.retryPending
          let signature = try? JSONSerialization.data(withJSONObject: displayed, options: [.sortedKeys])
          if signature == nil || signature != self.operationsSnapshot {
            self.operationsSnapshot = signature
            self.renderOperationsSnapshot(run)
          }
          self.status.stringValue = self.operationsError.isEmpty ? (run["error"] as? String ?? "") : self.operationsError
        }
      } catch {
        DispatchQueue.main.async {
          guard self.operationsRequestID == requestID else { return }
          self.operationsRequestID = nil
          guard self.operationsVisible, !self.terminationPending, self.navigationGeneration == generation, self.projectID == p, self.runID == r else { return }
          self.status.stringValue = "Не удалось обновить состояние: \(error.localizedDescription)"
        }
      }
    }
  }
  private func renderOperationsSnapshot(_ run: [String: Any]) {
      reset("Обработка", "Состояние задания и сохранённые результаты", preservingOperations: true)
      let state = run["state"] as? String ?? "UNKNOWN"
      let detail = run["message"] as? String ?? ""
      let done = run["completed_sources"] as? Int ?? 0
      let total = run["total_sources"] as? Int ?? 0
      let names = ["QUEUED": "В очереди", "RUNNING": "Выполняется", "COMPLETED": "Готово", "FAILED": "Ошибка", "CANCELLED": "Отменено"]
      add(row("Состояние: \(names[state] ?? state)", detail: "Готово источников: \(done) из \(total)"))
      if let recognition = run["recognition"] as? [String: Any], let mode = recognition["requested_mode"] as? String {
        add(row("Режим распознавания", detail: mode == "careful" ? "Тщательный" : "Обычный"))
      }
      if let language = run["source_speech_language"] as? [String: Any],
        let requested = language["requested"] as? String
      {
        let executed = language["executed"] as? String
        let detail = (executed ?? requested) == "ru" ? "Русский" : "Не поддерживается"
        add(row("Язык исходной речи", detail: detail))
      }
      if state == "RUNNING" || state == "QUEUED" {
        if !detail.isEmpty { add(row("Подробности", detail: detail)) }
        if let stage = run["current_stage"] as? String { add(row("Текущий этап", detail: stageLabel(stage))) }
        let stopButton = button(cancelPending ? "Останавливаю…" : "Отменить", #selector(cancelRun), enabled: !cancelPending)
        stopButton.toolTip = "Запросить остановку и дождаться подтверждения. Уже сохранённые результаты останутся в проекте."
        add(stopButton)
      }
      if state == "FAILED" || state == "CANCELLED" { add(button("Повторить", #selector(retryRun), enabled: !retryPending)) }
      // A multi-source run can truthfully be FAILED while earlier or later
      // independent sources completed.  Those persisted results remain
      // user-visible; failed peers still have no successful output fabricated.
      if state == "COMPLETED" || state == "FAILED" { renderResultRows(run) }
      if let error = run["error"] as? String { status.stringValue = error }
      if ["COMPLETED", "FAILED", "CANCELLED"].contains(state) { timer?.invalidate(); timer = nil }
  }
  private func startPolling() {
    timer?.invalidate()
    timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
      Task { @MainActor in self?.pollOperations() }
    }
  }
  private func renderResultRows(_ run: [String: Any]) {
    add(section("ГОТОВЫЕ РЕЗУЛЬТАТЫ"))
    for result in (run["source_results"] as? [[String: Any]]) ?? [] {
      add(row(result["display_name"] as? String ?? "Источник", detail: result["state"] as? String ?? "UNKNOWN"))
      let outputs = result["outputs"] as? [String: Any] ?? [:]
      renderASRDiagnostics(result)
      if let reuse = result["asr_reuse"] as? [String: Any], reuse["state"] as? String == "REUSED" {
        add(row("Расшифровка использована повторно", detail: "Исходник, модель, настройки и файлы проверены. Повторное распознавание не запускалось."))
      }
      renderPrimaryProcessResults(outputs, result: result)
      if outputs["subtitles"] as? String != nil,
        let projectID = projectID, let runID = runID, let sourceID = result["source_id"] as? String
      {
        let control = button("Открыть источник с расшифровкой", #selector(showMediaNavigation(_:)))
        control.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
        add(control)
      }
      renderTechnicalData(outputs)
    }
  }
  private func renderASRDiagnostics(_ result: [String: Any]) {
    guard let diagnostics = result["asr_diagnostics"] as? [String: Any],
      let status = diagnostics["status"] as? String,
      let suspicious = diagnostics["suspicious_chunks"] as? Int,
      let retries = diagnostics["protective_retry_count"] as? Int,
      let recovered = diagnostics["recovered_after_retry_count"] as? Int,
      let recognition = diagnostics["recognition"] as? [String: Any],
      let executedMode = recognition["executed_mode"] as? String,
      let language = diagnostics["source_speech_language"] as? [String: Any],
      let executedLanguage = language["executed"] as? String
    else { return }
    add(section("ПРОВЕРКА РАСШИФРОВКИ"))
    if status == "PASSED" {
      let detail = retries == 0
        ? "Пройдена. Подозрительных фрагментов не найдено."
        : "Пройдена после дополнительной проверки фрагментов: \(recovered)."
      add(row("Проверка качества", detail: detail))
    } else {
      add(row("Проверка качества", detail: "Не пройдена после повторной проверки. Требуется проверить аудио."))
    }
    add(row("Режим распознавания", detail: executedMode == "careful" ? "Тщательный" : "Обычный"))
    add(row("Язык исходной речи", detail: executedLanguage == "ru" ? "Русский" : "Не поддерживается"))
    if retries == 0 {
      add(row("Повторная проверка", detail: "Не потребовалась."))
    } else if status == "PASSED" {
      add(row("Повторная проверка", detail: "Выполнена для \(retries) фрагм.; итоговая расшифровка принята."))
    } else {
      add(row("Повторная проверка", detail: "Не устранила проблемы в \(suspicious) фрагм.; нужна проверка аудио."))
    }
  }
  private func renderPrimaryProcessResults(_ outputs: [String: Any], result: [String: Any]) {
    let grid = ResponsiveResultsGrid()
    var left = 0
    var right = 0
    func addCard(_ card: NSView, toLeft: Bool) {
      if toLeft { grid.leftColumn.addArrangedSubview(card); left += 1 }
      else { grid.rightColumn.addArrangedSubview(card); right += 1 }
    }
    if outputs["transcript"] is String, let projectID, let runID, let sourceID = result["source_id"] as? String {
      let ids = "\(projectID)\n\(runID)\n\(sourceID)"
      let open = button("Открыть", #selector(openTranscript(_:))); open.toolTip = ids
      let export = button("Экспортировать…", #selector(exportTranscript(_:))); export.toolTip = ids
      addCard(processCard("Расшифровка", controls: [open, export]), toLeft: true)
    }
    if let path = outputs["transcript_cleaned"] as? String {
      addCard(processCard("Очищенный текст", controls: outputControls(path)), toLeft: false)
    }
    if let path = outputs["translation_txt"] as? String {
      let provenancePath = outputs["translation_provenance"] as? String ?? ""
      let translatedTo = translationLanguageName(from: provenancePath, key: "target_language")
      let target = NSTextField(labelWithString: "Язык перевода: \(translatedTo)")
      target.textColor = .secondaryLabelColor
      addCard(processCard("Перевод", controls: [target] + outputControls(path)), toLeft: left <= right)
    } else if outputs["transcript"] is String,
      let projectID, let runID, let sourceID = result["source_id"] as? String
    {
      let sourceLanguage = translationSourceLanguage(result)
      let targetLanguage = sourceLanguage == "ru" ? "en" : "ru"
      let label = NSTextField(labelWithString: "Язык перевода")
      let target = TranslationTargetPicker()
      target.addItem(withTitle: languageName(targetLanguage))
      target.item(at: 0)?.representedObject = targetLanguage
      target.selectItem(at: 0)
      target.target = self; target.action = #selector(changeTranslationTarget(_:))
      let translate = TranslationButton(title: "Перевести", target: self, action: #selector(translateTranscript(_:)))
      translate.bezelStyle = .rounded
      translate.projectID = projectID; translate.sourceRunID = runID; translate.sourceID = sourceID
      translate.targetLanguage = targetLanguage
      target.translationButton = translate
      addCard(processCard("Перевод", controls: [label, target, translate]), toLeft: left <= right)
    }
    if let path = outputs["topic_translation_txt"] as? String,
      let projectID, let runID, let sourceID = result["source_id"] as? String
    {
      let open = button("Открыть перевод тем", #selector(showTopicTranslation(_:)))
      open.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
      let target = NSTextField(labelWithString: "Русский → Английский")
      target.textColor = .secondaryLabelColor
      addCard(processCard("Перевод тем", controls: [target, open] + outputControls(path)), toLeft: left <= right)
    }
    // The raw Topics JSON remains technical data. The normal Process view
    // reads the same persisted source-bound Topic result; review remains an
    // explicit and separate human decision.
    if outputs["topics"] is String,
      let projectID, let runID, let sourceID = result["source_id"] as? String
    {
      let open = button("Открыть темы", #selector(showProcessTopics(_:)))
      open.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
      let review = button("Проверить темы", #selector(prepareTopicReview(_:)))
      review.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
      let translate = TranslationButton(title: "Перевести темы", target: self, action: #selector(translateTopics(_:)))
      translate.bezelStyle = .rounded
      translate.projectID = projectID; translate.sourceRunID = runID; translate.sourceID = sourceID
      addCard(processCard("Темы и таймкоды", controls: [open, review, translate]), toLeft: left <= right)
    }
    if left + right > 0 {
      add(grid)
      // `content` aligns arranged subviews to the leading edge.  Give the grid
      // the available result-surface width so its responsive breakpoint is
      // based on the actual window, rather than on one card's intrinsic width.
      grid.widthAnchor.constraint(equalTo: content.widthAnchor, constant: -76).isActive = true
    }
  }
  private func readableOutput(_ outputs: [String: Any], keys: [String]) -> String? {
    for key in keys {
      if let value = outputs[key] as? String, URL(fileURLWithPath: value).pathExtension.lowercased() != "json" { return value }
    }
    return nil
  }
  private func processCard(_ title: String, controls: [NSButton]) -> NSBox {
    processCard(title, controls: controls.map { $0 as NSView })
  }
  private func processCard(_ title: String, controls: [NSView]) -> NSBox {
    let card = NSBox()
    card.boxType = .custom
    card.isTransparent = false
    card.cornerRadius = 8
    card.borderColor = .separatorColor
    let stack = NSStackView()
    stack.orientation = .vertical
    stack.alignment = .leading
    stack.spacing = 10
    stack.edgeInsets = NSEdgeInsets(top: 14, left: 14, bottom: 14, right: 14)
    let heading = NSTextField(labelWithString: title)
    heading.font = .systemFont(ofSize: 16, weight: .semibold)
    stack.addArrangedSubview(heading)
    let actions = NSStackView(views: controls)
    actions.orientation = .horizontal
    actions.spacing = 8
    stack.addArrangedSubview(actions)
    card.contentView = stack
    return card
  }
  private func languageName(_ code: String) -> String {
    switch code {
    case "ru": return "Русский"
    case "en": return "Английский"
    default: return "Недоступен"
    }
  }
  private func translationSourceLanguage(_ result: [String: Any]) -> String {
    let language = result["source_speech_language"] as? [String: Any]
    return language?["executed"] as? String ?? language?["requested"] as? String ?? "ru"
  }
  private func translationLanguageName(from path: String, key: String) -> String {
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
      let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let code = payload[key] as? String
    else { return "Не определён" }
    return languageName(code)
  }
  @objc private func changeTranslationTarget(_ sender: NSPopUpButton) {
    guard let picker = sender as? TranslationTargetPicker,
      let target = picker.selectedItem?.representedObject as? String,
      ["ru", "en"].contains(target)
    else { return }
    picker.translationButton?.targetLanguage = target
  }
  private func outputControls(_ path: String) -> [NSButton] {
    let open = button("Открыть", #selector(openOutput(_:))); open.toolTip = path
    let export = button("Экспортировать…", #selector(exportOutput(_:))); export.toolTip = path
    return [open, export]
  }
  private func renderTechnicalData(_ outputs: [String: Any]) {
    let technical = outputs.compactMap { key, value -> (String, String)? in
      guard let path = value as? String else { return nil }
      switch key {
      case "transcript", "transcript_cleaned", "topics_txt", "topics_markdown": return nil
      default: return (key, path)
      }
    }.sorted { $0.0 < $1.0 }
    guard !technical.isEmpty else { return }
    let disclosure = TechnicalDisclosure()
    for (kind, path) in technical {
      let control = button("Открыть технические данные: \(kind)", #selector(openOutput(_:)))
      control.toolTip = path
      disclosure.details.addArrangedSubview(control)
    }
    add(disclosure)
  }
  @objc private func unavailableAction() {}
  @objc private func createMachineEvidence(_ sender: NSButton) {
    let ids = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard ids.count == 3 else { return }
    sender.isEnabled = false
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        _ = try bridge.json("create-machine-evidence", request: ["project_id": ids[0], "run_id": ids[1], "source_id": ids[2]])
        DispatchQueue.main.async { self.renderOutputs() }
      } catch {
        DispatchQueue.main.async { sender.isEnabled = true; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  @objc private func buildReviewedPackage(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard identifiers.count == 3 else { return }
    status.stringValue = "Проверяю сохранённые решения и формирую пакет…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        _ = try bridge.json("build-reviewed-package", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2]])
        DispatchQueue.main.async {
          self.renderOutputs()
          self.status.stringValue = "Пакет готов. Выберите Obsidian или OneDrive для предварительного просмотра и публикации. Ничего не опубликовано автоматически."
        }
      } catch {
        DispatchQueue.main.async { self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  @objc private func prepareTopicReview(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard identifiers.count == 3 else { return }
    sender.isEnabled = false; sender.title = "Подготавливаю темы…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let result = try bridge.json("prepare-process-topic-review", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2]])["result"] as? [String: Any] ?? [:]
        guard let reviewStatus = result["status"] as? String,
              reviewStatus == "PROCESS_TOPIC_REVIEW_REQUIRED" || reviewStatus == "PROCESS_TOPIC_REVIEWED" else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          sender.title = "Проверить темы"; sender.isEnabled = true
          self.presentTopicReview(result, identifiers: identifiers, readOnly: reviewStatus == "PROCESS_TOPIC_REVIEWED")
        }
      } catch {
        DispatchQueue.main.async {
          sender.title = "Повторить подготовку тем"; sender.isEnabled = true
          self.status.textColor = .systemRed
          self.status.stringValue = error.localizedDescription
        }
      }
    }
  }
  @objc private func showProcessTopics(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard identifiers.count == 3 else { return }
    sender.isEnabled = false; sender.title = "Открываю темы…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let result = try bridge.json("process-topics", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2]])["result"] as? [String: Any] ?? [:]
        guard let topicStatus = result["status"] as? String,
              topicStatus == "PROCESS_MACHINE_TOPICS" || topicStatus == "PROCESS_TOPIC_REVIEWED" else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          sender.title = "Открыть темы"; sender.isEnabled = true
          self.presentProcessTopics(result, reviewed: topicStatus == "PROCESS_TOPIC_REVIEWED")
        }
      } catch {
        DispatchQueue.main.async {
          sender.title = "Открыть темы"; sender.isEnabled = true
          self.status.textColor = .systemRed
          self.status.stringValue = error.localizedDescription
        }
      }
    }
  }
  @objc private func translateTopics(_ sender: NSButton) {
    guard let translate = sender as? TranslationButton else { return }
    sender.isEnabled = false; sender.title = "Перевожу темы…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let value = try bridge.json("translate-topics", request: [
          "project_id": translate.projectID, "run_id": translate.sourceRunID, "source_id": translate.sourceID])
        guard let run = value["result"] as? [String: Any], let record = run["run"] as? [String: Any],
              let nextRun = record["run_id"] as? String else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          self.runID = nextRun
          self.status.stringValue = "Перевод тем запущен. Исходные темы не изменяются."
          self.renderOperations()
        }
      } catch {
        DispatchQueue.main.async { sender.title = "Перевести темы"; sender.isEnabled = true; self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  @objc private func showTopicTranslation(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard identifiers.count == 3 else { return }
    sender.isEnabled = false; sender.title = "Открываю перевод…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let result = try bridge.json("topic-translation", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2]])["result"] as? [String: Any] ?? [:]
        guard let topics = result["topics"] as? [[String: Any]], !topics.isEmpty else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          sender.title = "Открыть перевод тем"; sender.isEnabled = true
          self.presentTopicTranslation(topics)
        }
      } catch {
        DispatchQueue.main.async { sender.title = "Открыть перевод тем"; sender.isEnabled = true; self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  private func presentTopicTranslation(_ topics: [[String: Any]]) {
    let alert = NSAlert()
    alert.messageText = "Перевод тем"
    alert.informativeText = "Перевод является отдельным машинным результатом. Исходные темы и их проверка не изменены."
    let stack = FlippedStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
    for topic in topics {
      let original = topic["original"] as? [String: Any] ?? [:]
      let translation = topic["translation"] as? [String: Any] ?? [:]
      let originalTitle = original["title"] as? String ?? ""
      let translatedTitle = translation["title"] as? String ?? ""
      let translatedSummary = translation["summary"] as? String ?? ""
      let text = "\(originalTitle)\n\(translatedTitle)\n\(translatedSummary)"
      let label = NSTextField(wrappingLabelWithString: text); label.maximumNumberOfLines = 0
      stack.addArrangedSubview(label)
    }
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 570, height: 420)); scroll.hasVerticalScroller = true; scroll.documentView = stack
    stack.setFrameSize(NSSize(width: 540, height: stack.fittingSize.height)); alert.accessoryView = scroll
    alert.addButton(withTitle: "Готово"); _ = alert.runModal()
  }
  private func presentProcessTopics(_ result: [String: Any], reviewed: Bool) {
    guard let topics = result["topics"] as? [[String: Any]], !topics.isEmpty else {
      status.stringValue = "Нет сохранённых тем"; return
    }
    let alert = NSAlert()
    alert.messageText = "Темы и таймкоды"
    alert.informativeText = reviewed
      ? "Сохранённые проверенные темы для этого источника."
      : "Машинные темы. Перед использованием их можно проверить."
    if let detail = result["topic_detail"] as? [String: String],
      let executed = detail["executed"]
    {
      let label = ["low": "Крупно", "auto": "Обычно", "high": "Подробно"][executed] ?? executed
      alert.informativeText += " Детализация: \(label)."
    }
    let stack = FlippedStackView()
    stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 10
    for topic in topics {
      let start = topic["start_seconds"] as? Double ?? 0
      let end = topic["end_seconds"] as? Double ?? 0
      let timing = NSTextField(labelWithString: String(format: "Время: %.3f–%.3f с", start, end))
      timing.textColor = .secondaryLabelColor; timing.widthAnchor.constraint(equalToConstant: 560).isActive = true
      stack.addArrangedSubview(timing)
      let title = NSTextField(wrappingLabelWithString: "Тема: \(topic["title"] as? String ?? "")")
      title.font = .systemFont(ofSize: 14, weight: .semibold); title.widthAnchor.constraint(equalToConstant: 560).isActive = true
      stack.addArrangedSubview(title)
      let summary = NSTextField(wrappingLabelWithString: "Краткое содержание: \(topic["summary"] as? String ?? "")")
      summary.widthAnchor.constraint(equalToConstant: 560).isActive = true; stack.addArrangedSubview(summary)
    }
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 590, height: 420))
    scroll.hasVerticalScroller = true; scroll.documentView = stack
    stack.setFrameSize(NSSize(width: 570, height: stack.fittingSize.height)); alert.accessoryView = scroll
    alert.addButton(withTitle: "Готово")
    _ = alert.runModal()
  }
  // Process v1 subset of the pinned Topic contract: confirmation, rename,
  // reject and defer.  It never asks the user to classify Knowledge.
  private func presentTopicReview(_ package: [String: Any], identifiers: [String], readOnly: Bool = false) {
    guard let topics = package["topics"] as? [[String: Any]], !topics.isEmpty,
      let hash = package["package_sha256"] as? String else { status.stringValue = "Нет тем для проверки"; return }
    let alert = NSAlert()
    alert.messageText = "Проверка тем"
    alert.informativeText = readOnly
      ? "Сохранённые решения человека для этого источника."
      : "Подтвердите или отредактируйте каждую машинную тему. Решения сохраняются в результатах обработки источника."
    if let detail = package["topic_detail"] as? [String: String],
      let executed = detail["executed"]
    {
      let label = ["low": "Крупно", "auto": "Обычно", "high": "Подробно"][executed] ?? executed
      alert.informativeText += " Детализация: \(label)."
    }
    let stack = FlippedStackView()
    stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
    var choices: [(String, String, String, NSPopUpButton, NSTextField, NSTextField)] = []
    for topic in topics {
      guard let id = topic["id"] as? String else { return }
      let start = topic["start_seconds"] as? Double ?? 0
      let end = topic["end_seconds"] as? Double ?? 0
      let span = NSTextField(wrappingLabelWithString: String(format: "Источник: %.3f–%.3f с", start, end))
      span.widthAnchor.constraint(equalToConstant: 560).isActive = true; stack.addArrangedSubview(span)
      let title = NSTextField(string: topic["title"] as? String ?? "Тема")
      title.placeholderString = "Название темы"; title.widthAnchor.constraint(equalToConstant: 560).isActive = true; stack.addArrangedSubview(title)
      let summary = NSTextField(string: topic["summary"] as? String ?? "")
      summary.placeholderString = "Краткое описание"; summary.widthAnchor.constraint(equalToConstant: 560).isActive = true; stack.addArrangedSubview(summary)
      let choice = NSPopUpButton()
      if readOnly {
        title.isEditable = false; summary.isEditable = false
        let actions = package["actions"] as? [String: String] ?? [:]
        let labels = ["ACCEPT": "Подтверждено", "RENAME": "Переименовано", "REJECT": "Отклонено", "DEFER": "Отложено"]
        choice.addItem(withTitle: labels[actions[id] ?? ""] ?? "Сохранённое решение")
        choice.isEnabled = false
      } else {
        choice.addItems(withTitles: ["Выберите решение", "Подтвердить тему", "Переименовать", "Отклонить", "Отложить"])
      }
      stack.addArrangedSubview(choice)
      choices.append((id, title.stringValue, summary.stringValue, choice, title, summary))
    }
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 590, height: 420))
    scroll.hasVerticalScroller = true; scroll.documentView = stack
    stack.setFrameSize(NSSize(width: 570, height: stack.fittingSize.height)); alert.accessoryView = scroll
    if readOnly {
      alert.addButton(withTitle: "Готово")
      _ = alert.runModal()
      return
    }
    alert.addButton(withTitle: "Сохранить проверенные темы"); alert.addButton(withTitle: "Отмена")
    while true {
      guard alert.runModal() == .alertFirstButtonReturn else { return }
      if choices.allSatisfy({ $0.3.indexOfSelectedItem > 0 }) { break }
      alert.informativeText = "Выберите решение для КАЖДОЙ темы."
    }
    let actions = ["ACCEPT", "RENAME", "REJECT", "DEFER"]
    let decisions: [[String: Any]] = choices.map { choice in
      let selectedAction = actions[choice.3.indexOfSelectedItem - 1]
      // The pinned v1 contract permits one decision per Topic.  A title or
      // summary edit confirmed as "ACCEPT" is therefore represented truthfully
      // as its v1 RENAME decision, rather than silently dropping the edit.
      let edited = choice.4.stringValue != choice.1 || choice.5.stringValue != choice.2
      let action = selectedAction == "ACCEPT" && edited ? "RENAME" : selectedAction
      return ["topic_id": choice.0, "action": action, "reason": "Explicit Process Topic decision in Integra macOS review",
              "new_title": action == "RENAME" ? choice.4.stringValue : NSNull(),
              "new_summary": action == "RENAME" ? choice.5.stringValue : NSNull()]
    }
    status.stringValue = "Сохраняю проверенные темы…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let response = try bridge.json("apply-process-topic-review", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2],
          "expected_package_sha256": hash, "decisions": decisions])
        guard (response["result"] as? [String: Any])?["status"] as? String == "PROCESS_REVIEWED_TOPICS_CREATED" else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async { self.renderOutputs(); self.status.stringValue = "Проверенные темы сохранены." }
      } catch {
        DispatchQueue.main.async { self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  // Legacy Knowledge review remains available to its future Knowledge surface;
  // the Process results action above never calls this view or its operations.
  private func presentProcessTopicReviewLegacy(_ package: [String: Any], identifiers: [String]) {
    guard let topics = package["topics"] as? [[String: Any]], !topics.isEmpty,
      let hash = package["package_sha256"] as? String else { status.stringValue = "Нет тем для проверки"; return }
    NSSound.beep()
    let exactFragments = package["review_mode"] as? String == "EXACT_FRAGMENTS_V2"
    let alert = NSAlert()
    alert.messageText = exactFragments ? "Проверьте фрагменты и их точные границы" : "Проверьте темы перед созданием знаний"
    alert.informativeText = exactFragments ? "Выберите, какие фрагменты включить в знания, а какие исключить. Результат — проверенные фрагменты с цитатами; создание Canonical Knowledge для этих границ пока в разработке." : "Для каждой темы прочитайте цитату и выберите решение. Без вашего решения знания не создаются."
    let stack = FlippedStackView()
    stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
    if let mediaPath = package["media_path"] as? String {
      let player = AVPlayer(url: URL(fileURLWithPath: mediaPath))
      reviewPlayer = player
      let video = AVPlayerView(frame: NSRect(x: 0, y: 0, width: 560, height: 220))
      video.player = player
      video.widthAnchor.constraint(equalToConstant: 560).isActive = true
      video.heightAnchor.constraint(equalToConstant: 220).isActive = true
      stack.addArrangedSubview(video)
    }
    defer { reviewPlayer?.pause(); reviewPlayer = nil }
    var choices: [(String, NSPopUpButton)] = []
    for topic in topics {
      guard let id = topic["id"] as? String else { return }
      let text = NSTextField(wrappingLabelWithString: "\(topic["title"] as? String ?? "Тема")\n\(topic["summary"] as? String ?? "")\nЦитата: \(topic["quote"] as? String ?? "")")
      text.widthAnchor.constraint(equalToConstant: 560).isActive = true
      stack.addArrangedSubview(text)
      if let start = topic["start_seconds"] as? Double, let end = topic["end_seconds"] as? Double {
        let interval = String(format: "%.3f–%.3f с", start, end)
        let play = button("Прослушать цитату · \(interval)", #selector(playReviewQuote(_:)), enabled: reviewPlayer != nil)
        play.toolTip = "\(start)\n\(end)"
        stack.addArrangedSubview(play)
      }
      let choice = NSPopUpButton()
      choice.addItems(withTitles: exactFragments ? ["Выберите решение", "Включить фрагмент в знания", "Исключить фрагмент из знаний"] : ["Выберите решение", "Принять", "Отклонить"])
      stack.addArrangedSubview(choice); choices.append((id, choice))
    }
    let reviewer = NSTextField(frame: NSRect(x: 0, y: 0, width: 560, height: 24))
    reviewer.placeholderString = "Идентификатор проверяющего"; stack.addArrangedSubview(reviewer)
    let boundaries = NSButton(checkboxWithTitle: "Подтверждаю точные границы показанных цитат", target: nil, action: nil)
    if exactFragments { stack.addArrangedSubview(boundaries) }
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 590, height: 420))
    scroll.hasVerticalScroller = true; scroll.documentView = stack
    stack.setFrameSize(NSSize(width: 570, height: stack.fittingSize.height))
    alert.accessoryView = scroll
    alert.addButton(withTitle: exactFragments ? "Сохранить проверенные фрагменты" : "Сохранить решения и создать знания"); alert.addButton(withTitle: "Отмена")
    while true {
      guard alert.runModal() == .alertFirstButtonReturn else { return }
      if choices.allSatisfy({ $0.1.indexOfSelectedItem > 0 }) && !reviewer.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && (!exactFragments || boundaries.state == .on) { break }
      alert.informativeText = "Выберите решение для КАЖДОЙ темы, укажите идентификатор проверяющего и подтвердите границы цитат, если показан этот пункт."
    }
    let decisions = choices.map { ["topic_id": $0.0, "action": $0.1.indexOfSelectedItem == 1 ? "ACCEPT" : "REJECT", "reason": "Explicit decision in Integra macOS review"] }
    let reviewerID = reviewer.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
    status.stringValue = "Сохраняю решения и формирую проверенный результат…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let response = try bridge.json("apply-knowledge-review", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2],
          "expected_package_sha256": hash, "reviewer_id": reviewerID, "decisions": decisions, "boundaries_acknowledged": exactFragments])
        let result = response["result"] as? [String: Any]
        let fragments = result?["status"] as? String == "REVIEWED_TOPICS_CREATED"
        DispatchQueue.main.async { self.renderOutputs(); self.status.stringValue = fragments ? "Проверенные фрагменты сохранены. Canonical Knowledge для этих границ — В разработке." : "Решения сохранены. Проверенные знания доступны в результатах." }
      } catch {
        DispatchQueue.main.async { self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  @objc private func playReviewQuote(_ sender: NSButton) {
    let times = sender.toolTip?.split(separator: "\n").compactMap { Double($0) } ?? []
    guard times.count == 2, let player = reviewPlayer else { return }
    player.pause()
    player.currentItem?.forwardPlaybackEndTime = CMTime(seconds: times[1], preferredTimescale: 600)
    player.seek(to: CMTime(seconds: times[0], preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
    player.play()
  }
  @objc private func showTranscriptReview(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard identifiers.count == 3 else { return }
    sender.isEnabled = false
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let prepared = try bridge.json("prepare-transcript-review", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2]])["result"] as? [String: Any] ?? [:]
        guard let transcriptPath = prepared["transcript_path"] as? String else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          sender.isEnabled = true
          self.presentTranscriptReview(prepared: prepared, transcriptPath: transcriptPath, identifiers: identifiers)
        }
      } catch {
        DispatchQueue.main.async { sender.isEnabled = true; self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  private func presentTranscriptReview(prepared: [String: Any], transcriptPath: String, identifiers: [String]) {
    guard let requestHash = prepared["request_sha256"] as? String else { return }
    NSSound.beep()
    let alert = NSAlert()
    alert.messageText = "Необязательная полная проверка расшифровки"
    alert.informativeText = "Откройте и проверьте весь TXT. Подтверждение создаст Canonical Evidence через закреплённый SeminarText и будет привязано к точным хэшам источника, TXT и Word Timeline. Это действие не выполняется автоматически."
    let accessory = NSStackView()
    accessory.orientation = .vertical; accessory.alignment = .leading; accessory.spacing = 8
    let open = button("Открыть TXT для проверки", #selector(openOutput(_:)))
    open.toolTip = transcriptPath; accessory.addArrangedSubview(open)
    let reviewer = NSTextField(frame: NSRect(x: 0, y: 0, width: 420, height: 24))
    reviewer.placeholderString = "Ваш идентификатор проверки (например, yurielokhin)"
    accessory.addArrangedSubview(reviewer)
    let acknowledged = NSButton(checkboxWithTitle: "Я проверил(а) весь TXT и подтверждаю его для Evidence", target: nil, action: nil)
    accessory.addArrangedSubview(acknowledged)
    alert.accessoryView = accessory
    alert.addButton(withTitle: "Создать Canonical Evidence")
    alert.addButton(withTitle: "Отмена")
    guard alert.runModal() == .alertFirstButtonReturn else { return }
    guard acknowledged.state == .on else { status.textColor = .systemRed; status.stringValue = "Evidence не создан: требуется явное подтверждение проверки TXT."; return }
    let reviewerID = reviewer.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !reviewerID.isEmpty else { status.textColor = .systemRed; status.stringValue = "Evidence не создан: укажите идентификатор проверяющего."; return }
    status.textColor = .secondaryLabelColor; status.stringValue = "Создаю Canonical Evidence через SeminarText…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let result = try bridge.json("apply-transcript-review", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2],
          "reviewer_id": reviewerID, "acknowledged": true, "expected_request_sha256": requestHash])["result"] as? [String: Any] ?? [:]
        guard result["status"] as? String == "EVIDENCE_CREATED" else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          self.status.textColor = .labelColor
          self.status.stringValue = "Canonical Evidence создан из подтверждённого TXT. Теперь можно подготовить темы к проверке."
          self.renderOutputs()
        }
      } catch {
        DispatchQueue.main.async { self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  @objc private func openOutput(_ sender: NSButton) {
    if let path = sender.toolTip { NSWorkspace.shared.open(URL(fileURLWithPath: path)) }
  }
  @objc private func openTranscript(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard identifiers.count == 3 else { return }
    do {
      let result = try bridge.json("transcript-text", request: ["project_id": identifiers[0],
        "run_id": identifiers[1], "source_id": identifiers[2]])["result"] as? [String: Any]
      guard let path = result?["path"] as? String else { return }
      if !NSWorkspace.shared.open(URL(fileURLWithPath: path)) {
        status.stringValue = "TXT создан, но macOS не смогла открыть текстовый редактор."
      }
    } catch {
      status.textColor = .systemRed; status.stringValue = error.localizedDescription
    }
  }
  @objc private func translateTranscript(_ sender: NSButton) {
    guard let request = sender as? TranslationButton,
      !request.projectID.isEmpty, !request.sourceRunID.isEmpty, !request.sourceID.isEmpty,
      ["ru", "en"].contains(request.targetLanguage)
    else { return }
    sender.isEnabled = false; sender.title = "Перевожу…"
    let service = bridge!
    serviceQueue.async {
      do {
        let result = try service.json("translate-transcript", request: [
          "project_id": request.projectID, "run_id": request.sourceRunID, "source_id": request.sourceID,
          "translation_target_language": request.targetLanguage])["result"] as? [String: Any]
        let run = result?["run"] as? [String: Any]
        guard let newRunID = run?["run_id"] as? String else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          self.runID = newRunID
          self.renderOperations()
        }
      } catch {
        DispatchQueue.main.async {
          sender.isEnabled = true; sender.title = "Перевести"
          self.status.textColor = .systemRed
          self.status.stringValue = error.localizedDescription
        }
      }
    }
  }
  @objc private func exportTranscript(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard identifiers.count == 3 else { return }
    do {
      let result = try bridge.json("transcript-text", request: ["project_id": identifiers[0],
        "run_id": identifiers[1], "source_id": identifiers[2]])["result"] as? [String: Any]
      guard let path = result?["path"] as? String else { throw BridgeError.invalidResponse }
      exportManagedFile(path)
    } catch {
      status.textColor = .systemRed
      status.stringValue = error.localizedDescription
    }
  }
  @objc private func exportOutput(_ sender: NSButton) {
    guard let path = sender.toolTip else { return }
    exportManagedFile(path)
  }
  private func exportManagedFile(_ sourcePath: String) {
    let source = URL(fileURLWithPath: sourcePath)
    guard FileManager.default.fileExists(atPath: source.path), !source.hasDirectoryPath else {
      status.textColor = .systemRed
      status.stringValue = "Результат для экспорта недоступен."
      return
    }
    let panel = NSSavePanel()
    panel.title = "Экспортировать результат"
    panel.nameFieldStringValue = source.lastPathComponent
    panel.canCreateDirectories = true
    guard panel.runModal() == .OK, let destination = panel.url else { return }
    guard !FileManager.default.fileExists(atPath: destination.path) else {
      status.textColor = .systemRed
      status.stringValue = "Файл с таким именем уже существует. Выберите другое имя; управляемый результат не изменён."
      return
    }
    do {
      try FileManager.default.copyItem(at: source, to: destination)
      status.textColor = .labelColor
      status.stringValue = "Результат экспортирован: \(destination.lastPathComponent)"
    } catch {
      status.textColor = .systemRed
      status.stringValue = "Не удалось экспортировать результат: \(error.localizedDescription)"
    }
  }
  @objc private func showMediaNavigation(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard identifiers.count == 3 else { return }
    do {
      let navigation = try bridge.json(
        "media-navigation", request: ["project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2]])["result"]
        as? [String: Any] ?? [:]
      guard let path = navigation["media_path"] as? String,
        let segments = navigation["segments"] as? [[String: Any]]
      else { throw BridgeError.invalidResponse }
      renderMediaNavigation(path: path, segments: segments, projectID: identifiers[0], runID: identifiers[1], sourceID: identifiers[2])
    } catch { status.stringValue = error.localizedDescription }
  }
  private func renderMediaNavigation(path: String, segments: [[String: Any]], projectID: String, runID: String, sourceID: String) {
    let player = AVPlayer(url: URL(fileURLWithPath: path))
    let playerView = AVPlayerView()
    playerView.player = player
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 1040, height: 760),
      styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
    window.title = "Integra — расшифровка и таймкоды"
    let stack = FlippedStackView()
    stack.orientation = .vertical
    stack.alignment = .leading
    stack.spacing = 8
    stack.edgeInsets = NSEdgeInsets(top: 18, left: 22, bottom: 22, right: 22)
    let scroll = NSScrollView()
    scroll.hasVerticalScroller = true
    scroll.documentView = stack
    stack.translatesAutoresizingMaskIntoConstraints = false
    stack.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor, constant: -44).isActive = true
    playerView.translatesAutoresizingMaskIntoConstraints = false
    playerView.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
    playerView.heightAnchor.constraint(equalToConstant: 420).isActive = true
    stack.addArrangedSubview(playerView)
    let heading = NSTextField(labelWithString: "Расшифровка с реальными таймкодами SRT")
    heading.font = .systemFont(ofSize: 17, weight: .semibold)
    stack.addArrangedSubview(heading)
    for segment in segments {
      guard let start = segment["start_seconds"] as? Double, let end = segment["end_seconds"] as? Double, let text = segment["text"] as? String else { continue }
      let cue = button("[\(clock(start))] \(text)", #selector(seekTranscriptCue(_:)))
      cue.alignment = .left
      cue.toolTip = String(start)
      stack.addArrangedSubview(cue)
      let clip = button("Создать клип \(clock(start))–\(clock(end))", #selector(createSRTClip(_:)))
      clip.toolTip = "\(projectID)\n\(runID)\n\(sourceID)\n\(start)\n\(end)"
      stack.addArrangedSubview(clip)
    }
    window.contentView = scroll
    mediaPlayer = player
    mediaWindow = window
    window.center()
    window.makeKeyAndOrderFront(nil)
  }
  private func clock(_ seconds: Double) -> String {
    String(format: "%02d:%02d", Int(seconds) / 60, Int(seconds) % 60)
  }
  @objc private func seekTranscriptCue(_ sender: NSButton) {
    guard let value = sender.toolTip.flatMap(Double.init) else { return }
    mediaPlayer?.seek(to: CMTime(seconds: value, preferredTimescale: 600))
    mediaPlayer?.play()
  }
  @objc private func createSRTClip(_ sender: NSButton) {
    let values = sender.toolTip?.split(separator: "\n", maxSplits: 4).map(String.init) ?? []
    guard values.count == 5, let start = Double(values[3]), let end = Double(values[4]) else { return }
    sender.isEnabled = false
    sender.title = "Создаю локальный клип…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        let result = try bridge.json("create-media-clip", request: ["project_id": values[0], "run_id": values[1], "source_id": values[2], "start_seconds": start, "end_seconds": end])["result"] as? [String: Any]
        guard let path = result?["path"] as? String else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async { NSWorkspace.shared.open(URL(fileURLWithPath: path)); sender.title = "Клип создан — открыть"; sender.isEnabled = true }
      } catch {
        DispatchQueue.main.async { sender.title = "Не удалось создать клип"; sender.isEnabled = false; self.status.stringValue = error.localizedDescription }
      }
    }
  }
  @objc private func cancelRun() {
    guard !cancelPending, !terminationPending, let p = projectID, let r = runID else { return }
    cancelPending = true
    for case let control as NSButton in content.arrangedSubviews where control.action == #selector(cancelRun) {
      control.isEnabled = false
      control.title = "Останавливаю…"
    }
    let generation = navigationGeneration
    operationsError = "Останавливаю обработку…"
    status.stringValue = operationsError
    let service = bridge!
    serviceQueue.async {
      var failure = ""
      do { _ = try service.json("cancel-run", request: ["project_id": p, "run_id": r]) }
      catch { failure = error.localizedDescription }
      let message = failure
      DispatchQueue.main.async {
        self.cancelPending = false
        guard self.operationsVisible, !self.terminationPending, self.navigationGeneration == generation, self.projectID == p, self.runID == r else { return }
        self.operationsError = message
        self.operationsSnapshot = nil
        self.status.stringValue = message
        self.pollOperations()
      }
    }
  }
  @objc private func retryRun() {
    guard !terminationPending else { return }
    guard !retryPending else { return }
    guard let p = projectID, let r = runID else { return }
    retryPending = true
    let generation = navigationGeneration
    let service = bridge!
    operationsError = "Подготавливаю повтор; сохранённая расшифровка будет проверена перед использованием…"
    status.stringValue = operationsError
    serviceQueue.async {
      do {
        let value = try service.json("retry-run", request: ["project_id": p, "run_id": r])["result"] as? [String: Any]
        DispatchQueue.main.async {
          self.retryPending = false
          guard self.operationsVisible, !self.terminationPending, self.navigationGeneration == generation, self.projectID == p, self.runID == r else { return }
          self.runID = value?["run_id"] as? String
          self.renderOperations()
        }
      } catch {
        DispatchQueue.main.async {
          self.retryPending = false
          guard self.operationsVisible, !self.terminationPending, self.navigationGeneration == generation, self.projectID == p, self.runID == r else { return }
          self.operationsError = error.localizedDescription
          self.status.stringValue = self.operationsError
        }
      }
    }
  }
  private func renderProjects() {
    reset("Проекты", "Реальные локальные проекты Integra. Откройте проект, чтобы увидеть сохранённые источники и обработки.")
    do {
      let projects = try bridge.json("projects")["result"] as? [[String: Any]] ?? []
      if projects.isEmpty { add(NSTextField(labelWithString: "Проектов пока нет")) }
      for project in projects {
        guard let projectID = project["project_id"] as? String else { continue }
        let control = button(
          project["name"] as? String ?? "Проект", #selector(openProject(_:)))
        control.toolTip = projectID
        add(control)
        add(row("Источников: \(project["source_count"] ?? 0)", detail: "Статус: \(project["status"] ?? "")"))
      }
    } catch { status.stringValue = error.localizedDescription }
  }
  @objc private func openProject(_ sender: NSButton) {
    guard let identifier = sender.toolTip else { return }
    do {
      let project = try bridge.json("open-project", request: ["project_id": identifier])["result"]
        as? [String: Any] ?? [:]
      renderProject(project)
    } catch { status.stringValue = error.localizedDescription }
  }
  private func renderProject(_ project: [String: Any]) {
    let projectID = project["project_id"] as? String ?? ""
    reset(
      project["name"] as? String ?? "Проект",
      "Сохранённые обработки и исходники этого проекта. Все записи взяты из реального журнала запусков Integra.")
    do {
      let items = try bridge.json("recent-runs")["result"] as? [[String: Any]] ?? []
      let runs = items.filter { (($0["project"] as? [String: Any])?["project_id"] as? String) == projectID }
      if runs.isEmpty { add(NSTextField(labelWithString: "В проекте пока нет запусков")) }
      for item in runs {
        let run = item["run"] as? [String: Any] ?? [:]
        guard let runID = run["run_id"] as? String else { continue }
        let control = button("Открыть обработку — \(run["state"] ?? "UNKNOWN")", #selector(openRecentRun(_:)))
        control.toolTip = "\(projectID)\n\(runID)"
        add(control)
        for source in ((run["plan"] as? [String: Any])?["sources"] as? [[String: Any]]) ?? [] {
          add(row(source["display_name"] as? String ?? "Источник", detail: sourcePresentationDetail(source)))
        }
      }
    } catch { status.stringValue = error.localizedDescription }
  }
  private func renderSources() {
    reset("Исходники", "Все сохранённые локальные источники из реальных обработок Integra. Выберите источник, чтобы открыть его результат.")
    do {
      let items = try bridge.json("recent-runs")["result"] as? [[String: Any]] ?? []
      var seen = Set<String>(), count = 0
      for item in items {
        let project = item["project"] as? [String: Any] ?? [:]
        let run = item["run"] as? [String: Any] ?? [:]
        guard let projectID = project["project_id"] as? String, let runID = run["run_id"] as? String else { continue }
        for source in ((run["plan"] as? [String: Any])?["sources"] as? [[String: Any]]) ?? [] {
          guard let sourceID = source["source_id"] as? String, seen.insert(sourceID).inserted else { continue }
          let control = button(source["display_name"] as? String ?? "Источник", #selector(openRecentRun(_:)))
          control.toolTip = "\(projectID)\n\(runID)"
          add(control)
          add(row(sourcePresentationDetail(source), detail: project["name"] as? String ?? "Проект Integra"))
          count += 1
        }
      }
      if count == 0 { add(NSTextField(labelWithString: "Сохранённых исходников пока нет")) }
    } catch { status.stringValue = error.localizedDescription }
  }
  private func renderHistory() {
    reset("История", "Сохранённые реальные обработки. Выберите запись, чтобы открыть её состояние и результаты.")
    do {
      let items = try bridge.json("recent-runs")["result"] as? [[String: Any]] ?? []
      if items.isEmpty { add(NSTextField(labelWithString: "Обработок пока нет")) }
      for item in items {
        let project = item["project"] as? [String: Any] ?? [:]
        let run = item["run"] as? [String: Any] ?? [:]
        guard let projectID = project["project_id"] as? String,
          let runID = run["run_id"] as? String
        else { continue }
        let control = button(
          "\(project["name"] ?? "Проект") — \(run["state"] ?? "UNKNOWN")",
          #selector(openRecentRun(_:)))
        control.toolTip = "\(projectID)\n\(runID)"
        add(control)
      }
    } catch { status.stringValue = error.localizedDescription }
  }
  @objc private func openRecentRun(_ sender: NSButton) {
    let identifiers = sender.toolTip?.split(separator: "\n", maxSplits: 1).map(String.init) ?? []
    guard identifiers.count == 2 else { return }
    projectID = identifiers[0]
    runID = identifiers[1]
    do {
      let run = try bridge.json(
        "run-status", request: ["project_id": identifiers[0], "run_id": identifiers[1]])["result"]
        as? [String: Any] ?? [:]
      if run["state"] as? String == "COMPLETED" { renderOutputs() } else { renderOperations() }
    } catch { status.stringValue = error.localizedDescription }
  }
  private func renderOutputs() {
    reset("Обработанные материалы", "Конкретные артефакты текущей обработки.")
    if let p = projectID, let r = runID {
      do {
        let run =
          try bridge.json("run-status", request: ["project_id": p, "run_id": r])["result"]
          as? [String: Any] ?? [:]
        if run["state"] as? String == "COMPLETED" {
          renderResultRows(run)
        } else if run["state"] as? String == "FAILED" {
          add(NSTextField(labelWithString: "Обработка завершилась ошибкой"))
          renderResultRows(run)
        } else {
          add(NSTextField(labelWithString: "Текущая обработка ещё не завершена"))
        }
      } catch { status.stringValue = error.localizedDescription }
    } else {
      add(NSTextField(labelWithString: "Готовых материалов в текущей сессии нет"))
    }
  }
  private var knowledgeNotebook: [String: Any] = [:]
  private var knowledgeIdentity: [String: Any] = [:]
  private var knowledgeK2: [String: Any] = [:]

  private func renderKnowledge() {
    reset("База знаний", "Тематические конспекты из завершённых обработок. Проверка фрагментов не означает принятия канонических знаний.")
    add(button("Добавить результат Process", #selector(selectKnowledgeSource)))
    let bridge = self.bridge!
    let generation = navigationGeneration
    serviceQueue.async {
      do {
        let sources = try bridge.json("knowledge-sources")["result"] as? [[String: Any]] ?? []
        DispatchQueue.main.async {
          guard self.navigationGeneration == generation else { return }
          let saved = sources.filter { ($0["notebook_status"] as? String) != "NOT_ADDED" }
          if saved.isEmpty { self.add(NSTextField(labelWithString: "Сохранённых конспектов пока нет")) }
          for source in saved {
            let control = self.button("Открыть конспект · \(source["source_name"] ?? "Источник")", #selector(self.openKnowledgeSource(_:)), enabled: source["notebook_available"] as? Bool == true)
            control.toolTip = "\(source["project_id"] ?? "")\n\(source["run_id"] ?? "")\n\(source["source_id"] ?? "")"
            self.add(control)
            if let reason = source["reason"] as? String { self.add(NSTextField(wrappingLabelWithString: "Недоступен: \(reason)")) }
          }
        }
      } catch { DispatchQueue.main.async { self.status.stringValue = error.localizedDescription } }
    }
  }

  @objc private func selectKnowledgeSource() {
    let bridge = self.bridge!
    let generation = navigationGeneration
    status.stringValue = "Проверяю сохранённые результаты…"
    serviceQueue.async {
      do {
        let sources = try bridge.json("knowledge-sources")["result"] as? [[String: Any]] ?? []
        DispatchQueue.main.async {
          guard self.navigationGeneration == generation else { return }
          let alert = NSAlert(); alert.messageText = "Добавить результат Process"
          alert.informativeText = "Выберите завершённый источник с сохранёнными темами и точным временем слов. Повторная обработка не запускается."
          let list = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 620, height: 28))
          for source in sources {
            list.addItem(withTitle: "\(source["project_name"] ?? "Проект") · \(source["source_name"] ?? "Источник")" + (source["eligible"] as? Bool == true ? "" : " — недоступен"))
          }
          alert.accessoryView = list; alert.addButton(withTitle: "Добавить"); alert.addButton(withTitle: "Отмена")
          guard !sources.isEmpty else { self.status.stringValue = "Нет сохранённых результатов Process"; return }
          guard alert.runModal() == .alertFirstButtonReturn, sources.indices.contains(list.indexOfSelectedItem) else { return }
          let selected = sources[list.indexOfSelectedItem]
          guard selected["eligible"] as? Bool == true else { self.status.stringValue = "Источник недоступен: \(selected["reason"] ?? "Неполный результат")"; return }
          self.loadKnowledge(["project_id": selected["project_id"]!, "run_id": selected["run_id"]!, "source_id": selected["source_id"]!], create: true)
        }
      } catch { DispatchQueue.main.async { self.status.stringValue = error.localizedDescription } }
    }
  }

  @objc private func openKnowledgeSource(_ sender: NSButton) {
    let ids = sender.toolTip?.split(separator: "\n").map(String.init) ?? []
    guard ids.count == 3 else { return }
    loadKnowledge(["project_id": ids[0], "run_id": ids[1], "source_id": ids[2]], create: false)
  }

  private func loadKnowledge(_ identity: [String: Any], create: Bool) {
    navigationGeneration += 1
    let generation = navigationGeneration
    status.stringValue = "Открываю конспект без повторной обработки…"
    let bridge = self.bridge!
    serviceQueue.async {
      do {
        var request = identity; request["create"] = create
        let notebook = try bridge.json("knowledge-open", request: request)["result"] as? [String: Any] ?? [:]
        DispatchQueue.main.async { guard self.navigationGeneration == generation else { return }; self.knowledgeIdentity = identity; self.knowledgeNotebook = notebook; self.renderKnowledgeNotebook() }
      } catch { DispatchQueue.main.async { self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription } }
    }
  }

  private func renderKnowledgeNotebook() {
    let notebook = knowledgeNotebook
    let complete = notebook["status"] as? String == "REVIEWED_FRAGMENTS_V2"
    reset("Тематический конспект", complete ? "Проверенные фрагменты. Это не Canonical Knowledge ACCEPTED." : "Проверка не завершена. Отложенные фрагменты нельзя экспортировать как проверенные.")
    let processing = notebook["source_processing_state"] as? String == "COMPLETED" ? "Обработка завершена" : "Состояние обработки неизвестно"
    add(NSTextField(wrappingLabelWithString: "Источник: \(notebook["source_title"] ?? "Источник")\n\(processing)\nID источника: \(notebook["source_id"] ?? "")\nВерсия источника: \(notebook["source_revision_sha256"] ?? "")\nВерсия тем: \(notebook["topics_revision_sha256"] ?? "")\nВерсия файла расшифровки: \(notebook["transcript_artifact_sha256"] ?? "")\nКонспект: \(notebook["notebook_id"] ?? "")\nТочность: диапазон слов."))
    for revision in notebook["transcript_revisions"] as? [[String: Any]] ?? [] {
      let provenance = revision["transcript_provenance"] as? [String: Any] ?? [:]
      let verification: String
      switch provenance["verification_state"] as? String {
      case "machine_unverified": verification = "Машинная расшифровка: не проверена человеком"
      case "selectively_verified": verification = "Расшифровка выборочно проверена человеком; остальные участки не подтверждены"
      case "fully_human_verified": verification = "Расшифровка полностью проверена человеком"
      default: verification = "Состояние проверки расшифровки неизвестно"
      }
      let origin: String
      switch provenance["origin"] as? String {
      case "machine_generated": origin = "Машинное распознавание"
      case "human_verified": origin = "Проверенный человеком текст"
      case "human_corrected": origin = "Исправленный человеком текст"
      default: origin = "Происхождение текста не подтверждено"
      }
      add(NSTextField(wrappingLabelWithString: "\(verification)\nПроисхождение: \(origin)\nВерсия текста: \(revision["id"] ?? "")\nПроверка тематических фрагментов не изменяет статус исходной расшифровки."))
    }
    add(button("Все конспекты", #selector(showKnowledgeLanding)))
    if !complete { add(button("Проверить фрагменты", #selector(reviewKnowledge))) }
    if complete {
      add(button("Структурировать знания / открыть принятую версию", #selector(openCanonicalKnowledge)))
      add(button("Экспортировать конспект в Obsidian", #selector(exportKnowledge)))
    }
    if let reviewed = notebook["reviewed"] as? [String: Any], let lineage = reviewed["fragment_lineage"] as? [[String: Any]] {
      let units = (reviewed["semantic_knowledge"] as? [[String: Any]] ?? []) + (reviewed["non_semantic_excluded"] as? [[String: Any]] ?? [])
      for unit in units {
        add(NSTextField(wrappingLabelWithString: "\(unit["title"] ?? "Фрагмент")\n\(unit["summary"] ?? "")\n" + (unit["disposition"] as? String == "NON_SEMANTIC_EXCLUDED" ? "Исключён из конспекта" : "Включён в конспект")))
        for ref in unit["fragment_refs"] as? [String] ?? [] {
          if let fragment = lineage.first(where: { $0["id"] as? String == ref }) { addKnowledgeEvidence(fragment, id: ref) }
        }
      }
    } else {
      for topic in notebook["topics"] as? [[String: Any]] ?? [] {
        add(NSTextField(wrappingLabelWithString: "\(topic["title"] ?? "Тема")\n\(topic["summary"] ?? "")"))
        addKnowledgeEvidence(topic, id: topic["id"] as? String ?? "")
      }
    }
    status.stringValue = complete ? "Конспект сохранён; источник и версии проверены" : "Решения сохраняются только после явного выбора"
  }

  private func addKnowledgeEvidence(_ fragment: [String: Any], id: String) {
    add(NSTextField(wrappingLabelWithString: "Цитата: \(fragment["quote"] ?? "")\nКонтекст: \(fragment["context"] ?? fragment["quote"] ?? "")\nСлова: \(fragment["word_start_id"] ?? "") — \(fragment["word_end_id"] ?? "")\nВерсия текста: \(fragment["transcript_revision_id"] ?? "")"))
    let control = button("Открыть точный фрагмент источника", #selector(playKnowledgeFragment(_:)))
    control.toolTip = id; add(control)
  }

  @objc private func showKnowledgeLanding() { renderKnowledge() }

  @objc private func playKnowledgeFragment(_ sender: NSButton) {
    var request = knowledgeIdentity; request["fragment_id"] = sender.toolTip ?? ""
    request["notebook_id"] = knowledgeNotebook["notebook_id"]
    request["source_revision_sha256"] = knowledgeNotebook["source_revision_sha256"]
    presentKnowledgeNavigation(request)
  }

  private func presentKnowledgeNavigation(_ request: [String: Any], operation: String = "knowledge-navigation") {
    let bridge = self.bridge!
    let generation = navigationGeneration
    serviceQueue.async {
      do {
        let result = try bridge.json(operation, request: request)["result"] as? [String: Any] ?? [:]
        guard let path = result["media_path"] as? String, let start = result["start_seconds"] as? Double, let end = result["end_seconds"] as? Double else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          guard self.navigationGeneration == generation else { return }
          let alert = NSAlert(); alert.messageText = "Точный фрагмент источника"
          alert.informativeText = String(format: "%.3f–%.3f с\n", start, end) + "\(result["quote"] ?? "")\nВерсия источника проверена по хешу."
          let player = AVPlayer(url: URL(fileURLWithPath: path))
          let view = AVPlayerView(frame: NSRect(x: 0, y: 0, width: 620, height: 260)); view.player = player
          alert.accessoryView = view; alert.addButton(withTitle: "Закрыть")
          player.currentItem?.forwardPlaybackEndTime = CMTime(seconds: end, preferredTimescale: 600)
          player.seek(to: CMTime(seconds: start, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero) { ready in if ready { player.play() } }
          _ = alert.runModal(); player.pause()
        }
      } catch { DispatchQueue.main.async { self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription } }
    }
  }

  @objc private func reviewKnowledge() {
    guard let topics = knowledgeNotebook["topics"] as? [[String: Any]], let hash = knowledgeNotebook["state_sha256"] as? String else { return }
    let saved = knowledgeNotebook["decisions"] as? [[String: Any]] ?? []
    let alert = NSAlert(); alert.messageText = "Проверка тематического конспекта"
    alert.informativeText = "Принять, изменить или отложить каждый фрагмент. При изменении границ оставшиеся слова явно исключаются. Исходный текст и машинные темы не изменяются."
    let stack = FlippedStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 10
    var forms: [(String, NSPopUpButton, NSTextField, NSTextField, NSTextField, NSTextField)] = []
    let actions = ["ACCEPT", "EDIT", "REJECT", "DEFER"]
    for topic in topics {
      guard let id = topic["id"] as? String else { return }
      let prior = saved.first { $0["topic_id"] as? String == id } ?? [:]
      let label = NSTextField(wrappingLabelWithString: "Цитата: \(topic["quote"] ?? "")"); label.widthAnchor.constraint(equalToConstant: 600).isActive = true; stack.addArrangedSubview(label)
      let action = NSPopUpButton(); action.addItems(withTitles: ["Выберите решение", "Принять", "Изменить", "Исключить", "Отложить"])
      if let previous = prior["action"] as? String, let index = actions.firstIndex(of: previous) { action.selectItem(at: index+1) }
      stack.addArrangedSubview(action)
      let title = NSTextField(string: prior["new_title"] as? String ?? topic["title"] as? String ?? "")
      title.placeholderString = "Название"; title.widthAnchor.constraint(equalToConstant: 600).isActive = true; stack.addArrangedSubview(title)
      let summary = NSTextField(string: prior["new_summary"] as? String ?? topic["summary"] as? String ?? "")
      summary.placeholderString = "Конспект"; summary.widthAnchor.constraint(equalToConstant: 600).isActive = true; stack.addArrangedSubview(summary)
      stack.addArrangedSubview(NSTextField(labelWithString: "Точные границы — первый и последний ID слова"))
      let first = NSTextField(string: prior["word_start_id"] as? String ?? topic["word_start_id"] as? String ?? "")
      let last = NSTextField(string: prior["word_end_id"] as? String ?? topic["word_end_id"] as? String ?? "")
      first.widthAnchor.constraint(equalToConstant: 600).isActive = true; last.widthAnchor.constraint(equalToConstant: 600).isActive = true
      stack.addArrangedSubview(first); stack.addArrangedSubview(last)
      forms.append((id, action, title, summary, first, last))
    }
    let reviewer = NSTextField(string: "integra-local-human"); reviewer.placeholderString = "Идентификатор проверяющего"; stack.addArrangedSubview(reviewer)
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 640, height: 440)); scroll.hasVerticalScroller = true
    stack.setFrameSize(NSSize(width: 620, height: stack.fittingSize.height)); scroll.documentView = stack; alert.accessoryView = scroll
    alert.addButton(withTitle: "Сохранить решения"); alert.addButton(withTitle: "Отмена")
    while true {
      guard alert.runModal() == .alertFirstButtonReturn else { return }
      if forms.allSatisfy({ $0.1.indexOfSelectedItem > 0 }) { break }
      alert.informativeText = "Для каждого фрагмента выберите решение; спорное можно отложить."
    }
    let decisions: [[String: Any]] = forms.map { form in
      let original = topics.first { $0["id"] as? String == form.0 } ?? [:]
      let edited = form.2.stringValue != original["title"] as? String || form.3.stringValue != original["summary"] as? String || form.4.stringValue != original["word_start_id"] as? String || form.5.stringValue != original["word_end_id"] as? String
      let selected = actions[form.1.indexOfSelectedItem-1]
      let action = selected == "ACCEPT" && edited ? "EDIT" : selected
      var decision: [String: Any] = ["topic_id": form.0, "action": action, "reason": "Explicit local human K1 fragment review"]
      if action == "EDIT" || action == "DEFER" {
        decision["new_title"] = form.2.stringValue; decision["new_summary"] = form.3.stringValue
        decision["word_start_id"] = form.4.stringValue; decision["word_end_id"] = form.5.stringValue
      }
      return decision
    }
    var request = knowledgeIdentity; request["expected_state_sha256"] = hash; request["decisions"] = decisions; request["reviewer_id"] = reviewer.stringValue
    let bridge = self.bridge!
    let generation = navigationGeneration
    serviceQueue.async {
      do {
        let notebook = try bridge.json("knowledge-save", request: request)["result"] as? [String: Any] ?? [:]
        DispatchQueue.main.async { guard self.navigationGeneration == generation else { return }; self.knowledgeNotebook = notebook; self.renderKnowledgeNotebook() }
      } catch { DispatchQueue.main.async { self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription } }
    }
  }

  @objc private func exportKnowledge() {
    let request = knowledgeIdentity; let bridge = self.bridge!
    let generation = navigationGeneration
    serviceQueue.async {
      do {
        let result = try bridge.json("knowledge-package", request: request)["result"] as? [String: Any] ?? [:]
        guard let path = result["package_dir"] as? String else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async { guard self.navigationGeneration == generation else { return }; self.publishSelectedPackage(URL(fileURLWithPath: path), kind: "obsidian") }
      } catch { DispatchQueue.main.async { self.status.stringValue = error.localizedDescription } }
    }
  }

  @objc private func openCanonicalKnowledge() { performKnowledgeK2("open", request: knowledgeIdentity) }

  private func performKnowledgeK2(_ action: String, request: [String: Any]) {
    let bridge = self.bridge!
    let generation = navigationGeneration
    status.textColor = .labelColor
    status.stringValue = action == "open" ? "Открываю сохранённые знания…" : "Проверяю точные источники и решения…"
    serviceQueue.async {
      do {
        let result = try bridge.json("knowledge-k2-\(action)", request: request)["result"] as? [String: Any] ?? [:]
        DispatchQueue.main.async {
          guard self.navigationGeneration == generation else { return }
          self.knowledgeK2 = result
          self.renderCanonicalKnowledge()
        }
      } catch {
        DispatchQueue.main.async {
          guard self.navigationGeneration == generation else { return }
          self.status.textColor = .systemRed
          self.status.stringValue = "Не удалось завершить операцию: \(error.localizedDescription). Обновите сохранённый вид перед повторным применением."
        }
      }
    }
  }

  private func knowledgeText(_ value: Any?) -> String {
    guard let value, !(value is NSNull) else { return "—" }
    if let text = value as? String { return text }
    if let values = value as? [String] { return values.joined(separator: ", ") }
    if JSONSerialization.isValidJSONObject(value),
       let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]),
       let text = String(data: data, encoding: .utf8) { return text }
    return String(describing: value)
  }

  private func knowledgeRecordText(_ record: [String: Any]) -> String {
    let labels = ["preferred_label": "Название понятия", "aliases": "Варианты названия", "description": "Описание понятия",
                  "title": "Название темы", "summary": "Описание", "relation_type": "Тип связи",
                  "source_concept_id": "От понятия", "target_concept_id": "К понятию"]
    let lines = record.keys.sorted().compactMap { key -> String? in
      guard let label = labels[key] else { return nil }
      return "\(label): \(knowledgeText(record[key]))"
    }
    return (["ID: \(knowledgeText(record["id"]))"] + lines).joined(separator: "\n")
  }

  private func knowledgeEvidenceText(_ evidence: [String: Any]) -> String {
    let locator = evidence["locator"] as? [String: Any] ?? [:]
    let assurance = evidence["transcript_assurance"] as? [String: Any] ?? [:]
    let verification = ["machine_unverified": "Машинная расшифровка, не проверена человеком", "selectively_verified": "Расшифровка проверена выборочно", "fully_human_verified": "Расшифровка полностью проверена человеком"][assurance["verification_state"] as? String ?? ""] ?? "Статус проверки расшифровки см. в конспекте"
    let precision = evidence["precision"] as? String == "CUE_RANGE" ? "диапазон реплик" : "диапазон слов"
    return "Цитата: \(knowledgeText(evidence["quote"]))\nКонтекст: \(knowledgeText(evidence["context"]))\nИсточник: \(knowledgeText(evidence["source_id"]))\nВерсия источника: \(knowledgeText(evidence["source_revision_sha256"] ?? knowledgeNotebook["source_revision_sha256"]))\nВерсия текста: \(knowledgeText(evidence["transcript_revision_id"]))\n\(verification)\nФрагмент: \(knowledgeText(evidence["fragment_id"] ?? evidence["id"]))\nОснование: \(knowledgeText(evidence["evidence_id"] ?? evidence["id"]))\nТочность: \(precision) · \(knowledgeText(locator["start_seconds"] ?? evidence["start_seconds"]))–\(knowledgeText(locator["end_seconds"] ?? evidence["end_seconds"])) с\nГраницы: \(knowledgeText(evidence["word_start_id"] ?? locator["word_start_id"] ?? locator["cue_start_id"] ?? evidence["cue_start_id"])) — \(knowledgeText(evidence["word_end_id"] ?? locator["word_end_id"] ?? locator["cue_end_id"] ?? evidence["cue_end_id"]))"
  }

  private func knowledgeProposalText(_ proposal: [String: Any]) -> String {
    let kind = ["concepts": "Понятие", "topics": "Тема", "relations": "Связь"][proposal["entity_kind"] as? String ?? ""] ?? "Запись"
    let before = proposal["before"] as? [String: Any]
    let after = proposal["after"] as? [String: Any] ?? [:]
    let state = ["PROVISIONAL": "Предложено автоматически", "REVIEW_REQUIRED": "Требует смысловой проверки", "DEFERRED": "Отложено", "ACCEPTED": "Принято", "REJECTED": "Отклонено"][proposal["review_status"] as? String ?? ""] ?? knowledgeText(proposal["review_status"])
    let provenance = proposal["generation_provenance"] as? [String: Any] ?? [:]
    var text = "\(kind) · \(state)\nПредложение: \(knowledgeText(proposal["id"]))\nДействие: \(before == nil ? "Создать новую запись" : "Изменить существующую запись")\nСейчас: \(before.map(knowledgeRecordText) ?? "Записи нет")\nПредлагается:\n\(knowledgeRecordText(after))\nПроисхождение предложения: \(knowledgeText(provenance))"
    let duplicates = proposal["possible_duplicate_ids"] as? [String] ?? []
    if !duplicates.isEmpty { text += "\nВозможные совпадения названий: \(duplicates.joined(separator: ", ")). Совпадение названия не объединяет понятия." }
    for evidence in proposal["evidence"] as? [[String: Any]] ?? [] { text += "\n\n" + knowledgeEvidenceText(evidence) }
    return text
  }

  private func renderCanonicalKnowledge() {
    let current = knowledgeK2
    let hasRevision = current["revision_sha256"] as? String != nil
    reset("Структурированные знания", "Смысловая проверка понятий и связей. Принятие знаний не изменяет проверку исходной расшифровки.")
    add(button("Вернуться к конспекту", #selector(returnToKnowledgeNotebook)))
    add(button("Выбрать проверенные фрагменты", #selector(prepareCanonicalKnowledge)))
    let proposals = current["proposals"] as? [[String: Any]] ?? []
    if !proposals.isEmpty {
      add(NSTextField(wrappingLabelWithString: "Пакет предложений: \(knowledgeText(current["package_sha256"]))\nЧисло предложений: \(proposals.count). Для каждого требуется отдельное решение."))
      if current["package_applied"] as? Bool != true {
        add(button("Проверить смысловые предложения", #selector(reviewCanonicalKnowledge)))
        add(button("Предложить связь понятий", #selector(proposeKnowledgeRelation)))
      } else {
        add(NSTextField(wrappingLabelWithString: "Пакет уже рассмотрен. Для новой проверки или изменения существующих записей снова выберите их исходные фрагменты; ID принятых понятий сохраняются."))
      }
      for proposal in proposals {
        var display = proposal
        if current["package_applied"] as? Bool == true,
           let decision = (current["semantic_decisions"] as? [[String: Any]] ?? []).first(where: { $0["proposal_id"] as? String == proposal["id"] as? String }) {
          display["review_status"] = ["ACCEPT": "ACCEPTED", "EDIT": "ACCEPTED", "REJECT": "REJECTED", "DEFER": "DEFERRED"][decision["action"] as? String ?? ""]
        }
        add(NSTextField(wrappingLabelWithString: knowledgeProposalText(display)))
      }
    }
    for decision in current["semantic_decisions"] as? [[String: Any]] ?? [] {
      let action = ["ACCEPT": "Принято", "EDIT": "Принято с изменением", "REJECT": "Отклонено", "DEFER": "Отложено"][decision["action"] as? String ?? ""] ?? knowledgeText(decision["action"])
      let reviewer = current["semantic_reviewer"] as? [String: Any] ?? [:]
      add(NSTextField(wrappingLabelWithString: "Решение: \(action) · \(knowledgeText(decision["proposal_id"]))\nПроверяющий: \(knowledgeText(reviewer["actor_id"]))\nОбоснование: \(knowledgeText(decision["reason"]))"))
    }
    if hasRevision {
      add(NSTextField(wrappingLabelWithString: "Каноническая версия: \(knowledgeText(current["revision_sha256"]))\nРодительская версия: \(knowledgeText(current["parent_revision_sha256"]))\nВладелец: SeminarText. Здесь показано сохранённое представление."))
      add(button("Обновить сохранённое представление", #selector(openCanonicalKnowledge)))
      add(button("Предпросмотр / экспорт знаний в Obsidian", #selector(exportCanonicalKnowledge)))
      let view = current["knowledge_view"] as? [String: Any] ?? [:]
      let records = view["records"] as? [String: Any] ?? [:]
      add(NSTextField(labelWithString: "Принятые понятия, темы и связи"))
      for key in ["topics", "concepts", "relations"] {
        for record in records[key] as? [[String: Any]] ?? [] {
          add(NSTextField(wrappingLabelWithString: knowledgeRecordText(record)))
          for evidenceID in record["evidence_refs"] as? [String] ?? [] {
            let source = button("Открыть источник · \(evidenceID)", #selector(playCanonicalKnowledgeEvidence(_:)))
            source.toolTip = evidenceID; add(source)
          }
        }
      }
      let terms = view["terms"] as? [[String: Any]] ?? []
      if !terms.isEmpty {
        add(NSTextField(wrappingLabelWithString: "Термины — названия и варианты понятий:\n" + terms.map { "\(knowledgeText($0["value"] ?? $0["label"])) → \(knowledgeText($0["concept_id"]))" }.joined(separator: "\n")))
      }
      let graph = view["graph"] as? [String: Any] ?? [:]
      add(NSTextField(wrappingLabelWithString: "Граф знаний · \(knowledgeText(graph["graph_sha256"]))\n" + (graph["edges"] as? [[String: Any]] ?? []).map { "\(knowledgeText($0["from_id"])) → \(knowledgeText($0["kind"])) → \(knowledgeText($0["to_id"]))" }.joined(separator: "\n")))
      if let diff = current["diff"] as? [String: Any] {
        add(NSTextField(wrappingLabelWithString: "Изменения версии (механическое сравнение записей):\nДобавлено: \(knowledgeText(diff["added_ids"]))\nУдалено: \(knowledgeText(diff["removed_ids"]))\nИзменены байты: \(knowledgeText(diff["changed_ids"]))\nСмысловые противоречия этим сравнением не определяются."))
      }
    }
    status.stringValue = hasRevision ? "Сохранённая каноническая версия проверена" : "Предложения остаются предварительными до вашего явного решения"
  }

  @objc private func returnToKnowledgeNotebook() { renderKnowledgeNotebook() }

  private func knowledgeReviewScroll(_ stack: FlippedStackView, height: CGFloat = 440) -> NSScrollView {
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 660, height: height))
    scroll.hasVerticalScroller = true
    stack.setFrameSize(NSSize(width: 640, height: max(height, stack.fittingSize.height)))
    scroll.documentView = stack
    return scroll
  }

  private func addKnowledgeReviewLabel(_ text: String, to stack: FlippedStackView) {
    let label = NSTextField(wrappingLabelWithString: text)
    label.widthAnchor.constraint(equalToConstant: 620).isActive = true
    stack.addArrangedSubview(label)
  }

  @objc private func prepareCanonicalKnowledge() {
    let fragments = knowledgeK2["eligible_fragments"] as? [[String: Any]] ?? []
    guard !fragments.isEmpty else { status.stringValue = "Нет проверенных фрагментов для структурирования"; return }
    let alert = NSAlert(); alert.messageText = "Выберите точные проверенные фрагменты"
    alert.informativeText = "Выбранные фрагменты станут основаниями предварительных понятий и тем. Смысловые решения принимаются на следующем шаге. Новый пакет заменит текущие предварительные предложения."
    let stack = FlippedStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
    var choices: [(String, NSButton)] = []
    for fragment in fragments {
      guard let id = fragment["id"] as? String else { continue }
      let choice = NSButton(checkboxWithTitle: fragment["title"] as? String ?? "Фрагмент", target: nil, action: nil)
      choice.state = .off; stack.addArrangedSubview(choice); choices.append((id, choice))
      addKnowledgeReviewLabel(knowledgeEvidenceText(fragment), to: stack)
    }
    alert.accessoryView = knowledgeReviewScroll(stack)
    alert.addButton(withTitle: "Подготовить предложения"); alert.addButton(withTitle: "Отмена")
    guard alert.runModal() == .alertFirstButtonReturn else { return }
    let ids = choices.filter { $0.1.state == .on }.map { $0.0 }
    guard !ids.isEmpty else { status.stringValue = "Выберите хотя бы один проверенный фрагмент"; return }
    var request = knowledgeIdentity
    request["notebook_id"] = knowledgeK2["notebook_id"]
    request["expected_state_sha256"] = knowledgeK2["state_sha256"]
    request["selected_fragment_ids"] = ids
    performKnowledgeK2("prepare", request: request)
  }

  @objc private func reviewCanonicalKnowledge() {
    let proposals = knowledgeK2["proposals"] as? [[String: Any]] ?? []
    guard !proposals.isEmpty, let hash = knowledgeK2["package_sha256"] as? String else { return }
    let reviewDialog = KnowledgeReviewDialog()
    let alert = reviewDialog.alert; alert.messageText = "Смысловая проверка знаний — шаг 1 из 2"
    alert.informativeText = "Выберите решение и заполните обоснование для каждого предложения. Затем проверьте пакет на шаге 2 и явно подтвердите применение. Изменённые поля принимаются только через «Изменить и принять»."
    let stack = FlippedStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
    addKnowledgeReviewLabel("ID проверяющего: латинские строчные буквы, цифры, точка, дефис или подчёркивание; от 3 до 128 символов", to: stack)
    let reviewer = NSTextField(string: ""); reviewer.placeholderString = "Например: reviewer.ivanov"
    reviewer.widthAnchor.constraint(equalToConstant: 620).isActive = true; stack.addArrangedSubview(reviewer)
    var forms: [(String, NSPopUpButton, [(String, NSTextField)], NSTextField)] = []
    var relationForms: [String: NSPopUpButton] = [:]
    let relationTypes = knowledgeK2["supported_relation_types"] as? [String] ?? []
    let actions = ["ACCEPT", "EDIT", "REJECT", "DEFER"]
    let fieldLabels = ["preferred_label": "Название понятия", "aliases": "Варианты названия (через запятую)", "description": "Описание понятия", "title": "Название темы", "summary": "Описание"]
    for (index, proposal) in proposals.enumerated() {
      guard let id = proposal["id"] as? String else { return }
      let after = proposal["after"] as? [String: Any] ?? [:]
      addKnowledgeReviewLabel("Предложение \(index + 1) из \(proposals.count): \(knowledgeText(after["preferred_label"] ?? after["title"] ?? after["relation_type"]))", to: stack)
      let action = NSPopUpButton(); action.addItems(withTitles: ["Выберите решение", "Принять", "Изменить и принять", "Отклонить", "Отложить"])
      stack.addArrangedSubview(action)
      var fields: [(String, NSTextField)] = []
      for key in proposal["editable_fields"] as? [String] ?? [] {
        if key == "relation_type" {
          addKnowledgeReviewLabel("Тип связи при изменении", to: stack)
          let relation = NSPopUpButton(); relation.addItems(withTitles: relationTypes.map(knowledgeRelationTitle))
          if let current = after[key] as? String, let index = relationTypes.firstIndex(of: current) { relation.selectItem(at: index) }
          stack.addArrangedSubview(relation); relationForms[id] = relation
          continue
        }
        guard let label = fieldLabels[key] else { continue }
        addKnowledgeReviewLabel(label, to: stack)
        let field = NSTextField(string: knowledgeText(after[key]) == "—" ? "" : knowledgeText(after[key]))
        field.widthAnchor.constraint(equalToConstant: 620).isActive = true
        stack.addArrangedSubview(field); fields.append((key, field))
      }
      let reason = NSTextField(string: ""); reason.placeholderString = "Обоснование решения"
      reason.widthAnchor.constraint(equalToConstant: 620).isActive = true; stack.addArrangedSubview(reason)
      addKnowledgeReviewLabel(knowledgeProposalText(proposal), to: stack)
      forms.append((id, action, fields, reason))
    }
    alert.accessoryView = reviewDialog.accessory(knowledgeReviewScroll(stack))
    reviewDialog.validate = {
      let entries = forms.map { form -> (NSPopUpButton, NSTextField, Bool, Bool) in
          let original = proposals.first { $0["id"] as? String == form.0 }?["after"] as? [String: Any] ?? [:]
          var changed = form.2.contains(where: { $0.1.stringValue != (self.knowledgeText(original[$0.0]) == "—" ? "" : self.knowledgeText(original[$0.0])) })
          if let relation = relationForms[form.0], relationTypes.indices.contains(relation.indexOfSelectedItem) {
            changed = changed || relationTypes[relation.indexOfSelectedItem] != original["relation_type"] as? String
          }
          return (form.1, form.3, changed, !form.2.isEmpty || relationForms[form.0] != nil)
      }
      return reviewDialog.validateReview(reviewer: reviewer, entries: entries)
    }
    reviewDialog.configure(primaryTitle: "Проверить пакет решений → шаг 2")
    defer { reviewDialog.validate = { nil } }
    guard reviewDialog.run() == .alertFirstButtonReturn else { return }
    var decisions: [[String: Any]] = []
    for form in forms {
      let action = actions[form.1.indexOfSelectedItem - 1]
      var decision: [String: Any] = ["proposal_id": form.0, "action": action, "reason": form.3.stringValue]
      if action == "EDIT" {
        guard !form.2.isEmpty || relationForms[form.0] != nil else { status.stringValue = "Для этой записи изменение не поддерживается. Выберите принять, отклонить или отложить."; return }
        var edited: [String: Any] = [:]
        for (key, field) in form.2 {
          edited[key] = key == "aliases" ? field.stringValue.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty } as Any : field.stringValue
        }
        if let relation = relationForms[form.0], relationTypes.indices.contains(relation.indexOfSelectedItem) {
          edited["relation_type"] = relationTypes[relation.indexOfSelectedItem]
        }
        decision["edited_fields"] = edited
      }
      decisions.append(decision)
    }
    let confirmationDialog = KnowledgeReviewDialog()
    let confirm = confirmationDialog.alert; confirm.messageText = "Применить пакет решений — шаг 2 из 2"
    confirm.informativeText = "Пакет SHA-256: \(hash)\nПроверяющий: \(reviewer.stringValue)\nВключены только перечисленные ниже решения. Принятые записи создадут новую неизменяемую каноническую версию. Отложенные и отклонённые предложения не принимаются."
    let enumeration = FlippedStackView(); enumeration.orientation = .vertical; enumeration.alignment = .leading; enumeration.spacing = 10
    let explicit = NSButton(checkboxWithTitle: "Я подтверждаю именно этот пакет и перечисленные решения", target: nil, action: nil)
    explicit.state = .off; enumeration.addArrangedSubview(explicit)
    for decision in decisions {
      let proposal = proposals.first { $0["id"] as? String == decision["proposal_id"] as? String } ?? [:]
      addKnowledgeReviewLabel("\(knowledgeText(decision["proposal_id"]))\nРешение: \(knowledgeText(decision["action"]))\nОбоснование: \(knowledgeText(decision["reason"]))\nИзменения: \(knowledgeText(decision["edited_fields"]))\n\(knowledgeProposalText(proposal))", to: enumeration)
    }
    confirm.accessoryView = confirmationDialog.accessory(knowledgeReviewScroll(enumeration))
    confirmationDialog.validate = {
      guard explicit.state == .on else {
        confirmationDialog.invalidField = explicit
        return "Отметьте явное подтверждение пакета. Применение ещё не выполнялось; решения остаются в этом окне."
      }
      return nil
    }
    confirmationDialog.configure(primaryTitle: "Применить подтверждённые решения")
    defer { confirmationDialog.validate = { nil } }
    guard confirmationDialog.run() == .alertFirstButtonReturn else { status.stringValue = "Пакет не подтверждён; знания не изменены"; return }
    var request = knowledgeIdentity
    request["package_sha256"] = hash; request["reviewer_id"] = reviewer.stringValue
    request["decisions"] = decisions; request["explicit_confirmation"] = true
    request["confirmed_proposal_ids"] = forms.map { $0.0 }.sorted()
    performKnowledgeK2("apply", request: request)
  }

  private func knowledgeRelationTitle(_ type: String) -> String {
    ["associated_with": "Связано с", "contradicts": "Противоречит", "depends_on": "Зависит от", "refines": "Уточняет", "supports": "Поддерживает"][type] ?? type
  }

  @objc private func proposeKnowledgeRelation() {
    let concepts = knowledgeK2["available_concepts"] as? [[String: Any]] ?? []
    let types = knowledgeK2["supported_relation_types"] as? [String] ?? []
    let proposals = knowledgeK2["proposals"] as? [[String: Any]] ?? []
    var selectedIDs = Set<String>()
    for proposal in proposals {
      for evidence in proposal["evidence"] as? [[String: Any]] ?? [] {
        if let id = evidence["fragment_id"] as? String ?? evidence["id"] as? String { selectedIDs.insert(id) }
      }
    }
    let fragments = (knowledgeK2["eligible_fragments"] as? [[String: Any]] ?? []).filter { selectedIDs.contains($0["id"] as? String ?? "") }
    guard concepts.count >= 2, !types.isEmpty, !fragments.isEmpty else { status.stringValue = "Для связи нужны два понятия и точное проверенное основание"; return }
    let alert = NSAlert(); alert.messageText = "Предложить связь понятий"
    alert.informativeText = "Выберите существующие ID понятий и точные основания связи. Связь останется предварительной и потребует отдельного смыслового решения. При принятии оба понятия должны быть приняты."
    let stack = FlippedStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
    let source = NSPopUpButton(); let target = NSPopUpButton(); let kind = NSPopUpButton()
    source.addItem(withTitle: "Выберите первое понятие"); target.addItem(withTitle: "Выберите второе понятие"); kind.addItem(withTitle: "Выберите тип связи")
    for concept in concepts {
      let label = "\(knowledgeText(concept["label"])) · \(knowledgeText(concept["id"]))"
      source.addItem(withTitle: label); target.addItem(withTitle: label)
    }
    kind.addItems(withTitles: types.map(knowledgeRelationTitle))
    stack.addArrangedSubview(source); stack.addArrangedSubview(kind); stack.addArrangedSubview(target)
    var choices: [(String, NSButton)] = []
    for fragment in fragments {
      guard let id = fragment["id"] as? String else { continue }
      let choice = NSButton(checkboxWithTitle: "Основание связи · \(fragment["title"] ?? id)", target: nil, action: nil)
      choice.state = .off; stack.addArrangedSubview(choice); choices.append((id, choice))
      addKnowledgeReviewLabel(knowledgeEvidenceText(fragment), to: stack)
    }
    alert.accessoryView = knowledgeReviewScroll(stack); alert.addButton(withTitle: "Добавить предложение связи"); alert.addButton(withTitle: "Отмена")
    guard alert.runModal() == .alertFirstButtonReturn else { return }
    let evidenceIDs = choices.filter { $0.1.state == .on }.map { $0.0 }
    guard source.indexOfSelectedItem > 0, target.indexOfSelectedItem > 0, kind.indexOfSelectedItem > 0,
          source.indexOfSelectedItem != target.indexOfSelectedItem, !evidenceIDs.isEmpty else {
      status.stringValue = "Выберите два разных понятия, тип связи и точное основание"; return
    }
    var relationInputs: [[String: Any]] = proposals.compactMap { proposal in
      guard proposal["entity_kind"] as? String == "relations", let record = proposal["after"] as? [String: Any] else { return nil }
      let refs = (proposal["evidence"] as? [[String: Any]] ?? []).compactMap { $0["fragment_id"] as? String ?? $0["id"] as? String }
      return ["source_concept_id": record["source_concept_id"] ?? "", "target_concept_id": record["target_concept_id"] ?? "", "relation_type": record["relation_type"] ?? "", "fragment_ids": refs]
    }
    relationInputs.append(["source_concept_id": concepts[source.indexOfSelectedItem-1]["id"] ?? "", "target_concept_id": concepts[target.indexOfSelectedItem-1]["id"] ?? "", "relation_type": types[kind.indexOfSelectedItem-1], "fragment_ids": evidenceIDs])
    var request = knowledgeIdentity
    request["notebook_id"] = knowledgeK2["notebook_id"]; request["expected_state_sha256"] = knowledgeK2["state_sha256"]
    request["selected_fragment_ids"] = selectedIDs.sorted(); request["relation_inputs"] = relationInputs
    performKnowledgeK2("prepare", request: request)
  }

  @objc private func playCanonicalKnowledgeEvidence(_ sender: NSButton) {
    var request = knowledgeIdentity
    request["revision_sha256"] = knowledgeK2["revision_sha256"]; request["evidence_id"] = sender.toolTip
    presentKnowledgeNavigation(request, operation: "knowledge-k2-navigation")
  }

  @objc private func exportCanonicalKnowledge() {
    var request = knowledgeIdentity; request["revision_sha256"] = knowledgeK2["revision_sha256"]
    let bridge = self.bridge!; let generation = navigationGeneration
    serviceQueue.async {
      do {
        let result = try bridge.json("knowledge-k2-package", request: request)["result"] as? [String: Any] ?? [:]
        guard let path = result["package_dir"] as? String else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async { guard self.navigationGeneration == generation else { return }; self.publishSelectedPackage(URL(fileURLWithPath: path), kind: "obsidian") }
      } catch { DispatchQueue.main.async { self.status.textColor = .systemRed; self.status.stringValue = error.localizedDescription } }
    }
  }

  @objc private func publishObsidian() { publication(kind: "obsidian") }
  @objc private func publishOneDrive() { publication(kind: "onedrive") }
  private func publication(kind: String) {
    do {
      let packages = try bridge.json("available-packages")["result"] as? [[String: Any]] ?? []
      guard !packages.isEmpty else { status.textColor = .systemRed; status.stringValue = "Нет проверенных package в завершённых обработках Integra."; return }
      let chooser = NSAlert()
      chooser.messageText = "Выберите готовый package"
      chooser.informativeText = "Показаны только package, которые Integra заново проверила в сохранённых завершённых запусках."
      let list = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 560, height: 28), pullsDown: false)
      for item in packages { list.addItem(withTitle: "\(item["project_name"] ?? "Проект") · \(item["source_name"] ?? "Источник") · \(item["package_id"] ?? "package")") }
      chooser.accessoryView = list; chooser.addButton(withTitle: "Выбрать"); chooser.addButton(withTitle: "Отмена")
      guard chooser.runModal() == .alertFirstButtonReturn, packages.indices.contains(list.indexOfSelectedItem), let package = packages[list.indexOfSelectedItem]["package_dir"] as? String else { return }
      let packagePath = URL(fileURLWithPath: package)
      publishSelectedPackage(packagePath, kind: kind)
    } catch { status.textColor = .systemRed; status.stringValue = error.localizedDescription }
  }
  private func publishSelectedPackage(_ packagePath: URL, kind: String) {
    do {
      let manifestPath = packagePath.appendingPathComponent("package.json").path
      guard FileManager.default.fileExists(atPath: manifestPath) else {
        status.textColor = .systemRed
        status.stringValue = "Нужен корректный package с файлом package.json."
        return
      }
      let targetPanel = NSOpenPanel()
      targetPanel.title =
        kind == "obsidian" ? "Выберите Obsidian Vault" : "Выберите локальную папку OneDrive"
      targetPanel.canChooseDirectories = true
      targetPanel.canChooseFiles = false
      guard targetPanel.runModal() == .OK, let targetURL = targetPanel.url else { return }
      let request = ["package_dir": packagePath.path, "target_dir": targetURL.path, "publication_target": kind]
      let preview = try bridge.json("package-preview", request: request)
      let alert = NSAlert()
      alert.messageText = "Подтвердить публикацию?"
      alert.informativeText =
        "Preview проверен: \(preview["result"] ?? [:]). OneDrive publication is local and never claims cloud verification."
      alert.addButton(withTitle: "Опубликовать")
      alert.addButton(withTitle: "Отмена")
      if alert.runModal() == .alertFirstButtonReturn {
        let result = try bridge.json("package-publish", request: request)
        status.textColor = .labelColor
        status.stringValue = "Результат: \(result["result"] ?? [:])"
      }
    } catch {
      status.textColor = .systemRed
      status.stringValue = error.localizedDescription
    }
  }
  private func renderDiagnostics() {
    reset("Диагностика", "Проверка реального локального runtime.")
    do {
      let value = try bridge.json("media-preflight")["result"] as? [String: Any] ?? [:]
      add(
        row(
          "Локальная расшифровка доступна",
          detail: "Whisper model SHA-256: \(value["model_sha256"] ?? "")"))
    } catch { status.stringValue = error.localizedDescription }
    do {
      let value = try bridge.json("seminartext-preflight")["result"] as? [String: Any] ?? [:]
      add(row("SeminarText Topics runtime", detail: "Pinned commit: \(value["commit_sha"] ?? "") · model: \(value["model"] ?? "")"))
    } catch {
      add(row("SeminarText Topics runtime — В разработке", detail: error.localizedDescription))
    }
  }
}

@main
struct IntegraApplication {
  @MainActor static func main() {
    if CommandLine.arguments.contains("--self-test") {
      guard let resources = Bundle.main.resourceURL else { exit(2) }
      do {
        let bridge = Bridge(resources: resources)
        let registry = try bridge.json("capability-registry", request: ["sources": []])
        guard registry["ok"] as? Bool == true else { exit(3) }
        print("INTEGRA_MACOS_SELF_TEST: PASS")
        exit(0)
      } catch {
        print("INTEGRA_MACOS_SELF_TEST: FAIL \(error)")
        exit(4)
      }
    }
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.setActivationPolicy(.regular)
    app.activate(ignoringOtherApps: true)
    app.run()
  }
}
