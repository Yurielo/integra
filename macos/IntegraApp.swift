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

final class Bridge: @unchecked Sendable {
  private let resources: URL
  init(resources: URL) { self.resources = resources }
  func call(_ operation: String, request: [String: Any] = [:]) throws -> Data {
    let allowed = [
      "workflow", "deferred", "projects", "create-project", "open-project", "jobs", "start-job",
      "cancel-job", "resume-job", "import-media", "media-preflight", "seminartext-preflight", "project-view",
      "detect-sources", "capability-registry", "build-plan", "execute-plan", "run-status",
      "recent-runs", "available-packages", "cancel-run", "retry-run", "media-navigation", "create-media-clip", "build-reviewed-package", "package-preview", "package-publish",
      "obsidian-preview", "transcript-text",
      "onedrive-preview",
      "prepare-transcript-review", "apply-transcript-review", "prepare-topic-review",
      "prepare-knowledge-review", "apply-knowledge-review", "create-machine-evidence",
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

struct SidebarItem {
  let title: String
  let id: String
  let header: Bool
  let enabled: Bool
}

  @MainActor
  final class AppDelegate: NSObject, NSApplicationDelegate, NSTableViewDataSource, NSTableViewDelegate
  {
  private var window: NSWindow!, bridge: Bridge!
  private let sidebar = NSTableView(), content = FlippedStackView(),
    status = NSTextField(labelWithString: "")
  private var sources = [[String: Any]](), capabilities = [[String: Any]](),
    selected = Set<String>(), plan: [String: Any]?
  private var projectID: String?, runID: String?, timer: Timer?
  private var mediaPlayer: AVPlayer?, mediaWindow: NSWindow?
  private var reviewPlayer: AVPlayer?
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
    .init(title: "База знаний — В разработке", id: "knowledge", header: false, enabled: false),
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
    }
  }

  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
  func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
    Task {
      if let projectID, let runID {
        _ = try? bridge.json("cancel-run", request: ["project_id": projectID, "run_id": runID])
      }
      if let recent = try? bridge.json("recent-runs")["result"] as? [[String: Any]] {
        for item in recent {
          guard let project = item["project"] as? [String: Any], let run = item["run"] as? [String: Any],
                ["RUNNING", "QUEUED"].contains(run["state"] as? String ?? ""),
                let projectID = project["project_id"] as? String,
                let runID = run["run_id"] as? String
          else { continue }
          _ = try? bridge.json("cancel-run", request: ["project_id": projectID, "run_id": runID])
        }
      }
    }
    return .terminateNow
  }

  func applicationWillTerminate(_ notification: Notification) {
    timer?.invalidate()
    if let marker = ProcessInfo.processInfo.environment["INTEGRA_CLOSE_PROBE"] {
      try? "TERMINATED_AFTER_LAST_WINDOW_CLOSED\n"
        .write(toFile: marker, atomically: true, encoding: .utf8)
    }
  }

