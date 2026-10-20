// White-box native-control regression; no synthetic events or bridge calls.
// The production action is tested without ending an actual modal session.
let application = NSApplication.shared
precondition(knowledgeSourceNavigationFailureText.contains("Проверьте доступность исходного файла"))
let relationProposals: [[String: Any]] = [["id": "relation-proposal", "entity_kind": "relations",
  "after": ["source_concept_id": "source", "target_concept_id": "target"]]]
for action in ["ACCEPT", "EDIT"] {
  precondition(knowledgeConfirmedRelationEndpoints([["proposal_id": "relation-proposal", "action": action]], relationProposals) == Set(["source", "target"]))
}
for action in ["DEFER", "REJECT"] {
  precondition(knowledgeConfirmedRelationEndpoints([["proposal_id": "relation-proposal", "action": action]], relationProposals).isEmpty)
}
let interactive = CommandLine.arguments.contains("--interactive") || Bundle.main.bundleIdentifier == "app.integra.qa.k2-dialog"
if interactive {
  application.setActivationPolicy(.regular)
  application.finishLaunching()
}
let dialog = KnowledgeReviewDialog()
let reason = NSTextField(string: "")
let choice = NSPopUpButton()
choice.addItems(withTitles: ["Выберите решение", "Принять", "Изменить и принять"])
let secondChoice = NSPopUpButton()
secondChoice.addItems(withTitles: ["Выберите решение", "Принять", "Изменить и принять"])
let edited = NSTextField(string: "Original")
let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 660, height: 440))
let content = NSView(frame: NSRect(x: 0, y: 0, width: 640, height: 1200))
content.addSubview(reason); content.addSubview(choice); content.addSubview(secondChoice)
content.addSubview(edited); scroll.documentView = content
dialog.alert.accessoryView = dialog.accessory(scroll)
dialog.validate = {
  dialog.validateReview(entries: [(choice, reason, edited.stringValue != "Original", true)])
}
dialog.configure(primaryTitle: "Check")
precondition(dialog.alert.buttons[0].target === dialog)
precondition(dialog.alert.buttons[0].action == #selector(KnowledgeReviewDialog.submit))
precondition(!dialog.validateSubmission())
choice.selectItem(at: 1)
edited.stringValue = "Edited"
precondition(!dialog.validateSubmission())
precondition(edited.stringValue == "Edited")
choice.selectItem(at: 2)
precondition(dialog.validateSubmission())
precondition(dialog.feedback.stringValue.isEmpty)
// Confirmation validation must retain the same controls and decisions.
let confirmation = KnowledgeReviewDialog()
let explicit = NSButton(checkboxWithTitle: "Confirm", target: nil, action: nil)
explicit.state = .off
confirmation.validate = { explicit.state == .on ? nil : "explicit confirmation required" }
precondition(!confirmation.validateSubmission())
precondition(explicit.state == .off && edited.stringValue == "Edited")
explicit.state = .on
precondition(confirmation.validateSubmission())
precondition(dialog.feedback.superview !== scroll.documentView)
choice.selectItem(at: 2)
precondition(dialog.validateReview(entries: [(choice, reason, false, false)]) != nil)
choice.selectItem(at: 0)
precondition(dialog.validateReview(entries: [(choice, reason, false, true)]) != nil)
// K1 presents one independent selector per fragment. A choice in the first
// must survive validation of an incomplete second fragment.
choice.selectItem(at: 1)
secondChoice.selectItem(at: 0)
precondition(dialog.validateSelections([choice, secondChoice]) == "Фрагмент 2: выберите решение.")
precondition(choice.indexOfSelectedItem == 1)
secondChoice.selectItem(at: 1)
precondition(dialog.validateSelections([choice, secondChoice]) == nil)
dialog.validate = { nil }; confirmation.validate = { nil }
print("NATIVE_DIALOG_GUARDS_PASS")
if interactive {
  // CUA-driven manual/native lifecycle test of the exact production controller.
  // This small control harness has no runtime, project, Candidate or apply API.
  dialog.alert.messageText = "QA dialog control — NOT an Integra Candidate"
  dialog.alert.informativeText = "Выберите решение. Неполная проверка должна оставить это же окно открытым."
  choice.frame = NSRect(x: 0, y: 1100, width: 620, height: 24)
  reason.frame = NSRect(x: 0, y: 1060, width: 620, height: 24)
  edited.frame = NSRect(x: 0, y: 1020, width: 620, height: 24)
  reason.placeholderString = "reason"
  reason.stringValue = ""; edited.stringValue = "Original"
  choice.selectItem(at: 0)
  dialog.validate = {
    dialog.validateReview(entries: [(choice, reason, edited.stringValue != "Original", true)])
  }
  if dialog.run() == .alertFirstButtonReturn {
    confirmation.alert.messageText = "QA explicit confirmation — step 2"
    let confirmScroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 660, height: 440))
    let confirmContent = NSView(frame: NSRect(x: 0, y: 0, width: 640, height: 440))
    explicit.frame = NSRect(x: 0, y: 380, width: 620, height: 24)
    explicit.state = .off; confirmContent.addSubview(explicit); confirmScroll.documentView = confirmContent
    confirmation.alert.accessoryView = confirmation.accessory(confirmScroll)
    confirmation.validate = { explicit.state == .on ? nil : "Explicit confirmation required; this window must remain open" }
    confirmation.configure(primaryTitle: "Apply (control test only)")
    if confirmation.run() == .alertFirstButtonReturn { print("NATIVE_MODAL_LIFECYCLE_PASS") }
  }
}
