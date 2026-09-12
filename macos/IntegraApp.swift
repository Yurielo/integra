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
      "recent-runs", "available-packages", "cancel-run", "retry-run", "media-navigation", "create-media-clip", "package-preview", "package-publish",
      "obsidian-preview",
      "onedrive-preview",
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
    process.waitUntilExit()
    let data = output.fileHandleForReading.readDataToEndOfFile()
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
      "Введите одну или несколько ссылок, каждую с новой строки. Тип ссылки будет определён, но загрузка пока помечена «В разработке»."
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
        case "subtitles": title = "Открыть субтитры (SRT)"
        case "word_timeline": title = "Открыть Word Timeline (JSON)"
        case "translation": title = "Открыть перевод VideoText (JSON)"
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
        case "transcript_json":
          title = "Открыть сырую расшифровку (JSON)"
        case "package_dir": title = "Открыть управляемый package (для публикации)"
        case "package_id": title = "Открыть package id (metadata)"
        default: title = "Открыть: \(kind)"
        }
        let control = button(title, #selector(openOutput(_:)))
        control.toolTip = path as? String
        add(control)
      }
      if outputs["subtitles"] as? String != nil,
        let projectID = projectID, let runID = runID, let sourceID = result["source_id"] as? String
      {
        let control = button("Открыть видео/аудио с расшифровкой", #selector(showMediaNavigation(_:)))
        control.toolTip = "\(projectID)\n\(runID)\n\(sourceID)"
        add(control)
      }
    }
    add(section("СЛЕДУЮЩИЕ ДЕЙСТВИЯ"))
    for title in [
      "Темы и таймкоды", "База знаний", "Создать клипы", "Учебные материалы",
      "Маркетинговые материалы", "Подготовить публикацию",
    ] {
      add(button("\(title) — В разработке", #selector(unavailableAction), enabled: false))
    }
  }
  @objc private func unavailableAction() {}
  @objc private func openOutput(_ sender: NSButton) {
    if let path = sender.toolTip { NSWorkspace.shared.open(URL(fileURLWithPath: path)) }
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
      let request = ["package_dir": packagePath.path, "target_dir": targetURL.path]
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