  private func buildWindow() {
    window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 1320, height: 760),
      styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
      backing: .buffered, defer: false)
    window.title = "Integra — Новая обработка"
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
    case "diagnostics": renderDiagnostics()
    default: break
    }
  }

  private func reset(_ title: String, _ subtitle: String) {
    timer?.invalidate()
    timer = nil
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
    case "translation": return "Перевод VideoText"
    case "topics": return "Темы и таймкоды"
    case "audio_enhancement": return "Улучшение звука"
    case "document_analysis": return "Анализ документа"
    case "ocr": return "OCR BookText / Surya"
    default: return stage
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
          "\(source["display_name"] ?? "Источник")", detail: "\(source["source_type"] ?? "UNKNOWN")"
        ))
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
  @objc private func addYouTube() {
    let alert = NSAlert()
    alert.messageText = "YouTube"
    alert.informativeText =
      "Введите одну или несколько ссылок, каждую с новой строки. Одиночное видео или плейлист будут загружены в проект после выбора доступного результата. Плейлист сначала получает фактический состав, затем скачивает элементы последовательно с checkpoint после каждого элемента."
    let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 420, height: 72))
    field.placeholderString = "https://youtube.com/watch?v=…"
    alert.accessoryView = field
    alert.addButton(withTitle: "Добавить")
    alert.addButton(withTitle: "Отмена")
    if alert.runModal() == .alertFirstButtonReturn {
      detect(field.stringValue.split(whereSeparator: \.isNewline).map(String.init))
    }
  }
  private func detect(_ inputs: [String]) {
    status.textColor = .secondaryLabelColor
    status.stringValue = "Определяю тип и реальные возможности…"
    let bridge = self.bridge!
    DispatchQueue.global(qos: .userInitiated).async {
      do {
        let detected =
          try bridge.json("detect-sources", request: ["inputs": inputs])["result"]
          as? [[String: Any]] ?? []
        let caps =
          try bridge.json("capability-registry", request: ["sources": detected])["result"]
          as? [[String: Any]] ?? []
        DispatchQueue.main.async {
          self.sources = detected
          self.capabilities = caps
          if let index = CommandLine.arguments.firstIndex(of: "--ui-probe-output"),
            CommandLine.arguments.indices.contains(index + 1)
          {
            self.selected = Set(
              CommandLine.arguments[index + 1].split(separator: ",").map(String.init))
            self.plan =
              try? self.bridge.json(
                "build-plan",
                request: ["sources": detected, "selected_outputs": Array(self.selected).sorted()]
              )["result"] as? [String: Any]
          } else {
            self.selected = []
            self.plan = nil
          }
          self.renderNew()
          self.runNativeSmokeIfRequested()
        }
      } catch {
        DispatchQueue.main.async {
          self.status.textColor = .systemRed
          self.status.stringValue = error.localizedDescription
        }
      }
    }
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
    guard let plan = plan else { return }
    status.textColor = .secondaryLabelColor
    status.stringValue = "Создаю проект и ставлю реальную обработку в очередь…"
    let bridge = self.bridge!
    let name = sources.first?["display_name"] as? String ?? "Новая обработка"
    DispatchQueue.global(qos: .userInitiated).async {
      do {
        let result =
          try bridge.json("execute-plan", request: ["plan": plan, "name": name])["result"]
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
    guard let directory = ProcessInfo.processInfo.environment["INTEGRA_NATIVE_SMOKE_DIR"],
      let dataRoot = ProcessInfo.processInfo.environment["INTEGRA_APP_DATA_ROOT"],
      dataRoot == directory + "/app-data", plan != nil,
      !selected.isEmpty, selected.isSubset(of: ["speed_video", "audio_analysis", "document_text"]),
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
    func actionButton(_ view: NSView) -> NSButton? {
      if let button = view as? NSButton, button.action == #selector(execute), button.isEnabled { return button }
      for child in view.subviews { if let button = actionButton(child) { return button } }
      return nil
    }
    capture("plan.png")
    guard let view = window.contentView, let button = actionButton(view) else { return }
    button.performClick(nil)
    let deadline = Date().addingTimeInterval(180)
    Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] probe in
      Task { @MainActor in
        guard let self else { probe.invalidate(); return }
        if let projectID = self.projectID, let runID = self.runID,
          let run = try? self.bridge.json("run-status", request: ["project_id": projectID, "run_id": runID])["result"] as? [String: Any],
          ["COMPLETED", "FAILED", "CANCELLED"].contains(run["state"] as? String ?? "")
        {
          probe.invalidate()
          self.renderOperations()
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

  private func renderOperations() {
    reset(
      "Выполняется",
      "Здесь показано реальное состояние backend-задания. Чтобы остановить обработку, нажмите «Отменить». Закрытие окна/приложения также отменяет активную задачу."
    )
    guard let projectID = projectID, let runID = runID else {
      add(NSTextField(labelWithString: "Активной обработки нет"))
      return
    }
    do {
      let run =
        try bridge.json("run-status", request: ["project_id": projectID, "run_id": runID])["result"]
        as? [String: Any] ?? [:]
      let state = run["state"] as? String ?? "UNKNOWN"
      let progress = run["progress"] as? Int
      let detail = run["message"] as? String ?? ""
      let done = run["completed_sources"] as? Int ?? 0
      let total = run["total_sources"] as? Int ?? 0
      add(row("Состояние: \(state)", detail: "Готово источников: \(done) из \(total)"))
      if let progress = progress { add(row("Прогресс", detail: "\(progress)%")) }
      if !detail.isEmpty { add(row("Подробности", detail: detail)) }
      if let stage = run["current_stage"] as? String { add(row("Текущий этап", detail: stageLabel(stage))) }
      if state == "RUNNING" || state == "QUEUED" {
        let stopButton = button("Отменить", #selector(cancelRun))
        stopButton.toolTip = "Немедленно остановить текущую обработку и сохранить текущий результат."
        add(stopButton)
      }
      if state == "FAILED" || state == "CANCELLED" { add(button("Повторить", #selector(retryRun))) }
      if state == "COMPLETED" { renderResultRows(run) }
      if state == "FAILED" { renderFailedASRReports(run) }
      if let error = run["error"] as? String { status.stringValue = error }
      if ["RUNNING", "QUEUED"].contains(state) { startPolling() }
    } catch { status.stringValue = error.localizedDescription }
  }
  private func startPolling() {
    timer?.invalidate()
    timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
      Task { @MainActor in self?.renderOperations() }
    }
  }
  private func renderResultRows(_ run: [String: Any]) {
    add(section("ГОТОВЫЕ РЕЗУЛЬТАТЫ"))
    for result in (run["source_results"] as? [[String: Any]]) ?? [] {
      add(
        row(
          result["display_name"] as? String ?? "Источник",
          detail: result["state"] as? String ?? "UNKNOWN"))
      let outputs = result["outputs"] as? [String: Any] ?? [:]
      for (kind, path) in outputs.sorted(by: { $0.key < $1.key }) {
        let title: String
        switch kind {
        case "transcript": title = "Открыть расшифровку (TXT)"
        case "transcript_cleaned": title = "Открыть очищенный текст SeminarText (производная версия)"
        case "transcript_quality_report": title = "Открыть отчёт проверки расшифровки"
        case "transcript_asr_record": title = "Открыть сведения о распознавании SeminarText"
        case "canonical_evidence": title = "Открыть Canonical Evidence SeminarText (JSON)"
        case "transcript_review_result": title = "Открыть подтверждение проверки TXT (JSON)"
        case "topic_review_drafts": title = "Открыть входные данные проверки тем SeminarText (JSON)"
        case "canonical_knowledge": title = "Открыть проверенные знания (JSON)"
        case "knowledge_markdown": title = "Открыть проверенные темы и цитаты"
        case "topic_review_package": title = "Открыть пакет проверки тем"
        case "topic_review_decisions": title = "Открыть сохранённые решения"
        case "reviewed_topics": title = "Открыть проверенные фрагменты (JSON)"
        case "reviewed_topics_markdown": title = "Открыть проверенные фрагменты и цитаты"
        case "subtitles": title = "Открыть субтитры (SRT)"
        case "word_timeline": title = "Открыть Word Timeline (JSON)"
        case "translation": title = "Открыть перевод VideoText (JSON)"
        case "downloaded_media": title = "Открыть загруженное видео/аудио YouTube"
        case "youtube_source_record": title = "Открыть сведения о загрузке YouTube (JSON)"
        case "playlist_snapshot": title = "Открыть фактический состав плейлиста YouTube (JSON)"
        case "playlist_discovery": title = "Открыть provenance плейлиста YouTube (JSON)"
        case "playlist_plan": title = "Открыть план обработки плейлиста (JSON)"
        case "playlist_checkpoint": title = "Открыть checkpoint плейлиста (JSON)"
        case "playlist_downloads": title = "Открыть записи скачанных элементов (JSON)"
        case "playlist_artifacts_directory": title = "Открыть загруженные элементы плейлиста"
        case "topics": title = "Открыть черновики тем SeminarText (JSON)"
        case "burned_video": title = "Открыть видео со встроенными субтитрами"
        case "clips_manifest": title = "Открыть список созданных клипов (JSON)"
        case "enhanced_audio": title = "Открыть улучшенный звук (M4A)"
        case "audio_enhancement_record": title = "Открыть сведения об улучшении звука (JSON)"
        case "text": title = "Открыть текстовый документ (TXT)"
        case "document_record": title = "Открыть контракт документа (JSON)"
        case "document_structure": title = "Открыть структуру документа (JSON)"
        case "discover_images": title = "Открыть встроенные изображения (JSON)"
        case "embedded_images_directory": title = "Открыть извлечённые изображения"
        case "embedded_images_manifest": title = "Открыть манифест извлечённых изображений (JSON)"
        case "booktext_text": title = "Открыть OCR-текст BookText (TXT)"
        case "booktext_markdown": title = "Открыть OCR-документ BookText (Markdown)"
        case "booktext_record": title = "Открыть OCR-результат BookText (JSON)"
        case "booktext_manifest": title = "Открыть манифест Integra / BookText (JSON)"
        case "booktext_review": title = "Открыть очередь проверки OCR (TXT)"
        case "booktext_review_json": title = "Открыть очередь проверки OCR (JSON)"
        case "booktext_searchable_pdf": title = "Открыть поисковый PDF BookText"
        case "booktext_pages": title = "Открыть обработанные страницы BookText"
        case "booktext_surya_raw": title = "Открыть исходный вывод Surya OCR"
        case "booktext_vision_qa": title = "Открыть Apple Vision QA"
        case "selected_ocr_pages": title = "Открыть выбранные OCR-страницы с исходной нумерацией"
        case "audio_analysis": title = "Открыть анализ звука VideoText"
        case "speed_video": title = "Открыть видео 1,25×"
        case "machine_evidence_record": title = "Открыть происхождение машинного Evidence"
        case "transcript_json":
          title = "Открыть сырую расшифровку (JSON)"
        case "package_dir": title = "Открыть управляемый package (для публикации)"
        case "package_id": title = "Открыть package id (metadata)"
        default: title = "Открыть: \(kind)"
        }
        if kind == "transcript", let projectID = projectID, let runID = runID,
          let sourceID = result["source_id"] as? String {
          let control = button(title, #selector(openTranscript(_:)))
          control.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
          add(control)
          continue
        }
        let control = button(title, #selector(openOutput(_:)))
        control.toolTip = path as? String
        add(control)
      }
      if outputs["topic_review_decisions"] as? String != nil,
        let projectID = projectID, let runID = runID, let sourceID = result["source_id"] as? String
      {
        let control = button("Подготовить проверенный пакет для Obsidian / OneDrive", #selector(buildReviewedPackage(_:)))
        control.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
        add(control)
      }
      if outputs["subtitles"] as? String != nil,
        let projectID = projectID, let runID = runID, let sourceID = result["source_id"] as? String
      {
        let control = button("Открыть видео/аудио с расшифровкой", #selector(showMediaNavigation(_:)))
        control.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
        add(control)
      }
      if outputs["transcript"] as? String != nil, outputs["word_timeline"] as? String != nil,
        let projectID = projectID, let runID = runID, let sourceID = result["source_id"] as? String
      {
        let hasEvidenceDependents = ["topic_review_drafts", "topic_review_package", "topic_review_decisions",
          "reviewed_topics", "canonical_knowledge", "package_dir"].contains { outputs[$0] != nil }
        let control = button(hasEvidenceDependents ? "Повторная проверка TXT — нужен новый запуск" : "Проверить TXT и создать Evidence",
          #selector(showTranscriptReview(_:)), enabled: !hasEvidenceDependents)
        control.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
        add(control)
        if outputs["canonical_evidence"] == nil {
          let machine = button("Продолжить с машинным текстом → Evidence", #selector(createMachineEvidence(_:)))
          machine.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
          add(machine)
        }
        add(row("Canonical Evidence", detail: "Полная проверка TXT необязательна. Машинный текст остаётся непроверенным; принятие тем — отдельное явное решение."))
      }
      if outputs["reviewed_topics"] == nil, outputs["canonical_knowledge"] == nil, outputs["canonical_evidence"] as? String != nil, outputs["topics"] as? String != nil,
        let projectID = projectID, let runID = runID, let sourceID = result["source_id"] as? String
      {
        let control = button("Подготовить темы к проверке", #selector(prepareTopicReview(_:)))
        control.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
        add(control)
        add(row("Проверка тем", detail: "Проверьте цитаты и явно примите или отклоните каждую тему."))
      }
    }
    add(section("СЛЕДУЮЩИЕ ДЕЙСТВИЯ"))
    for title in [
      "Редактор границ тем", "Редактор связей знаний", "Тематические клипы", "Учебные материалы",
      "Маркетинговые материалы", "Другие форматы публикации",
    ] {
      add(button("\(title) — В разработке", #selector(unavailableAction), enabled: false))
    }
  }
  private func renderFailedASRReports(_ run: [String: Any]) {
    for result in (run["source_results"] as? [[String: Any]]) ?? [] {
      guard result["state"] as? String == "FAILED",
        let outputs = result["outputs"] as? [String: Any],
        let report = outputs["transcript_quality_report"] as? String else { continue }
      add(section("РАСШИФРОВКА НЕ ПРОШЛА ПРОВЕРКУ КАЧЕСТВА"))
      add(row(result["display_name"] as? String ?? "Источник",
              detail: "Подозрительные фрагменты сохранены для проверки. Темы и знания из них не создавались."))
      let control = button("Открыть отчёт проверки расшифровки", #selector(openOutput(_:)))
      control.toolTip = report
      add(control)
    }
  }
  @objc private func unavailableAction() {}
  @objc private func createMachineEvidence(_ sender: NSButton) {
    let ids = sender.toolTip?.split(separator: "\n", maxSplits: 2).map(String.init) ?? []
    guard ids.count == 3 else { return }
    sender.isEnabled = false
    let bridge = self.bridge!
    DispatchQueue.global(qos: .userInitiated).async {
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
    DispatchQueue.global(qos: .userInitiated).async {
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
    sender.isEnabled = false; sender.title = "Подготавливаю review input…"
    let bridge = self.bridge!
    DispatchQueue.global(qos: .userInitiated).async {
      do {
        let result = try bridge.json("prepare-knowledge-review", request: [
          "project_id": identifiers[0], "run_id": identifiers[1], "source_id": identifiers[2]])["result"] as? [String: Any] ?? [:]
        guard result["status"] as? String == "REVIEW_REQUIRED" else { throw BridgeError.invalidResponse }
        DispatchQueue.main.async {
          sender.title = "Подготовить темы к проверке"; sender.isEnabled = true
          self.presentTopicReview(result, identifiers: identifiers)
        }
      } catch {
        DispatchQueue.main.async {
          let incompatible = error.localizedDescription.contains("BenchmarkSegments")
          sender.title = incompatible ? "Эти границы тем — В разработке" : "Повторить подготовку тем"
          sender.isEnabled = !incompatible
          self.status.textColor = .systemRed
          self.status.stringValue = incompatible ? "Границы этих тем пока не поддерживаются компонентом знаний. Решения не запрошены, знания не созданы." : error.localizedDescription
        }
      }
    }
  }
  private func presentTopicReview(_ package: [String: Any], identifiers: [String]) {
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
    DispatchQueue.global(qos: .userInitiated).async {
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
    DispatchQueue.global(qos: .userInitiated).async {
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
    DispatchQueue.global(qos: .userInitiated).async {
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
    DispatchQueue.global(qos: .userInitiated).async {
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
    guard let p = projectID, let r = runID else { return }
    do {
      _ = try bridge.json("cancel-run", request: ["project_id": p, "run_id": r])
      renderOperations()
    } catch { status.stringValue = error.localizedDescription }
  }
  @objc private func retryRun() {
    guard let p = projectID, let r = runID else { return }
    do {
      let value =
        try bridge.json("retry-run", request: ["project_id": p, "run_id": r])["result"]
        as? [String: Any]
      runID = value?["run_id"] as? String
      renderOperations()
    } catch { status.stringValue = error.localizedDescription }
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
          add(row(source["display_name"] as? String ?? "Источник", detail: source["source_type"] as? String ?? "UNKNOWN"))
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
          add(row(source["source_type"] as? String ?? "UNKNOWN", detail: project["name"] as? String ?? "Проект Integra"))
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
          renderFailedASRReports(run)
        } else {
          add(NSTextField(labelWithString: "Текущая обработка ещё не завершена"))
        }
      } catch { status.stringValue = error.localizedDescription }
    } else {
      add(NSTextField(labelWithString: "Готовых материалов в текущей сессии нет"))
    }
    add(section("ПУБЛИКАЦИЯ ПРОВЕРЕННОГО PACKAGE"))
    add(button("Экспортировать в Obsidian", #selector(publishObsidian)))
    add(button("Опубликовать в папку OneDrive", #selector(publishOneDrive)))
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
